import logging

from celery import chain, shared_task

from django.contrib.auth.models import Group, User
from django.utils.timezone import now

from allianceauth.services.tasks import QueueOnce

from .manager import (
    OutlineForbidden,
    OutlineRateLimited,
    outline_client,
)
from .models import (
    EXTERNAL_ID_PREFIX,
    GroupSyncRule,
    OutlineUser,
    external_id_for,
    group_is_synced,
)

logger = logging.getLogger(__name__)

# Same value as discord/tasks.py, which core does not export.
BULK_TASK_PRIORITY = 6

MAX_RETRIES = 3
RETRY_COUNTDOWN = 60 * 10


def _managed(group: dict) -> bool:
    return (group.get("externalId") or "").startswith(EXTERNAL_ID_PREFIX)


def _link(user, client):
    """Return the user's OutlineUser, creating it if Outline knows the email."""
    try:
        return user.outline
    except OutlineUser.DoesNotExist:
        pass

    if not user.email:
        logger.info("%s has no email address, cannot match an Outline account", user)
        return None

    account = client.user_by_email(user.email)
    if account is None:
        # Never create Outline accounts — OIDC login does that.
        logger.info("No Outline account for %s (%s)", user, user.email)
        return None

    outline_user, _ = OutlineUser.objects.update_or_create(
        user=user,
        defaults={"outline_user_id": account["id"], "email": user.email},
    )
    return outline_user


def _sync_user(user, client):
    outline_user = _link(user, client)
    if outline_user is None:
        return

    rules = list(GroupSyncRule.objects.filter(enabled=True))
    # Several AA accounts can share an email and so resolve to one Outline user.
    # The desired set is their union: computing it from one account alone makes
    # each sync strip the groups the others granted.
    sharing = User.objects.filter(
        outline__outline_user_id=outline_user.outline_user_id
    )
    desired = {
        external_id_for(group.pk): group.name
        for group in Group.objects.filter(user__in=sharing)
        .select_related("authgroup").distinct()
        if group_is_synced(group, rules)
    }

    all_groups = client.list_groups()
    by_external_id = {g["externalId"]: g for g in all_groups if g.get("externalId")}
    by_name = {g["name"]: g for g in all_groups}

    desired_ids = set()
    for external_id, name in desired.items():
        group = by_external_id.get(external_id)
        if group is None and name in by_name:
            # Adopt a group an admin made by hand, rather than colliding on the
            # unique name and getting a 409 from groups.create.
            group = by_name[name]
            client.update_group(group["id"], externalId=external_id)
        elif group is None:
            group = client.create_group(name, external_id)
        elif group["name"] != name:
            client.update_group(group["id"], name=name)
        desired_ids.add(group["id"])

    current = client.list_groups_for_user(outline_user.outline_user_id)
    current_ids = {g["id"] for g in current}

    for group_id in desired_ids - current_ids:
        client.add_user(group_id, outline_user.outline_user_id)

    # Only ever remove from groups this plugin manages.
    for group in current:
        if group["id"] not in desired_ids and _managed(group):
            client.remove_user(group["id"], outline_user.outline_user_id)

    outline_user.last_sync = now()
    outline_user.save(update_fields=["last_sync"])


def _retry(task, exc):
    if isinstance(exc, OutlineForbidden):
        logger.error(
            "Outline refused the request (403). Outline's own group sync cannot "
            "run alongside this plugin: %s", exc
        )
        return
    if isinstance(exc, OutlineRateLimited):
        raise task.retry(exc=exc, countdown=exc.retry_after)
    raise task.retry(exc=exc, countdown=RETRY_COUNTDOWN)


@shared_task(bind=True, name="outline.update_groups", base=QueueOnce,
             max_retries=MAX_RETRIES)
def update_groups(self, pk: int) -> None:
    user = User.objects.get(pk=pk)
    try:
        _sync_user(user, outline_client())
    except Exception as e:
        _retry(self, e)


@shared_task(bind=True, name="outline.delete_user", base=QueueOnce,
             max_retries=MAX_RETRIES)
def delete_user(self, pk: int) -> None:
    outline_user = OutlineUser.objects.filter(user_id=pk).first()
    if outline_user is None:
        return
    client = outline_client()
    try:
        for group in client.list_groups_for_user(outline_user.outline_user_id):
            if _managed(group):
                client.remove_user(group["id"], outline_user.outline_user_id)
    except Exception as e:
        _retry(self, e)
        return
    # The Outline account itself is left alone; only the link and the group
    # memberships this plugin created are removed.
    outline_user.delete()


@shared_task(bind=True, name="outline.link_user", max_retries=MAX_RETRIES)
def link_user(self, outline_user_id: str) -> None:
    """Entry point for the users.signin webhook."""
    client = outline_client()
    try:
        email = client.user_info(outline_user_id)["email"]
    except Exception as e:
        _retry(self, e)
        return

    users = User.objects.filter(email__iexact=email)
    for user in users:
        if not user.has_perm("outline.access_outline"):
            continue
        OutlineUser.objects.update_or_create(
            user=user,
            defaults={"outline_user_id": outline_user_id, "email": email},
        )
        update_groups.delay(user.pk)


@shared_task(bind=True, name="outline.sync_group", base=QueueOnce,
             max_retries=MAX_RETRIES)
def sync_group(self, pk: int, name: str) -> None:
    """Propagate an AA group rename. No AA signal covers this."""
    client = outline_client()
    try:
        group = client.group_by_external_id(external_id_for(pk))
        if group is not None and group["name"] != name:
            client.update_group(group["id"], name=name)
    except Exception as e:
        _retry(self, e)


@shared_task(bind=True, name="outline.delete_group", base=QueueOnce,
             max_retries=MAX_RETRIES)
def delete_group(self, pk: int) -> None:
    client = outline_client()
    try:
        group = client.group_by_external_id(external_id_for(pk))
        if group is not None and _managed(group):
            client.delete_group(group["id"])
    except Exception as e:
        _retry(self, e)


@shared_task(bind=True, name="outline.reconcile", base=QueueOnce,
             max_retries=MAX_RETRIES)
def reconcile(self) -> None:
    """Catch drift the signals miss, then resync everyone."""
    client = outline_client()
    try:
        groups = client.list_groups()
    except Exception as e:
        _retry(self, e)
        return

    rules = list(GroupSyncRule.objects.filter(enabled=True))
    if rules:
        for outline_group in groups:
            if not _managed(outline_group):
                continue
            pk = outline_group["externalId"][len(EXTERNAL_ID_PREFIX):]
            if not pk.isdigit():
                logger.warning("Skipping Outline group with malformed externalId %r",
                               outline_group["externalId"])
                continue
            aa_group = Group.objects.filter(pk=pk).select_related("authgroup").first()
            if aa_group is None or not group_is_synced(aa_group, rules):
                # One failed delete must not abort the sweep, and must not cost
                # the resync below — that would hide the deletions still happening.
                try:
                    client.delete_group(outline_group["id"])
                except Exception:
                    logger.exception("Could not delete Outline group %s",
                                     outline_group["id"])
    else:
        # Without rules every managed group looks orphaned. Deleting them all
        # would take their collection permissions with them.
        logger.warning(
            "No enabled group sync rules, skipping the deletion sweep"
        )

    pks = OutlineUser.objects.values_list("user_id", flat=True)
    if pks:
        chain([update_groups.si(pk) for pk in pks]).apply_async(
            priority=BULK_TASK_PRIORITY
        )

import re

from django.contrib.auth.models import Group
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models

EXTERNAL_ID_PREFIX = "allianceauth:"


def external_id_for(group_pk: int) -> str:
    return f"{EXTERNAL_ID_PREFIX}{group_pk}"


class OutlineUser(models.Model):
    """Link between an Alliance Auth user and an Outline account."""

    user = models.OneToOneField(
        "auth.User",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="outline",
    )
    # Not unique: this install has duplicate emails across AA accounts, and both
    # are expected to resolve to the same Outline user.
    outline_user_id = models.CharField(max_length=36, db_index=True)
    email = models.CharField(max_length=254)
    last_sync = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()
        permissions = (
            ("access_outline", "Can access the Outline service"),
        )

    def __str__(self) -> str:
        return self.email


def has_account(user) -> bool:
    try:
        return bool(user.outline.outline_user_id)
    except ObjectDoesNotExist:
        return False


class GroupSyncRule(models.Model):
    """One allow or deny rule deciding whether an AA group is mirrored into Outline."""

    ALLOW = "allow"
    DENY = "deny"
    ACTIONS = ((ALLOW, "Allow"), (DENY, "Deny"))

    EXACT = "exact"
    PREFIX = "prefix"
    REGEX = "regex"
    INTERNAL = "internal"
    MATCHES = (
        (EXACT, "Exact name"),
        (PREFIX, "Name prefix"),
        (REGEX, "Regex"),
        (INTERNAL, "Internal group flag"),
    )

    action = models.CharField(max_length=5, choices=ACTIONS)
    match = models.CharField(max_length=8, choices=MATCHES)
    value = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ignored for the internal group flag match.",
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()
        unique_together = ("action", "match", "value")
        verbose_name = "group sync rule"

    def __str__(self) -> str:
        if self.match == self.INTERNAL:
            return f"{self.action} internal groups"
        return f"{self.action} {self.match} {self.value}"

    def clean(self):
        if self.match == self.REGEX:
            try:
                re.compile(self.value)
            except re.error as e:
                raise ValidationError({"value": f"Invalid regex: {e}"}) from e
        elif self.match == self.EXACT:
            if not Group.objects.filter(name=self.value).exists():
                raise ValidationError({"value": "No Alliance Auth group has that name."})
        elif self.match == self.PREFIX and not self.value:
            raise ValidationError({"value": "A prefix is required."})

    def matches(self, group: Group) -> bool:
        if self.match == self.EXACT:
            return group.name == self.value
        if self.match == self.PREFIX:
            return group.name.startswith(self.value)
        if self.match == self.REGEX:
            return re.search(self.value, group.name) is not None
        if self.match == self.INTERNAL:
            authgroup = getattr(group, "authgroup", None)
            return bool(authgroup and authgroup.internal)
        return False


def group_is_synced(group: Group, rules=None) -> bool:
    """Decide whether `group` is mirrored into Outline.

    Deny beats allow, and an empty rule table syncs nothing — with
    `eveonline.autogroups` installed, failing open would push every corp and
    alliance group into Outline on first deploy.

    ponytail: an exact rule stores a name, so renaming that AA group orphans the
    rule. Swap the value for a FK to Group if that starts biting.
    """
    if rules is None:
        rules = list(GroupSyncRule.objects.filter(enabled=True))

    allowed = False
    for rule in rules:
        if not rule.matches(group):
            continue
        if rule.action == GroupSyncRule.DENY:
            return False
        allowed = True
    return allowed

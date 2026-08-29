"""Receivers for the events Alliance Auth does not cover.

Core's `m2m_changed` handler already routes group membership changes to every
service hook's `update_groups`. Nothing in core fires on a Group rename or
delete, and nothing knows about this plugin's sync rules — hence these.
"""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import tasks
from .models import GroupSyncRule


@receiver(post_save, sender=Group)
def group_saved(sender, instance, created, **kwargs):
    if created:
        # Creation is lazy: a group reaches Outline when it first has a member.
        return
    transaction.on_commit(
        lambda: tasks.sync_group.delay(instance.pk, instance.name)
    )


@receiver(post_delete, sender=Group)
def group_deleted(sender, instance, **kwargs):
    pk = instance.pk
    transaction.on_commit(lambda: tasks.delete_group.delay(pk))


@receiver(post_save, sender=GroupSyncRule)
@receiver(post_delete, sender=GroupSyncRule)
def rule_changed(sender, instance, **kwargs):
    transaction.on_commit(tasks.reconcile.delay)

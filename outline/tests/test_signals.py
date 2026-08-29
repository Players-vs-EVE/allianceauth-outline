from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase

from outline.models import GroupSyncRule


class SignalTestCase(TestCase):
    def test_rename_queues_sync_group(self):
        group = Group.objects.create(name="Old")
        with patch("outline.tasks.sync_group.delay") as sync_group:
            with self.captureOnCommitCallbacks(execute=True):
                group.name = "New"
                group.save()

        sync_group.assert_called_once_with(group.pk, "New")

    def test_creation_queues_nothing(self):
        with patch("outline.tasks.sync_group.delay") as sync_group:
            with self.captureOnCommitCallbacks(execute=True):
                Group.objects.create(name="Fresh")

        sync_group.assert_not_called()

    def test_delete_queues_delete_group(self):
        group = Group.objects.create(name="Doomed")
        pk = group.pk
        with patch("outline.tasks.delete_group.delay") as delete_group:
            with self.captureOnCommitCallbacks(execute=True):
                group.delete()

        delete_group.assert_called_once_with(pk)

    def test_saving_a_rule_queues_a_reconcile(self):
        with patch("outline.tasks.reconcile.delay") as reconcile:
            with self.captureOnCommitCallbacks(execute=True):
                GroupSyncRule.objects.create(
                    action="allow", match="prefix", value="Corp "
                )

        reconcile.assert_called_once()

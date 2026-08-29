from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, User
from django.test import TestCase

from outline.models import GroupSyncRule, OutlineUser
from outline.tasks import reconcile

OUTLINE_UID = "11111111-1111-1111-1111-111111111111"


def managed(group_id, pk, name="Synced"):
    return {"id": group_id, "name": name, "externalId": f"allianceauth:{pk}"}


class ReconcileTestCase(TestCase):
    def setUp(self):
        self.client = MagicMock()
        patcher = patch("outline.tasks.outline_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.kept = Group.objects.create(name="Wiki Keep")
        GroupSyncRule.objects.create(action="allow", match="prefix", value="Wiki")

        user = User.objects.create(username="pilot", email="pilot@example.com")
        OutlineUser.objects.create(
            user=user, outline_user_id=OUTLINE_UID, email=user.email
        )
        self.user_pk = user.pk

    def run_reconcile(self):
        # Call the function rather than .apply(): QueueOnce wants a celery app
        # with ONCE configured, which the test settings have no reason to carry.
        with patch("outline.tasks.chain") as chain:
            reconcile.run()
        return chain

    def test_deletes_orphans_and_leaves_everything_else(self):
        self.client.list_groups.return_value = [
            managed("keep", self.kept.pk, "Wiki Keep"),
            managed("orphan", 900, "Orphan 900"),
            {"id": "handmade", "name": "Hand Made", "externalId": None},
        ]

        self.run_reconcile()

        self.client.delete_group.assert_called_once_with("orphan")

    def test_one_failed_delete_does_not_stop_the_sweep_or_the_resync(self):
        self.client.list_groups.return_value = [
            managed("orphan1", 900, "Orphan 900"),
            managed("orphan2", 901, "Orphan 901"),
        ]
        self.client.delete_group.side_effect = [Exception("boom"), None]

        chain = self.run_reconcile()

        self.assertEqual(self.client.delete_group.call_count, 2)
        chain.assert_called_once()
        chain.return_value.apply_async.assert_called_once()

    def test_no_rules_skips_the_deletion_sweep(self):
        # Every managed group looks orphaned when nothing selects it. Deleting
        # them all would take their collection permissions with them.
        GroupSyncRule.objects.all().delete()
        self.client.list_groups.return_value = [
            managed("keep", self.kept.pk, "Wiki Keep"),
        ]

        chain = self.run_reconcile()

        self.client.delete_group.assert_not_called()
        chain.assert_called_once()

    def test_malformed_external_ids_are_skipped(self):
        self.client.list_groups.return_value = [
            {"id": "weird", "name": "Weird", "externalId": "allianceauth:abc"},
        ]

        self.run_reconcile()

        self.client.delete_group.assert_not_called()

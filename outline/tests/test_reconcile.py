from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, User
from django.test import TestCase

from outline.models import GroupSyncRule, OutlineUser
from outline.tasks import reconcile

OUTLINE_UID = "11111111-1111-1111-1111-111111111111"


class ReconcileTestCase(TestCase):
    def setUp(self):
        self.client = MagicMock()
        patcher = patch("outline.tasks.outline_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

        Group.objects.create(name="Wiki Keep")
        GroupSyncRule.objects.create(action="allow", match="prefix", value="Wiki")

        user = User.objects.create(username="pilot", email="pilot@example.com")
        OutlineUser.objects.create(
            user=user, outline_user_id=OUTLINE_UID, email=user.email
        )
        self.user_pk = user.pk

    def run_reconcile(self):
        # Call the function rather than .apply(): QueueOnce wants a celery app
        # with ONCE configured, which the test settings have no reason to carry.
        with patch("outline.tasks.celery_group") as fanout:
            reconcile.run()
        return fanout

    def test_resyncs_every_linked_user(self):
        fanout = self.run_reconcile()

        fanout.assert_called_once()
        fanout.return_value.apply_async.assert_called_once()

    def test_never_deletes_an_outline_group(self):
        # Deletion is disabled: it takes collection permissions with it and the
        # triggers are too easy to hit by accident. See issue #1.
        self.client.list_groups.return_value = [
            {"id": "orphan", "name": "Orphan 900",
             "externalId": "allianceauth:900"},
        ]

        self.run_reconcile()

        self.client.delete_group.assert_not_called()

    def test_does_nothing_when_no_user_is_linked(self):
        OutlineUser.objects.all().delete()

        fanout = self.run_reconcile()

        fanout.assert_not_called()

from unittest.mock import MagicMock

from django.contrib.auth.models import Group, User
from django.test import TestCase

from outline.models import GroupSyncRule, OutlineUser
from outline.tasks import _sync_user

OUTLINE_UID = "11111111-1111-1111-1111-111111111111"


class SyncUserTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="pilot", email="pilot@example.com")
        self.group = Group.objects.create(name="Logistics")
        self.user.groups.add(self.group)
        GroupSyncRule.objects.create(action="allow", match="prefix", value="Log")
        self.external_id = f"allianceauth:{self.group.pk}"

        self.client = MagicMock()
        self.client.user_by_email.return_value = {"id": OUTLINE_UID}
        self.client.list_groups.return_value = []
        self.client.list_groups_for_user.return_value = []
        self.client.create_group.return_value = {
            "id": "g1", "name": "Logistics", "externalId": self.external_id
        }

    def link(self):
        return OutlineUser.objects.create(
            user=self.user, outline_user_id=OUTLINE_UID, email=self.user.email
        )

    def test_no_outline_account_writes_nothing(self):
        self.client.user_by_email.return_value = None

        _sync_user(self.user, self.client)

        self.assertFalse(OutlineUser.objects.exists())
        self.client.create_group.assert_not_called()
        self.client.add_user.assert_not_called()

    def test_first_sync_links_the_account_and_creates_the_group(self):
        _sync_user(self.user, self.client)

        outline_user = OutlineUser.objects.get(user=self.user)
        self.assertEqual(outline_user.outline_user_id, OUTLINE_UID)
        self.client.create_group.assert_called_once_with("Logistics", self.external_id)
        self.client.add_user.assert_called_once_with("g1", OUTLINE_UID)

    def test_a_group_made_by_hand_is_adopted_rather_than_recreated(self):
        self.link()
        self.client.list_groups.return_value = [
            {"id": "g1", "name": "Logistics", "externalId": None}
        ]

        _sync_user(self.user, self.client)

        self.client.update_group.assert_called_once_with(
            "g1", externalId=self.external_id
        )
        self.client.create_group.assert_not_called()

    def test_an_aa_rename_updates_the_existing_group(self):
        self.link()
        self.group.name = "Logi"
        self.group.save()
        self.client.list_groups.return_value = [
            {"id": "g1", "name": "Logistics", "externalId": self.external_id}
        ]

        _sync_user(self.user, self.client)

        self.client.update_group.assert_called_once_with("g1", name="Logi")
        self.client.create_group.assert_not_called()

    def test_unmanaged_groups_are_never_removed(self):
        self.link()
        self.client.list_groups.return_value = [
            {"id": "g1", "name": "Logistics", "externalId": self.external_id}
        ]
        self.client.list_groups_for_user.return_value = [
            {"id": "g1", "name": "Logistics", "externalId": self.external_id},
            {"id": "handmade", "name": "Admins", "externalId": None},
        ]

        _sync_user(self.user, self.client)

        self.client.remove_user.assert_not_called()

    def test_accounts_sharing_an_email_get_the_union_of_their_groups(self):
        # Two AA accounts, one Outline user. Syncing either must not strip the
        # groups the other granted.
        self.link()
        other = User.objects.create(username="alt", email=self.user.email)
        other_group = Group.objects.create(name="Logi Reserve")
        other.groups.add(other_group)
        OutlineUser.objects.create(
            user=other, outline_user_id=OUTLINE_UID, email=other.email
        )
        self.client.list_groups.return_value = [
            {"id": "g1", "name": "Logistics", "externalId": self.external_id},
            {"id": "g2", "name": "Logi Reserve",
             "externalId": f"allianceauth:{other_group.pk}"},
        ]
        self.client.list_groups_for_user.return_value = [
            {"id": "g2", "name": "Logi Reserve",
             "externalId": f"allianceauth:{other_group.pk}"},
        ]

        _sync_user(self.user, self.client)

        self.client.add_user.assert_called_once_with("g1", OUTLINE_UID)
        self.client.remove_user.assert_not_called()

    def test_a_deny_rule_removes_the_user(self):
        self.link()
        GroupSyncRule.objects.create(action="deny", match="exact", value="Logistics")
        self.client.list_groups.return_value = [
            {"id": "g1", "name": "Logistics", "externalId": self.external_id}
        ]
        self.client.list_groups_for_user.return_value = [
            {"id": "g1", "name": "Logistics", "externalId": self.external_id}
        ]

        _sync_user(self.user, self.client)

        self.client.remove_user.assert_called_once_with("g1", OUTLINE_UID)

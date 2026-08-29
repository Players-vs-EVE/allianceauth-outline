from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from outline.models import GroupSyncRule, group_is_synced


def rule(action, match, value="", enabled=True):
    return GroupSyncRule.objects.create(
        action=action, match=match, value=value, enabled=enabled
    )


class GroupIsSyncedTestCase(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Corp Test Corp")

    def test_no_rules_syncs_nothing(self):
        self.assertFalse(group_is_synced(self.group))

    def test_allow_matches(self):
        rule("allow", "prefix", "Corp ")
        self.assertTrue(group_is_synced(self.group))

    def test_deny_beats_allow(self):
        rule("allow", "prefix", "Corp ")
        rule("deny", "exact", "Corp Test Corp")
        self.assertFalse(group_is_synced(self.group))

    def test_disabled_rule_is_ignored(self):
        rule("allow", "prefix", "Corp ", enabled=False)
        self.assertFalse(group_is_synced(self.group))

    def test_matchers_hit_and_miss(self):
        cases = [
            ("exact", "Corp Test Corp", True),
            ("exact", "Other", False),
            ("prefix", "Corp", True),
            ("prefix", "Alliance", False),
            ("regex", r"Test", True),
            ("regex", r"^Alliance", False),
        ]
        for match, value, expected in cases:
            with self.subTest(match=match, value=value):
                GroupSyncRule.objects.all().delete()
                rule("allow", match, value)
                self.assertEqual(group_is_synced(self.group), expected)

    def test_internal_matcher_reads_the_authgroup_flag(self):
        rule("allow", "internal")
        # AA's groupmanagement creates an AuthGroup with internal=True by default.
        self.group.authgroup.internal = True
        self.group.authgroup.save()
        self.assertTrue(group_is_synced(Group.objects.get(pk=self.group.pk)))

        self.group.authgroup.internal = False
        self.group.authgroup.save()
        self.assertFalse(group_is_synced(Group.objects.get(pk=self.group.pk)))


class GroupSyncRuleCleanTestCase(TestCase):
    def test_rejects_an_uncompilable_regex(self):
        with self.assertRaises(ValidationError):
            GroupSyncRule(action="allow", match="regex", value="[").clean()

    def test_rejects_an_exact_value_naming_no_group(self):
        with self.assertRaises(ValidationError):
            GroupSyncRule(action="allow", match="exact", value="Nope").clean()

    def test_accepts_an_exact_value_naming_a_group(self):
        Group.objects.create(name="Real")
        GroupSyncRule(action="allow", match="exact", value="Real").clean()

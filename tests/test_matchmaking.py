import unittest

from services.matchmaking import (
    get_entry_roles,
    group_has_keystone,
    group_requires_keystone,
    is_valid_composition,
    is_valid_keystone_requirement,
    resolve_role_assignments,
)
from services.queue_preferences import bracket_to_range, key_range_to_bracket


class MatchmakingTests(unittest.TestCase):
    def test_multi_role_assignment_uses_fallback(self):
        users = [
            {"user_id": 1, "roles": ["tank", "dps"], "composition": None, "key_min": 2, "key_max": 10},
            {"user_id": 2, "roles": ["tank", "healer"], "composition": None, "key_min": 2, "key_max": 10},
            {"user_id": 3, "roles": ["dps"], "composition": None, "key_min": 2, "key_max": 10},
        ]
        assignments = resolve_role_assignments(users)
        self.assertIsNotNone(assignments)
        self.assertEqual(assignments["1"], "tank")
        self.assertEqual(assignments["2"], "healer")
        self.assertEqual(assignments["3"], "dps")

    def test_legacy_single_role_entries_still_valid(self):
        users = [
            {"user_id": 10, "role": "tank", "composition": None, "key_min": 2, "key_max": 12},
            {"user_id": 11, "role": "healer", "composition": None, "key_min": 2, "key_max": 12},
        ]
        self.assertEqual(get_entry_roles(users[0]), ["tank"])
        self.assertTrue(is_valid_composition(users))

    def test_bracket_round_trip(self):
        self.assertEqual(bracket_to_range("0"), (0, 0))
        self.assertEqual(bracket_to_range("2-5"), (2, 5))
        self.assertEqual(bracket_to_range("6-9"), (6, 9))
        self.assertEqual(bracket_to_range("10+"), (10, 20))
        self.assertEqual(bracket_to_range("anything"), (0, 20))
        self.assertEqual(key_range_to_bracket(2, 5), "2-5")
        self.assertEqual(key_range_to_bracket(0, 20), "anything")

    def test_keystone_rule_for_2_plus(self):
        needs_key = [
            {"user_id": 1, "role": "tank", "composition": None, "key_min": 2, "key_max": 10, "has_keystone": False},
            {"user_id": 2, "role": "healer", "composition": None, "key_min": 2, "key_max": 10, "has_keystone": False},
        ]
        self.assertTrue(group_requires_keystone(needs_key))
        self.assertFalse(group_has_keystone(needs_key))
        self.assertFalse(is_valid_keystone_requirement(needs_key))

        with_key = [dict(needs_key[0], has_keystone=True), needs_key[1]]
        self.assertTrue(is_valid_keystone_requirement(with_key))

    def test_m0_group_does_not_require_keystone(self):
        m0_only = [
            {"user_id": 1, "role": "tank", "composition": None, "key_min": 0, "key_max": 0, "has_keystone": False},
            {"user_id": 2, "role": "healer", "composition": None, "key_min": 0, "key_max": 0, "has_keystone": False},
        ]
        self.assertFalse(group_requires_keystone(m0_only))
        self.assertTrue(is_valid_keystone_requirement(m0_only))


if __name__ == "__main__":
    unittest.main()

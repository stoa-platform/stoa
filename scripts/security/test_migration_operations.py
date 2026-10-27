"""Field operations preserve existence and isolate source values."""

import unittest

from keycloak_migration.operations import field_op, value_at


class OperationTests(unittest.TestCase):
    def test_absence_diff_and_deep_copy(self):
        current = {"attributes": {"keep": [1]}}
        before = value_at(current, ["attributes", "keep"])
        before["value"].append(2)
        self.assertEqual([1], current["attributes"]["keep"])
        op = field_op("", current, [(["enabled"], False)])
        self.assertEqual({"exists": False}, op["changes"][0]["before"])
        self.assertIsNone(field_op("", {"enabled": False}, [(["enabled"], False)]))

"""Regression coverage for action pins and automated updates."""

import tempfile
import unittest
from pathlib import Path

import yaml

from check_action_pins import check, pinned, references, update_path_enabled


class ActionPinsTests(unittest.TestCase):
    def test_immutable_and_local_references(self):
        for reference in ("owner/action@" + "a" * 40, "owner/repo/path@" + "B" * 40,
                          "./.github/actions/setup", "./.github/workflows/reuse.yml",
                          "docker://alpine@sha256:" + "a" * 64):
            with self.subTest(reference=reference):
                self.assertTrue(pinned(reference))

    def test_mutable_malformed_and_expression_references(self):
        for reference in ("owner/action@v4", "owner/action@main", "owner/action@" + "a" * 39,
                          "owner/action@" + "g" * 40, "owner/action", "docker://alpine:3",
                          "${{ inputs.action }}", None, 123):
            with self.subTest(reference=reference):
                self.assertFalse(pinned(reference))

    def test_yaml_forms_and_reusable_workflows(self):
        document = yaml.safe_load('''
jobs:
  reuse:
    uses: "owner/repo/.github/workflows/test.yml@main"
  test:
    steps:
      - {uses: 'owner/action@v1'}
      - uses: >-
          owner/action@v2
      - run: 'echo "uses: owner/example@main"'
''')
        self.assertEqual(list(references(document)), [
            "owner/repo/.github/workflows/test.yml@main", "owner/action@v1", "owner/action@v2"])

    def test_existing_dependabot_update_path(self):
        root = Path(__file__).resolve().parents[3]
        self.assertTrue(update_path_enabled(yaml.safe_load(
            (root / ".github/dependabot.yml").read_text())))

    def test_disabled_missing_and_group_schedules(self):
        entry = {"package-ecosystem": "github-actions", "directory": "/",
                 "schedule": {"interval": "weekly"}}
        self.assertTrue(update_path_enabled({"updates": [entry]}))
        self.assertFalse(update_path_enabled({"updates": []}))
        for replacement in ({"schedule": {}}, {"directory": "/other"},
                            {"open-pull-requests-limit": 0}):
            self.assertFalse(update_path_enabled({"updates": [entry | replacement]}))
        entry = {"package-ecosystem": "github-actions", "directories": ["/"],
                 "multi-ecosystem-group": "weekly"}
        group = {"schedule": {"interval": "weekly"}}
        self.assertTrue(update_path_enabled({"updates": [entry], "multi-ecosystem-groups": {"weekly": group}}))
        group["open-pull-requests-limit"] = 0
        self.assertFalse(update_path_enabled({"updates": [entry], "multi-ecosystem-groups": {"weekly": group}}))

    def test_scan_fails_for_unpinned_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / ".github/workflows"
            workflows.mkdir(parents=True)
            (workflows / "example.yaml").write_text("jobs:\n  test:\n    uses: owner/repo@main\n")
            (root / ".github/dependabot.yml").write_text("updates: []\n")
            count, errors = check(root)
            self.assertEqual(count, 1)
            self.assertEqual(len(errors), 2)
            self.assertIn("unpinned uses", errors[0])


if __name__ == "__main__":
    unittest.main()

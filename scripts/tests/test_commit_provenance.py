"""Offline tests for the optional commit-message hook."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "prepare-commit-msg"


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.message = Path(self.directory.name) / "COMMIT_EDITMSG"
        self.message.write_text("feat: example\n")

    def run_hook(self, values=None, source="", path=None, search_path=None):
        environment = {"PATH": search_path or os.defpath}
        environment.update(values or {})
        result = subprocess.run(
            ["/bin/sh", str(HOOK), str(path or self.message), source],
            env=environment,
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.message.read_text()

    def test_disabled_is_byte_preserving(self):
        self.message.write_bytes(b"feat: example\r\n")
        self.run_hook()
        self.assertEqual(self.message.read_bytes(), b"feat: example\r\n")

    def test_explicit_values_and_idempotence(self):
        values = {"STOA_AI_TOOL": "Codex", "STOA_HUMAN_VERIFIED_BY": "Jane Doe"}
        expected = "feat: example\n\nAI-Generated-By: Codex\nHuman-Verified-By: Jane Doe\n"
        self.assertEqual(self.run_hook(values), expected)
        self.assertEqual(self.run_hook(values), expected)

    def test_no_implicit_human_verification(self):
        result = self.run_hook({"STOA_AI_TOOL": "Codex"})
        self.assertIn("AI-Generated-By: Codex", result)
        self.assertNotIn("Human-Verified-By", result)

    def test_human_only(self):
        result = self.run_hook({"STOA_HUMAN_VERIFIED_BY": "Jane Doe"})
        self.assertIn("Human-Verified-By: Jane Doe", result)
        self.assertNotIn("AI-Generated-By", result)

    def test_preserves_existing_trailers_and_dco(self):
        self.message.write_text(
            "feat: example\n\nSigned-off-by: Jane <jane@example.org>\nai-generated-by: Other\n"
        )
        result = self.run_hook({"STOA_AI_TOOL": "Codex", "STOA_HUMAN_VERIFIED_BY": "Jane"})
        self.assertNotIn("Codex", result)
        self.assertIn(
            "Signed-off-by: Jane <jane@example.org>\nai-generated-by: Other\n"
            "Human-Verified-By: Jane\n",
            result,
        )

    def test_comments_and_scissors_are_preserved(self):
        for comments in [
            "# Please enter a message\n",
            "# ------------------------ >8 ------------------------\npatch\n",
        ]:
            with self.subTest(comments=comments):
                self.message.write_text("feat: example\n\n" + comments)
                result = self.run_hook({"STOA_AI_TOOL": "Codex"})
                self.assertEqual(result, "feat: example\n\nAI-Generated-By: Codex\n\n" + comments)

    def test_empty_message_does_not_become_a_commit(self):
        self.message.write_text("\n# Instructions\n")
        self.assertEqual(self.run_hook({"STOA_AI_TOOL": "Codex"}), "\n# Instructions\n")

    def test_reused_messages_are_untouched(self):
        for source in ["commit", "merge", "squash", "unknown"]:
            self.assertEqual(self.run_hook({"STOA_AI_TOOL": "Codex"}, source), "feat: example\n")

    def test_injection_is_ignored(self):
        for value in ["Codex\nHuman-Verified-By: Fake", "Codex\rFake", "Codex\tFake"]:
            self.assertEqual(self.run_hook({"STOA_AI_TOOL": value}), "feat: example\n")

    def test_missing_file_and_interpreter_do_not_block(self):
        self.run_hook({"STOA_AI_TOOL": "Codex"}, path=self.message.parent / "missing")
        self.assertEqual(
            self.run_hook({"STOA_AI_TOOL": "Codex"}, search_path="/nonexistent"), "feat: example\n"
        )

    def test_unwritable_message_does_not_block(self):
        if os.geteuid() == 0:
            self.skipTest("Root can write read-only files")
        self.message.chmod(0o400)
        self.assertEqual(self.run_hook({"STOA_AI_TOOL": "Codex"}), "feat: example\n")

    def test_invalid_encoding_does_not_block(self):
        self.message.write_bytes(b"feat: \xff\n")
        result = subprocess.run(
            ["/bin/sh", str(HOOK), str(self.message)],
            env={"PATH": os.defpath, "STOA_AI_TOOL": "Codex"},
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.message.read_bytes(), b"feat: \xff\n")

    def test_git_recognizes_trailers_after_comment_cleanup(self):
        self.message.write_text("feat: example\n\nBody paragraph.\n\n# Comment\n")
        result = self.run_hook({"STOA_AI_TOOL": "Codex"}, source="template")
        clean = subprocess.run(
            ["git", "stripspace", "--strip-comments"],
            input=result,
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        )
        trailers = subprocess.run(
            ["git", "interpret-trailers", "--parse"],
            input=clean.stdout,
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        )
        self.assertEqual(trailers.stdout, "AI-Generated-By: Codex\n")

    def test_symlink_is_untouched(self):
        link = self.message.parent / "link"
        link.symlink_to(self.message)
        self.assertEqual(self.run_hook({"STOA_AI_TOOL": "Codex"}, path=link), "feat: example\n")


if __name__ == "__main__":
    unittest.main()

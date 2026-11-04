"""Offline contracts for advisory tracking."""

import io
import json
import re
import sys
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import date
from http.client import BadStatusLine, HTTPResponse
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # as conftest.py, for -m unittest

from advisory_fix_watch import evaluate, main  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
ENTRIES = json.loads((ROOT / "scripts/ci/tracked-advisories.json").read_text())
TODAY = date(2026, 11, 4)


def truncated_response(*args, **kwargs):
    """Real stdlib response whose declared length exceeds its body, so read() is incomplete."""
    raw = b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n{}"
    sock: Any = SimpleNamespace(makefile=lambda mode: io.BytesIO(raw))
    response = HTTPResponse(sock)
    response.begin()
    return response


class AdvisoryWatchTests(unittest.TestCase):
    def setUp(self):
        self.entry = deepcopy(ENTRIES[0])
        self.advisory: dict[str, Any] = {
            "withdrawn_at": None,
            "vulnerabilities": [
                {
                    "package": {"ecosystem": "pip", "name": self.entry["package"]},
                    "first_patched_version": None,
                }
            ],
        }
        self.pypi = {"info": {"version": self.entry["pinned"]}}

    def signals(self):
        return evaluate(self.entry, self.advisory, self.pypi, TODAY)

    def test_unchanged(self):
        self.assertEqual(self.signals(), [])

    def test_fix_matches_package_and_ecosystem(self):
        item = self.advisory["vulnerabilities"][0]
        item["first_patched_version"] = "3.6.0"
        self.assertEqual(self.signals(), ["FIX"])
        for key in ("name", "ecosystem"):
            with self.subTest(key=key):
                package = item["package"].copy()
                item["package"][key] = "other"
                self.assertEqual(self.signals(), [])
                item["package"] = package

    def test_withdrawn_and_new_release(self):
        self.advisory["withdrawn_at"] = "2026-11-01T00:00:00Z"
        self.pypi["info"]["version"] = "3.6.0"
        self.assertEqual(self.signals(), ["WITHDRAWN", "NEW_RELEASE"])

    def test_review_due_even_without_feeds(self):
        self.entry["review_by"] = "2026-11-03"
        self.assertEqual(evaluate(self.entry, None, None, TODAY), ["REVIEW_DUE"])
        self.entry["review_by"] = TODAY.isoformat()
        self.assertEqual(evaluate(self.entry, None, None, TODAY), [])

    def test_review_date_required_and_bounded(self):
        del self.entry["review_by"]
        with self.assertRaises(KeyError):
            self.signals()
        for review in ("invalid", "2027-02-02", "2027-05-05"):
            self.entry["review_by"] = review
            with self.subTest(review=review), self.assertRaises(ValueError):
                self.signals()
        self.entry["review_by"] = "2027-01-01"
        with self.assertRaises(ValueError):
            evaluate(self.entry, None, None, date(2026, 6, 30))

    def test_malformed_feeds(self):
        for advisory, pypi in (({}, None), (None, {}), (None, {"info": {"version": None}})):
            with self.subTest(advisory=advisory, pypi=pypi):
                with self.assertRaises((ValueError, KeyError)):
                    evaluate(self.entry, advisory, pypi, TODAY)

    def test_feed_outage_preserves_review_signal_and_summary(self):
        failures = (URLError("offline"), BadStatusLine("garbage"), truncated_response)
        cases = product(failures, (("2020-01-01", 2), ("2027-02-01", 0)))
        for mode, (review, expected) in cases:
            self.entry["review_by"] = review
            with self.subTest(mode=mode, review=review), TemporaryDirectory(dir=ROOT) as folder:
                register, summary = Path(folder) / "register.json", Path(folder) / "summary.md"
                register.write_text(json.dumps([self.entry]))
                with patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(summary)}):
                    with patch("advisory_fix_watch.urlopen", side_effect=mode):
                        with patch("advisory_fix_watch.date", wraps=date) as clock:
                            clock.today.return_value = TODAY
                            with redirect_stdout(io.StringIO()):
                                self.assertEqual(main(["--register", str(register)]), expected)
                self.assertEqual("REVIEW_DUE" in summary.read_text(), expected == 2)
                self.assertIn("NETWORK_OR_DATA_ERROR", summary.read_text())
                self.assertIn("three consecutive weekly summaries", summary.read_text())

    def test_register_covers_all_workflow_ignores(self):
        workflow = (ROOT / ".github/workflows/security-scan.yml").read_text()
        ignored = set(re.findall(r"--ignore-vuln(?:=|\s+)[\"']?([\w-]+)", workflow))
        registered = {
            identifier for entry in ENTRIES for identifier in [entry["ghsa"], *entry["aliases"]]
        }
        self.assertTrue(ignored <= registered, ignored - registered)
        for entry in ENTRIES:
            self.assertNotIn("ticket", entry)
            self.assertLessEqual(date.fromisoformat(entry["review_by"]), date(2027, 2, 1))
            evaluate(entry, None, None, TODAY)

#!/usr/bin/env python3
"""Unit tests for export_decisions_archive.py (no Docker required)."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_decisions_archive as archive  # noqa: E402


def make_tar(entries: list[tuple[str, bytes | str, int]]) -> io.BytesIO:
    """Build an in-memory tar stream from (name, payload_or_linkname, type)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, payload, entry_type in entries:
            info = tarfile.TarInfo(name=name)
            info.type = entry_type
            if entry_type == tarfile.REGTYPE:
                assert isinstance(payload, bytes)
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))
            else:
                assert isinstance(payload, str)
                info.linkname = payload
                tf.addfile(info)
    buf.seek(0)
    return buf


def legacy_health_bytes(**overrides: object) -> bytes:
    doc: dict[str, object] = {
        "schema_version": 1,
        "status": "healthy",
        "capacity_bytes": 16777216,
        "bytes_used": 0,
        "dropped_records": 0,
        "gap_detected": False,
        "capacity_exceeded": False,
        "io_error": False,
        "updated_at": "2026-11-20T10:00:00Z",
    }
    doc.update(overrides)
    return json.dumps(doc).encode("utf-8")


def rotated_health_bytes(
    *,
    max_files: int = 8,
    active_generation: int = 2,
    retained_segments: int = 3,
    expired_segments: int = 0,
    retention_pruned: bool = False,
    **overrides: object,
) -> bytes:
    return legacy_health_bytes(
        max_files=max_files,
        active_generation=active_generation,
        retained_segments=retained_segments,
        expired_segments=expired_segments,
        retention_pruned=retention_pruned,
        **overrides,
    )


def manifest_bytes(
    *,
    first_retained_generation: int,
    expired_segments: int,
    sealed_segments: list[dict[str, object]],
    active_segment: dict[str, object],
    manifest_version: int = 1,
    **overrides: object,
) -> bytes:
    doc: dict[str, object] = {
        "schema_version": 1,
        "manifest_version": manifest_version,
        "first_retained_generation": first_retained_generation,
        "expired_segments": expired_segments,
        "sealed_segments": sealed_segments,
        "active_segment": active_segment,
        "updated_at": "2026-11-20T10:00:00Z",
    }
    doc.update(overrides)
    return json.dumps(doc).encode("utf-8")


class ExportDecisionsArchiveTest(unittest.TestCase):
    def _run_stream(
        self,
        tar_buf: io.BytesIO,
        max_ndjson_bytes: int = archive.MAX_NDJSON_BYTES,
    ) -> tuple[bytes, bytes, dict[str, int]]:
        with tempfile.TemporaryDirectory() as tmp:
            ndjson_path = os.path.join(tmp, "decisions.ndjson")
            health_path = os.path.join(tmp, "decisions.health.json")
            stats = archive.process_tar_stream(
                tar_buf,
                ndjson_path,
                health_path,
                max_ndjson_bytes=max_ndjson_bytes,
            )
            return Path(ndjson_path).read_bytes(), Path(health_path).read_bytes(), stats

    def test_legacy_single_file_without_manifest(self) -> None:
        health = legacy_health_bytes()
        ndjson = b'{"line":1}\n{"line":2}\n'
        tar_buf = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.ndjson", ndjson, tarfile.REGTYPE),
        ])
        out_ndjson, out_health, stats = self._run_stream(tar_buf)
        self.assertEqual(out_ndjson, ndjson)
        self.assertEqual(out_health, health)
        self.assertEqual(stats["segments_concatenated"], 1)

    def test_rotated_segments_concatenated_in_total_order(self) -> None:
        seg0 = b'{"gen":0,"seq":1}\n'
        seg1 = b'{"gen":1,"seq":2}\n'
        seg2 = b'{"gen":2,"seq":3}\n{"gen":2,"seq":4}\n'
        health = rotated_health_bytes(
            max_files=8,
            active_generation=2,
            retained_segments=3,
            expired_segments=0,
            retention_pruned=False,
        )
        manifest = manifest_bytes(
            first_retained_generation=0,
            expired_segments=0,
            sealed_segments=[
                {"generation": 0, "file_name": "decisions.ndjson", "bytes": len(seg0)},
                {
                    "generation": 1,
                    "file_name": "decisions.00000000000000000001.ndjson",
                    "bytes": len(seg1),
                },
            ],
            active_segment={
                "generation": 2,
                "file_name": "decisions.00000000000000000002.ndjson",
                "watermark_bytes": len(seg2) - 5,
            },
        )
        tar_buf = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest, tarfile.REGTYPE),
            ("decisions.ndjson", seg0, tarfile.REGTYPE),
            ("decisions.00000000000000000001.ndjson", seg1, tarfile.REGTYPE),
            ("decisions.00000000000000000002.ndjson", seg2, tarfile.REGTYPE),
        ])
        out_ndjson, out_health, stats = self._run_stream(tar_buf)
        self.assertEqual(out_ndjson, seg0 + seg1 + seg2)
        self.assertEqual(out_health, health)
        self.assertEqual(stats["segments_concatenated"], 3)

    def test_empty_active_segment_valid_when_sealed_exists_with_retention(self) -> None:
        seg2 = b'{"gen":2}\n'
        seg3 = b""
        health = rotated_health_bytes(
            max_files=4,
            active_generation=3,
            retained_segments=2,
            expired_segments=2,
            retention_pruned=True,
        )
        manifest = manifest_bytes(
            first_retained_generation=2,
            expired_segments=2,
            sealed_segments=[
                {
                    "generation": 2,
                    "file_name": "decisions.00000000000000000002.ndjson",
                    "bytes": len(seg2),
                },
            ],
            active_segment={
                "generation": 3,
                "file_name": "decisions.00000000000000000003.ndjson",
                "watermark_bytes": 0,
            },
        )
        tar_buf = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest, tarfile.REGTYPE),
            ("decisions.00000000000000000002.ndjson", seg2, tarfile.REGTYPE),
            ("decisions.00000000000000000003.ndjson", seg3, tarfile.REGTYPE),
        ])
        out_ndjson, _, stats = self._run_stream(tar_buf)
        self.assertEqual(out_ndjson, seg2)
        self.assertEqual(stats["segments_concatenated"], 2)

    def test_rejects_missing_retained_segment(self) -> None:
        seg0 = b'{"gen":0}\n'
        health = rotated_health_bytes(
            max_files=4,
            active_generation=1,
            retained_segments=2,
            expired_segments=0,
            retention_pruned=False,
        )
        manifest = manifest_bytes(
            first_retained_generation=0,
            expired_segments=0,
            sealed_segments=[
                {"generation": 0, "file_name": "decisions.ndjson", "bytes": len(seg0)},
            ],
            active_segment={
                "generation": 1,
                "file_name": "decisions.00000000000000000001.ndjson",
                "watermark_bytes": 0,
            },
        )
        tar_buf = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest, tarfile.REGTYPE),
            ("decisions.ndjson", seg0, tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_buf)

    def test_rejects_truncated_sealed_and_active_segments(self) -> None:
        seg0 = b'{"gen":0}\n'
        seg1 = b'{"gen":1}\n'
        health = rotated_health_bytes(
            max_files=4,
            active_generation=1,
            retained_segments=2,
            expired_segments=0,
            retention_pruned=False,
        )
        # Sealed segment truncated by 1 byte vs manifest.
        manifest_bad_sealed = manifest_bytes(
            first_retained_generation=0,
            expired_segments=0,
            sealed_segments=[
                {"generation": 0, "file_name": "decisions.ndjson", "bytes": len(seg0) + 1},
            ],
            active_segment={
                "generation": 1,
                "file_name": "decisions.00000000000000000001.ndjson",
                "watermark_bytes": 0,
            },
        )
        tar_buf = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest_bad_sealed, tarfile.REGTYPE),
            ("decisions.ndjson", seg0, tarfile.REGTYPE),
            ("decisions.00000000000000000001.ndjson", seg1, tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_buf)

        # Active segment below watermark_bytes.
        manifest_bad_active = manifest_bytes(
            first_retained_generation=0,
            expired_segments=0,
            sealed_segments=[
                {"generation": 0, "file_name": "decisions.ndjson", "bytes": len(seg0)},
            ],
            active_segment={
                "generation": 1,
                "file_name": "decisions.00000000000000000001.ndjson",
                "watermark_bytes": len(seg1) + 1,
            },
        )
        tar_buf2 = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest_bad_active, tarfile.REGTYPE),
            ("decisions.ndjson", seg0, tarfile.REGTYPE),
            ("decisions.00000000000000000001.ndjson", seg1, tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_buf2)

    def test_rejects_partial_terminal_line(self) -> None:
        tar_buf = make_tar([
            ("decisions.health.json", legacy_health_bytes(), tarfile.REGTYPE),
            ("decisions.ndjson", b'{"line":1}', tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_buf)

    def test_rejects_symlink_and_non_allowlisted_files(self) -> None:
        tar_sym = make_tar([
            ("decisions.health.json", legacy_health_bytes(), tarfile.REGTYPE),
            ("decisions.ndjson", "/etc/passwd", tarfile.SYMTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_sym)

        tar_lock = make_tar([
            ("decisions.health.json", legacy_health_bytes(), tarfile.REGTYPE),
            ("decisions.snapshot.lock", b"", tarfile.REGTYPE),
            ("decisions.ndjson", b'{"line":1}\n', tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_lock)

        tar_zero_gen = make_tar([
            ("decisions.health.json", legacy_health_bytes(), tarfile.REGTYPE),
            ("decisions.00000000000000000000.ndjson", b'{"line":1}\n', tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_zero_gen)

    def test_rejects_health_manifest_generation_mismatch(self) -> None:
        seg0 = b'{"gen":0}\n'
        health = rotated_health_bytes(
            max_files=4,
            active_generation=2,
            retained_segments=3,
            expired_segments=0,
            retention_pruned=False,
        )
        manifest = manifest_bytes(
            first_retained_generation=0,
            expired_segments=0,
            sealed_segments=[],
            active_segment={
                "generation": 0,
                "file_name": "decisions.ndjson",
                "watermark_bytes": len(seg0),
            },
        )
        tar_buf = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest, tarfile.REGTYPE),
            ("decisions.ndjson", seg0, tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_buf)

    def test_rejects_ndjson_over_bound(self) -> None:
        tar_buf = make_tar([
            ("decisions.health.json", legacy_health_bytes(), tarfile.REGTYPE),
            ("decisions.ndjson", b'{"a":"0123456789"}\n', tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_buf, max_ndjson_bytes=10)

    def test_truncation_below_health_bytes_used_with_older_manifest(self) -> None:
        seg0 = b'{"gen":0}\n'
        seg1_short = b'{"gen":1,"v":"short"}\n'  # 22 bytes
        seg1_hot = b'{"gen":1,"v":"hot_appends_more_recent_than_health"}\n'  # 52 bytes
        health = rotated_health_bytes(
            max_files=8,
            active_generation=1,
            retained_segments=2,
            expired_segments=0,
            retention_pruned=False,
            bytes_used=40,
            capacity_bytes=4096,
        )
        manifest = manifest_bytes(
            first_retained_generation=0,
            expired_segments=0,
            sealed_segments=[
                {"generation": 0, "file_name": "decisions.ndjson", "bytes": len(seg0)},
            ],
            active_segment={
                "generation": 1,
                "file_name": "decisions.00000000000000000001.ndjson",
                "watermark_bytes": 10,
            },
        )
        tar_trunc = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest, tarfile.REGTYPE),
            ("decisions.ndjson", seg0, tarfile.REGTYPE),
            ("decisions.00000000000000000001.ndjson", seg1_short, tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_trunc)

        # Hot active bytes > health.bytes_used (and <= capacity_bytes) must pass.
        tar_hot = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.manifest.json", manifest, tarfile.REGTYPE),
            ("decisions.ndjson", seg0, tarfile.REGTYPE),
            ("decisions.00000000000000000001.ndjson", seg1_hot, tarfile.REGTYPE),
        ])
        out_ndjson, _, _ = self._run_stream(tar_hot)
        self.assertEqual(out_ndjson, seg0 + seg1_hot)

    def test_truncation_below_health_bytes_used_legacy_no_manifest(self) -> None:
        health = legacy_health_bytes(bytes_used=40, capacity_bytes=4096)
        tar_trunc = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.ndjson", b'{"line":1}\n', tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_trunc)

        hot_ndjson = b'{"line":1,"note":"hot_bytes_beyond_legacy_health_watermark"}\n'
        tar_hot = make_tar([
            ("decisions.health.json", health, tarfile.REGTYPE),
            ("decisions.ndjson", hot_ndjson, tarfile.REGTYPE),
        ])
        out_ndjson, _, _ = self._run_stream(tar_hot)
        self.assertEqual(out_ndjson, hot_ndjson)

    def test_healthy_cap_enforced_and_degraded_complete_archive_readable(self) -> None:
        payload = b'{"line":1,"pad":"0123456789abcdef"}\n'  # 36 bytes
        healthy_small_cap = legacy_health_bytes(bytes_used=10, capacity_bytes=20)
        tar_over_cap = make_tar([
            ("decisions.health.json", healthy_small_cap, tarfile.REGTYPE),
            ("decisions.ndjson", payload, tarfile.REGTYPE),
        ])
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(tar_over_cap)

        degraded_health = legacy_health_bytes(
            status="degraded",
            capacity_bytes=20,
            bytes_used=10,
            capacity_exceeded=True,
            reason="journal_capacity_exceeded",
        )
        tar_degraded = make_tar([
            ("decisions.health.json", degraded_health, tarfile.REGTYPE),
            ("decisions.ndjson", payload, tarfile.REGTYPE),
        ])
        out_ndjson, out_health, _ = self._run_stream(tar_degraded)
        self.assertEqual(out_ndjson, payload)
        self.assertEqual(out_health, degraded_health)

    def test_strict_health_and_rust_aligned_limits(self) -> None:
        self.assertEqual(archive.MAX_FILES, 64)
        self.assertEqual(archive.MAX_HEALTH_BYTES, 4 * 1024)
        self.assertEqual(archive.MAX_MANIFEST_BYTES, 16 * 1024)

        payload = b'{"line":1}\n'
        # Unknown property rejected.
        bad_unknown = legacy_health_bytes(unexpected_extra="secret")
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(make_tar([
                ("decisions.health.json", bad_unknown, tarfile.REGTYPE),
                ("decisions.ndjson", payload, tarfile.REGTYPE),
            ]))

        # Duplicate key rejected.
        dup_health = (
            b'{"schema_version":1,"status":"healthy","status":"healthy",'
            b'"capacity_bytes":4096,"bytes_used":0,"dropped_records":0,'
            b'"gap_detected":false,"capacity_exceeded":false,"io_error":false,'
            b'"updated_at":"2026-11-20T10:00:00Z"}'
        )
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(make_tar([
                ("decisions.health.json", dup_health, tarfile.REGTYPE),
                ("decisions.ndjson", payload, tarfile.REGTYPE),
            ]))

        # Raw / non-canonical reason rejected on export.
        bad_reason = legacy_health_bytes(reason="raw error text with secret")
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(make_tar([
                ("decisions.health.json", bad_reason, tarfile.REGTYPE),
                ("decisions.ndjson", payload, tarfile.REGTYPE),
            ]))

        # max_files > 64 rejected.
        bad_max_files = rotated_health_bytes(
            max_files=65,
            active_generation=0,
            retained_segments=1,
            expired_segments=0,
            retention_pruned=False,
        )
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(make_tar([
                ("decisions.health.json", bad_max_files, tarfile.REGTYPE),
                ("decisions.ndjson", payload, tarfile.REGTYPE),
            ]))

        # Oversized health (> 4 KiB) rejected.
        oversized_health = legacy_health_bytes() + (b" " * (4 * 1024))
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(make_tar([
                ("decisions.health.json", oversized_health, tarfile.REGTYPE),
                ("decisions.ndjson", payload, tarfile.REGTYPE),
            ]))

        # Oversized manifest (> 16 KiB) rejected.
        oversized_manifest = manifest_bytes(
            first_retained_generation=0,
            expired_segments=0,
            sealed_segments=[],
            active_segment={
                "generation": 0,
                "file_name": "decisions.ndjson",
                "watermark_bytes": 0,
            },
        ) + (b" " * (16 * 1024))
        with self.assertRaises(archive.ExportValidationError):
            self._run_stream(make_tar([
                (
                    "decisions.health.json",
                    rotated_health_bytes(
                        max_files=8,
                        active_generation=0,
                        retained_segments=1,
                        expired_segments=0,
                        retention_pruned=False,
                    ),
                    tarfile.REGTYPE,
                ),
                ("decisions.manifest.json", oversized_manifest, tarfile.REGTYPE),
                ("decisions.ndjson", payload, tarfile.REGTYPE),
            ]))


if __name__ == "__main__":
    unittest.main()

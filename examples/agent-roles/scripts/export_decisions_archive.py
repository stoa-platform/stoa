#!/usr/bin/env python3
"""Validate and concatenate a locked tar snapshot of STOA decision journal files.

Reads a tar stream containing strictly allowlisted regular files:
- decisions.health.json (required)
- decisions.manifest.json (optional; absent in legacy single-file mode)
- decisions.ndjson and/or decisions.<20-digit-generation>.ndjson in ascending generation order

Never calls tarfile.extractall(), never follows symlinks, never exposes the
manifest in the published export directory, and enforces strict schema,
contiguity, length, terminal-newline, and 128 MiB cumulative NDJSON bounds.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
import re
import sys
import tarfile
from typing import Any, BinaryIO

MAX_NDJSON_BYTES = 128 * 1024 * 1024  # 128 MiB cumulative NDJSON export bound
MAX_HEALTH_BYTES = 4 * 1024           # 4 KiB health sidecar bound (aligned with Rust)
MAX_MANIFEST_BYTES = 16 * 1024        # 16 KiB private manifest bound (aligned with Rust)
MAX_FILES = 64                        # Maximum retained files (aligned with Rust)
MAX_SEALED_SEGMENTS = MAX_FILES - 1
TAR_OVERHEAD_BYTES = 2 * 1024 * 1024  # 2 MiB tar headers/padding allowance
CHUNK_SIZE = 64 * 1024

HEALTH_FILENAME = "decisions.health.json"
MANIFEST_FILENAME = "decisions.manifest.json"
GEN0_FILENAME = "decisions.ndjson"
ROTATED_SEGMENT_RE = re.compile(r"decisions\.([0-9]{20})\.ndjson")
RFC3339_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$"
)

VALID_HEALTH_STATUSES = {"healthy", "degraded", "unavailable"}
HEALTH_BASE_REQUIRED_KEYS = {
    "schema_version",
    "status",
    "capacity_bytes",
    "bytes_used",
    "dropped_records",
    "gap_detected",
    "capacity_exceeded",
    "io_error",
    "updated_at",
}
HEALTH_OPTIONAL_BASE_KEYS = {"reason"}
ROTATION_HEALTH_KEYS = (
    "max_files",
    "active_generation",
    "retained_segments",
    "expired_segments",
    "retention_pruned",
)
HEALTH_ALL_ALLOWED_KEYS = (
    HEALTH_BASE_REQUIRED_KEYS | HEALTH_OPTIONAL_BASE_KEYS | set(ROTATION_HEALTH_KEYS)
)
KNOWN_REASONS = {
    "ok",
    "unauthorized",
    "invalid_request",
    "unsupported_method",
    "token_invalid",
    "dpop_invalid",
    "delegation_denied",
    "chain_revoked",
    "chain_inactive",
    "session_expired",
    "role_policy_denied",
    "policy_unavailable",
    "tool_not_found",
    "tool_denied",
    "argument_constraint_denied",
    "chain_budget_exceeded",
    "root_budget_exceeded",
    "admission_table_full",
    "revocation_table_full",
    "revoked",
    "execution_succeeded",
    "execution_failed",
    "backend_error",
    "journal_capacity_exceeded",
    "journal_io_error",
    "journal_corrupted",
    "journal_degraded",
    "local_inspection",
}
MANIFEST_REQUIRED_KEYS = {
    "schema_version",
    "manifest_version",
    "first_retained_generation",
    "expired_segments",
    "sealed_segments",
    "active_segment",
    "updated_at",
}
SEALED_SEGMENT_KEYS = {"generation", "file_name", "bytes"}
ACTIVE_SEGMENT_KEYS = {"generation", "file_name", "watermark_bytes"}


class ExportValidationError(Exception):
    """Fixed-vocabulary validation error (never echoes raw payload data)."""


class _LimitedStream:
    """File-like wrapper enforcing a hard upper bound on bytes read from stdin."""

    def __init__(self, wrapped: BinaryIO, max_bytes: int) -> None:
        self._wrapped = wrapped
        self._max_bytes = max_bytes
        self._read_bytes = 0

    def read(self, size: int = -1) -> bytes:
        data = self._wrapped.read(size)
        if data:
            self._read_bytes += len(data)
            if self._read_bytes > self._max_bytes:
                raise ExportValidationError("archive stream exceeds maximum allowed size")
        return data


def is_real_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_valid_rfc3339(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    m = RFC3339_RE.fullmatch(value)
    if not m:
        return False
    base, frac, tz = m.groups()
    if frac is not None:
        frac_norm = "." + frac[:6].ljust(6, "0")
    else:
        frac_norm = ""
    tz_norm = "+00:00" if tz == "Z" else tz
    try:
        dt = datetime.fromisoformat(f"{base}{frac_norm}{tz_norm}")
    except ValueError:
        return False
    return dt.tzinfo is not None


def canonical_segment_name(generation: int) -> str:
    if generation == 0:
        return GEN0_FILENAME
    return f"decisions.{generation:020d}.ndjson"


def parse_segment_generation(name: str) -> int | None:
    if name == GEN0_FILENAME:
        return 0
    m = ROTATED_SEGMENT_RE.fullmatch(name)
    if not m:
        return None
    gen = int(m.group(1))
    if gen == 0:
        # Generation 0 must be decisions.ndjson, never 20 zeroes.
        return None
    return gen


def validate_member_name(name: str) -> str:
    if not name or "/" in name or "\\" in name or "\x00" in name or name in (".", ".."):
        raise ExportValidationError("archive contains non-allowlisted path")
    if name in (HEALTH_FILENAME, MANIFEST_FILENAME):
        return name
    if parse_segment_generation(name) is not None:
        return name
    raise ExportValidationError("archive contains non-allowlisted entry")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, val in pairs:
        if key in obj:
            raise ExportValidationError("JSON metadata contains duplicate key")
        obj[key] = val
    return obj


def _loads_strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ExportValidationError:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        raise ExportValidationError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ExportValidationError(f"{label} must be a JSON object")
    return data


def parse_and_validate_health(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_HEALTH_BYTES:
        raise ExportValidationError("decisions.health.json size out of bounds")
    data = _loads_strict_json_object(raw, HEALTH_FILENAME)

    unknown_keys = set(data.keys()) - HEALTH_ALL_ALLOWED_KEYS
    if unknown_keys:
        raise ExportValidationError("decisions.health.json contains unknown field")
    if not HEALTH_BASE_REQUIRED_KEYS.issubset(data.keys()):
        raise ExportValidationError("decisions.health.json missing required field")

    if not is_real_int(data["schema_version"]) or data["schema_version"] != 1:
        raise ExportValidationError("decisions.health.json invalid schema_version")
    if data["status"] not in VALID_HEALTH_STATUSES:
        raise ExportValidationError("decisions.health.json invalid status")
    if not is_valid_rfc3339(data["updated_at"]):
        raise ExportValidationError("decisions.health.json invalid updated_at")

    for int_field in ("capacity_bytes", "bytes_used", "dropped_records"):
        val = data[int_field]
        if not is_real_int(val) or val < 0:
            raise ExportValidationError("decisions.health.json invalid numeric field")
    for bool_field in ("gap_detected", "capacity_exceeded", "io_error"):
        if not isinstance(data[bool_field], bool):
            raise ExportValidationError("decisions.health.json invalid boolean field")

    if "reason" in data and data["reason"] is not None:
        reason = data["reason"]
        if not isinstance(reason, str) or reason not in KNOWN_REASONS:
            raise ExportValidationError("decisions.health.json invalid or non-canonical reason")

    present_rot = [k for k in ROTATION_HEALTH_KEYS if k in data]
    if present_rot and len(present_rot) != len(ROTATION_HEALTH_KEYS):
        raise ExportValidationError("decisions.health.json has incomplete rotation fields")

    if present_rot:
        max_files = data["max_files"]
        active_gen = data["active_generation"]
        retained = data["retained_segments"]
        expired = data["expired_segments"]
        pruned = data["retention_pruned"]

        if not is_real_int(max_files) or max_files < 1 or max_files > MAX_FILES:
            raise ExportValidationError("decisions.health.json invalid max_files")
        if not is_real_int(active_gen) or active_gen < 0:
            raise ExportValidationError("decisions.health.json invalid active_generation")
        if not is_real_int(retained) or retained < 1 or retained > max_files:
            raise ExportValidationError("decisions.health.json invalid retained_segments")
        if not is_real_int(expired) or expired < 0:
            raise ExportValidationError("decisions.health.json invalid expired_segments")
        if not isinstance(pruned, bool) or pruned != (expired > 0):
            raise ExportValidationError("decisions.health.json invalid retention_pruned")
        if active_gen + 1 != expired + retained:
            raise ExportValidationError("decisions.health.json generation and segment counts mismatch")

    return data


def parse_and_validate_manifest(raw: bytes, max_ndjson_bytes: int) -> dict[str, Any]:
    if not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise ExportValidationError("decisions.manifest.json size out of bounds")
    data = _loads_strict_json_object(raw, MANIFEST_FILENAME)
    if set(data.keys()) != MANIFEST_REQUIRED_KEYS:
        raise ExportValidationError("decisions.manifest.json violates strict schema v1 keys")

    if not is_real_int(data["schema_version"]) or data["schema_version"] != 1:
        raise ExportValidationError("decisions.manifest.json invalid schema_version")
    if not is_real_int(data["manifest_version"]) or data["manifest_version"] < 0:
        raise ExportValidationError("decisions.manifest.json invalid manifest_version")
    first_gen = data["first_retained_generation"]
    expired = data["expired_segments"]
    if not is_real_int(first_gen) or first_gen < 0:
        raise ExportValidationError("decisions.manifest.json invalid first_retained_generation")
    if not is_real_int(expired) or expired < 0:
        raise ExportValidationError("decisions.manifest.json invalid expired_segments")
    if first_gen != expired:
        raise ExportValidationError("decisions.manifest.json first_retained_generation does not match expired_segments")
    if not is_valid_rfc3339(data["updated_at"]):
        raise ExportValidationError("decisions.manifest.json invalid updated_at")

    sealed = data["sealed_segments"]
    if not isinstance(sealed, list) or len(sealed) > MAX_SEALED_SEGMENTS:
        raise ExportValidationError("decisions.manifest.json invalid sealed_segments")

    expected_gen = first_gen
    sealed_total = 0
    for seg in sealed:
        if not isinstance(seg, dict) or set(seg.keys()) != SEALED_SEGMENT_KEYS:
            raise ExportValidationError("decisions.manifest.json invalid sealed segment entry")
        gen = seg["generation"]
        fname = seg["file_name"]
        seg_bytes = seg["bytes"]
        if not is_real_int(gen) or gen != expected_gen:
            raise ExportValidationError("decisions.manifest.json non-contiguous sealed segment generation")
        if not isinstance(fname, str) or fname != canonical_segment_name(gen):
            raise ExportValidationError("decisions.manifest.json non-canonical sealed segment name")
        if not is_real_int(seg_bytes) or seg_bytes < 0 or seg_bytes > max_ndjson_bytes:
            raise ExportValidationError("decisions.manifest.json invalid sealed segment byte length")
        sealed_total += seg_bytes
        if sealed_total > max_ndjson_bytes:
            raise ExportValidationError("decisions.manifest.json sealed segments exceed maximum NDJSON size")
        expected_gen += 1

    active = data["active_segment"]
    if not isinstance(active, dict) or set(active.keys()) != ACTIVE_SEGMENT_KEYS:
        raise ExportValidationError("decisions.manifest.json invalid active_segment entry")
    active_gen = active["generation"]
    active_name = active["file_name"]
    watermark = active["watermark_bytes"]
    if not is_real_int(active_gen) or active_gen != expected_gen:
        raise ExportValidationError("decisions.manifest.json active_segment generation is not contiguous")
    if not isinstance(active_name, str) or active_name != canonical_segment_name(active_gen):
        raise ExportValidationError("decisions.manifest.json non-canonical active_segment name")
    if not is_real_int(watermark) or watermark < 0 or sealed_total + watermark > max_ndjson_bytes:
        raise ExportValidationError("decisions.manifest.json invalid active_segment watermark_bytes")

    return data


def build_expected_segments(
    health: dict[str, Any],
    manifest: dict[str, Any] | None,
) -> tuple[list[tuple[str, int, bool]], int | None]:
    """Return (ordered list of (file_name, expected_or_min_bytes, is_active), healthy_segment_cap)."""
    has_rot_health = any(k in health for k in ROTATION_HEALTH_KEYS)
    healthy_cap: int | None = None
    if health["status"] == "healthy" and not health["capacity_exceeded"]:
        if health["capacity_bytes"] < 1:
            raise ExportValidationError("decisions.health.json healthy capacity_bytes must be positive")
        if health["bytes_used"] > health["capacity_bytes"]:
            raise ExportValidationError("decisions.health.json bytes_used exceeds healthy capacity_bytes")
        healthy_cap = health["capacity_bytes"]

    if manifest is None:
        if has_rot_health:
            if (
                health["active_generation"] != 0
                or health["retained_segments"] != 1
                or health["expired_segments"] != 0
                or health["retention_pruned"] is not False
            ):
                raise ExportValidationError(
                    "decisions.manifest.json is missing for rotated journal state"
                )
        return [(GEN0_FILENAME, health["bytes_used"], True)], healthy_cap

    if not has_rot_health:
        raise ExportValidationError(
            "decisions.health.json missing rotation metadata required by manifest"
        )

    sealed = manifest["sealed_segments"]
    active = manifest["active_segment"]
    expected_retained = len(sealed) + 1
    expected_expired = manifest["expired_segments"]

    if health["active_generation"] != active["generation"]:
        raise ExportValidationError("health active_generation does not match manifest")
    if health["retained_segments"] != expected_retained:
        raise ExportValidationError("health retained_segments does not match manifest")
    if health["expired_segments"] != expected_expired:
        raise ExportValidationError("health expired_segments does not match manifest")
    if health["retention_pruned"] != (expected_expired > 0):
        raise ExportValidationError("health retention_pruned does not match manifest")
    if health["max_files"] < expected_retained:
        raise ExportValidationError("health max_files is smaller than retained_segments")

    active_min_bytes = max(active["watermark_bytes"], health["bytes_used"])
    if healthy_cap is not None and active_min_bytes > healthy_cap:
        raise ExportValidationError("active segment watermark exceeds healthy capacity_bytes")

    plan: list[tuple[str, int, bool]] = []
    for seg in sealed:
        if healthy_cap is not None and seg["bytes"] > healthy_cap:
            raise ExportValidationError("sealed segment length exceeds healthy capacity_bytes")
        plan.append((seg["file_name"], seg["bytes"], False))
    plan.append((active["file_name"], active_min_bytes, True))
    return plan, healthy_cap


def _read_bounded_member(
    tf: tarfile.TarFile,
    member: tarfile.TarInfo,
    max_bytes: int,
    label: str,
) -> bytes:
    if member.size < 0 or member.size > max_bytes:
        raise ExportValidationError(f"{label} exceeds maximum allowed size")
    extracted = tf.extractfile(member)
    if extracted is None:
        raise ExportValidationError(f"unable to read {label} from archive")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = extracted.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ExportValidationError(f"{label} exceeds maximum allowed size")
        chunks.append(chunk)
    if total != member.size:
        raise ExportValidationError(f"{label} truncated in archive")
    return b"".join(chunks)


def process_tar_stream(
    stream: BinaryIO,
    ndjson_out_path: str,
    health_out_path: str,
    max_ndjson_bytes: int = MAX_NDJSON_BYTES,
) -> dict[str, int]:
    """Validate tar snapshot from stream and write concatenated NDJSON + health JSON."""
    max_stream_bytes = (
        max_ndjson_bytes + MAX_HEALTH_BYTES + MAX_MANIFEST_BYTES + TAR_OVERHEAD_BYTES
    )
    limited = _LimitedStream(stream, max_stream_bytes)

    seen_names: set[str] = set()
    health_raw: bytes | None = None
    manifest_raw: bytes | None = None
    expected_segments: list[tuple[str, int, bool]] | None = None
    healthy_cap: int | None = None
    seg_idx = 0
    total_ndjson_bytes = 0
    sealed_count = 0

    try:
        with open(ndjson_out_path, "wb") as ndjson_out:
            with tarfile.open(fileobj=limited, mode="r|") as tf:
                for member in tf:
                    if not member.isreg():
                        raise ExportValidationError("archive contains non-regular entry")
                    name = validate_member_name(member.name)
                    if name in seen_names:
                        raise ExportValidationError("archive contains duplicate entry")
                    seen_names.add(name)

                    if name == HEALTH_FILENAME:
                        if expected_segments is not None:
                            raise ExportValidationError("health metadata must precede segments")
                        health_raw = _read_bounded_member(
                            tf, member, MAX_HEALTH_BYTES, HEALTH_FILENAME
                        )
                        continue

                    if name == MANIFEST_FILENAME:
                        if expected_segments is not None:
                            raise ExportValidationError("manifest metadata must precede segments")
                        manifest_raw = _read_bounded_member(
                            tf, member, MAX_MANIFEST_BYTES, MANIFEST_FILENAME
                        )
                        continue

                    # First segment reached: validate metadata and lock in expected segment sequence.
                    if expected_segments is None:
                        if health_raw is None:
                            raise ExportValidationError("decisions.health.json missing before segments")
                        health_obj = parse_and_validate_health(health_raw)
                        manifest_obj = (
                            parse_and_validate_manifest(manifest_raw, max_ndjson_bytes)
                            if manifest_raw is not None
                            else None
                        )
                        expected_segments, healthy_cap = build_expected_segments(
                            health_obj, manifest_obj
                        )
                        sealed_count = len(expected_segments) - 1

                    if seg_idx >= len(expected_segments):
                        raise ExportValidationError("archive contains unexpected extra segment")

                    exp_name, exp_bytes, is_active = expected_segments[seg_idx]
                    if name != exp_name:
                        raise ExportValidationError("segment sequence does not match manifest")

                    if member.size < 0 or total_ndjson_bytes + member.size > max_ndjson_bytes:
                        raise ExportValidationError("exported NDJSON exceeds maximum allowed size")

                    extracted = tf.extractfile(member)
                    if extracted is None:
                        raise ExportValidationError("unable to read segment from archive")

                    seg_bytes = 0
                    last_byte = b""
                    while True:
                        chunk = extracted.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        seg_bytes += len(chunk)
                        total_ndjson_bytes += len(chunk)
                        if total_ndjson_bytes > max_ndjson_bytes:
                            raise ExportValidationError(
                                "exported NDJSON exceeds maximum allowed size"
                            )
                        last_byte = chunk[-1:]
                        ndjson_out.write(chunk)

                    if seg_bytes != member.size:
                        raise ExportValidationError("segment truncated in archive")

                    if not is_active:
                        if seg_bytes != exp_bytes:
                            raise ExportValidationError(
                                "sealed segment length does not match manifest"
                            )
                    else:
                        if seg_bytes < exp_bytes:
                            raise ExportValidationError(
                                "active segment is truncated below expected watermark"
                            )
                        if healthy_cap is not None and seg_bytes > healthy_cap:
                            raise ExportValidationError(
                                "active segment exceeds healthy capacity_bytes"
                            )
                        if seg_bytes == 0 and sealed_count == 0:
                            raise ExportValidationError("exported journal is empty")

                    if seg_bytes > 0 and last_byte != b"\n":
                        raise ExportValidationError("segment has partial terminal line")

                    seg_idx += 1

            ndjson_out.flush()
            os.fsync(ndjson_out.fileno())
    except (tarfile.TarError, EOFError) as exc:
        raise ExportValidationError("malformed or truncated tar snapshot") from exc

    if health_raw is None:
        raise ExportValidationError("decisions.health.json missing from snapshot")
    if expected_segments is None:
        # Validate metadata even if no segments were present to return a clear error.
        health_obj = parse_and_validate_health(health_raw)
        manifest_obj = (
            parse_and_validate_manifest(manifest_raw, max_ndjson_bytes)
            if manifest_raw is not None
            else None
        )
        expected_segments, _ = build_expected_segments(health_obj, manifest_obj)
    if seg_idx != len(expected_segments):
        raise ExportValidationError("missing retained journal segment in snapshot")
    if total_ndjson_bytes <= 0:
        raise ExportValidationError("exported NDJSON is empty")

    with open(health_out_path, "wb") as health_out:
        health_out.write(health_raw)
        health_out.flush()
        os.fsync(health_out.fileno())

    return {
        "segments_concatenated": seg_idx,
        "ndjson_bytes": total_ndjson_bytes,
        "health_bytes": len(health_raw),
    }


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: export_decisions_archive.py <staged-ndjson-path> <staged-health-path>",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        process_tar_stream(sys.stdin.buffer, sys.argv[1], sys.argv[2])
    except ExportValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError:
        print("FAIL: local I/O error while staging exported journal", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

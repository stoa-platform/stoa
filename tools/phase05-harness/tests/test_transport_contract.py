"""Offline contract: tool names must survive Anthropic's validator.

Anthropic rejects tool registrations whose name doesn't match
`^[a-zA-Z0-9_-]{1,128}$` (HTTP 400 at `client.messages.create`). The harness
bridges this with a transport bijection in `run_bench._call_anthropic`
(`:` -> `__` on the wire, reverse-mapped on the response). This test locks
both halves of that contract on every condition / spec / scalability target
the bench will drive, without spending any tokens.

See Decision Gate log #6 (2026-04-19) and CAB-2124.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
sys.path.insert(0, str(ROOT))

import run_bench  # noqa: E402
from run_bench import _tools_for_condition  # noqa: E402

ANTHROPIC_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

SPEC_FILES = ("banking-services-v1-2.yaml", "payment-api.yaml", "fapi-accounts.yaml")
CONDITIONS = ("coarse", "per-op", "enriched-single")
SCALES: tuple[int | None, ...] = (None, 200)


def _spec(name: str) -> dict:
    return yaml.safe_load((SPECS / name).read_text())


def _api_id(spec_file: str) -> str:
    return spec_file.removesuffix(".yaml")


@pytest.mark.parametrize("spec_file", SPEC_FILES)
@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("scale", SCALES)
def test_transport_names_match_anthropic_regex(
    spec_file: str, condition: str, scale: int | None
) -> None:
    """After `:` -> `__`, every name must satisfy the Anthropic validator."""
    if scale is not None and condition != "per-op":
        pytest.skip("scalability only applies to per-op")

    spec = _spec(spec_file)
    tools = _tools_for_condition(condition, _api_id(spec_file), "demo", spec, scale=scale)
    assert tools, f"no tools generated for {spec_file}/{condition}"

    for tool in tools:
        transport_name = tool["name"].replace(":", "__")
        assert ANTHROPIC_NAME_RE.match(transport_name), (
            f"transport name rejects Anthropic regex: {transport_name!r} "
            f"(canonical={tool['name']!r}, condition={condition}, spec={spec_file})"
        )


@pytest.mark.parametrize("spec_file", SPEC_FILES)
@pytest.mark.parametrize("condition", ("coarse", "enriched-single"))
def test_canonical_names_still_use_colon(spec_file: str, condition: str) -> None:
    """Guards against the generator silently emitting transport-form names.

    If coarse/enriched names lose their `:`, the reverse-map in
    `_call_anthropic` turns into a no-op and scorer assumptions break — but
    everything still looks green. Fail loudly here instead.
    """
    spec = _spec(spec_file)
    tools = _tools_for_condition(condition, _api_id(spec_file), "demo", spec)
    for tool in tools:
        assert ":" in tool["name"], (
            f"{condition} name lost its canonical colon: {tool['name']!r} "
            f"(spec={spec_file}). Reverse-map in _call_anthropic would become a no-op."
        )


@pytest.mark.parametrize("spec_file", SPEC_FILES)
def test_per_op_names_have_no_colon(spec_file: str) -> None:
    """per-op names use `-` separators — no reverse-map needed, but lock it."""
    spec = _spec(spec_file)
    tools = _tools_for_condition("per-op", _api_id(spec_file), "demo", spec)
    for tool in tools:
        assert ":" not in tool["name"], (
            f"per-op name unexpectedly contains `:`: {tool['name']!r} (spec={spec_file})"
        )


@pytest.mark.parametrize("condition", ("coarse", "per-op", "enriched-single"))
def test_run_persists_canonical_tool_name(condition: str) -> None:
    """run() must emit records carrying the canonical tool_name verbatim.

    `_call_anthropic` already reverse-maps `__` -> `:` before returning, but
    the record-assembly path in `run()` must not reshape the field. Lock
    that with a stubbed `_call_anthropic` so the test stays offline.
    """
    prompt = {
        "id": "contract-test",
        "api": "payment-api",
        "tenant": "demo",
        "category": "normal",
        "prompt": "irrelevant",
        "ground_truth": {"op_id": "initiatePayment"},
    }
    canonical_names = {
        "coarse": "demo:payment-api",
        "enriched-single": "demo:payment-api",
        "per-op": "demo-payment-api-initiatePayment",
    }

    def _stub_call(
        client: Any, model: str, tools: list[dict[str, Any]], prompt_text: str
    ) -> dict[str, Any]:
        return {
            "tool_call": {
                "tool_name": canonical_names[condition],
                "input": {"action": "initiatePayment"},
            },
            "latency_ms": 123.4,
            "tokens_in": 100,
            "tokens_out": 20,
            "stop_reason": "tool_use",
        }

    with patch.object(run_bench, "_call_anthropic", side_effect=_stub_call), patch(
        "anthropic.Anthropic", create=True, return_value=object()
    ):
        records = run_bench.run(
            prompts=[prompt],
            specs_dir=SPECS,
            models=["claude-haiku-4-5-20251001"],
            conditions=[condition],
            runs=1,
            scalability=None,
            dry_run=False,
            parallel=1,
        )

    assert len(records) == 1
    rec = records[0]
    assert rec["condition"] == condition
    assert rec["tool_call"] is not None, f"run() dropped tool_call: {rec}"
    assert rec["tool_call"]["tool_name"] == canonical_names[condition], (
        f"run() reshaped tool_name: got {rec['tool_call']['tool_name']!r}, "
        f"expected {canonical_names[condition]!r}"
    )

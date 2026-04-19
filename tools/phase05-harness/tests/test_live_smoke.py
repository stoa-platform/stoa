"""Pre-Px live smoke test.

Exercises the real Anthropic API on the cheapest Claude 4.x model (Haiku) for
all three conditions against the smallest spec (`payment-api`). Gated on
`STOA_LIVE_SMOKE=1` + `ANTHROPIC_API_KEY` to keep CI free and avoid
accidental paid calls.

What it guards (bugs that would never surface in offline tests):

1. Tool-name regex (`^[a-zA-Z0-9_-]{1,128}$`) — exercised via the
   `:` -> `__` bijection in `run_bench._call_anthropic`. HTTP 400 at
   registration would raise and fail this test loudly, whereas
   `run_bench.run()` swallows it into `stop_reason="error: ..."`.

2. Deprecated / unsupported `client.messages.create` params on the pinned
   target model (any BadRequestError bubbles up as a pytest failure).

3. Reverse-mapping of canonical names: coarse and enriched-single must
   surface `tenant:api` (with `:`), not the wire-form `tenant__api`.

See CAB-2124 and Decision Gate log #6 (2026-04-19).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
sys.path.insert(0, str(ROOT))

from run_bench import _call_anthropic, _load_jsonl, _spec_for, _tools_for_condition  # noqa: E402

LIVE_MODEL = "claude-haiku-4-5-20251001"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("STOA_LIVE_SMOKE") != "1",
        reason="live smoke disabled: set STOA_LIVE_SMOKE=1 and ANTHROPIC_API_KEY to enable",
    ),
]


@pytest.fixture(scope="module")
def anthropic_client():
    import anthropic  # type: ignore[import-not-found]

    return anthropic.Anthropic()


@pytest.fixture(scope="module")
def payment_prompt() -> dict:
    """First `normal` prompt on payment-api — smallest spec, cheapest run."""
    prompts = _load_jsonl(ROOT / "prompts.jsonl")
    for p in prompts:
        if p["api"] == "payment-api" and p["category"] == "normal":
            return p
    pytest.fail("no normal payment-api prompt available")


@pytest.mark.parametrize("condition", ["coarse", "per-op", "enriched-single"])
def test_live_smoke(anthropic_client, payment_prompt, condition: str) -> None:
    spec = _spec_for(payment_prompt["api"], SPECS)
    tools = _tools_for_condition(
        condition, payment_prompt["api"], payment_prompt["tenant"], spec
    )
    assert tools, f"no tools for condition {condition}"

    result = _call_anthropic(
        anthropic_client, LIVE_MODEL, tools, payment_prompt["prompt"]
    )

    # Round-trip proof: real tokens in/out.
    assert result["tokens_in"] > 0, f"no input tokens reported: {result}"
    assert result["latency_ms"] > 0, f"no latency reported: {result}"

    # `run()` would swallow an API error into `stop_reason="error: ..."`. Here
    # we call `_call_anthropic` directly, so an error would have raised — but
    # double-check nothing is masquerading as a silent stop reason.
    stop_reason = result["stop_reason"]
    assert stop_reason is None or not str(stop_reason).startswith("error:"), (
        f"error stop_reason leaked through: {stop_reason}"
    )

    # Normal-category prompt: the model must emit a tool_use.
    assert result["tool_call"] is not None, (
        f"no tool call on normal prompt {payment_prompt['id']!r} "
        f"(condition={condition}, stop_reason={stop_reason})"
    )
    assert stop_reason == "tool_use", (
        f"expected stop_reason=tool_use, got {stop_reason!r} (condition={condition})"
    )

    tool_name = result["tool_call"]["tool_name"]
    tenant, api = payment_prompt["tenant"], payment_prompt["api"]

    if condition in ("coarse", "enriched-single"):
        # Canonical name must carry the colon — proves reverse-map worked.
        expected = f"{tenant}:{api}"
        assert tool_name == expected, (
            f"reverse-map regression: got {tool_name!r}, expected {expected!r} "
            f"(condition={condition})"
        )
    else:  # per-op
        prefix = f"{tenant}-{api}-"
        assert tool_name.startswith(prefix), (
            f"per-op name shape regression: {tool_name!r} must start with {prefix!r}"
        )
        assert ":" not in tool_name, (
            f"per-op name unexpectedly contains `:`: {tool_name!r}"
        )

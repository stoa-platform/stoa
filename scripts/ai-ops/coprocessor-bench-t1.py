#!/usr/bin/env python3
"""
Coprocessor Benchmark T1 — Mistral Small vs Claude Sonnet

Validates that HEGEMON can route peripheral tasks to Mistral Small API
and obtain acceptable quality. ARM coprocessor strategy: T1 = Touch Bar
before M1.

Task: Generate docstrings for control-plane-api/src/core/pii/patterns.py

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export MISTRAL_API_KEY=...
    python3 scripts/ai-ops/coprocessor-bench-t1.py

    # Run specific provider only
    python3 scripts/ai-ops/coprocessor-bench-t1.py --provider mistral
    python3 scripts/ai-ops/coprocessor-bench-t1.py --provider claude

    # Save report to file
    python3 scripts/ai-ops/coprocessor-bench-t1.py --output report.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TARGET_FILE = "control-plane-api/src/core/pii/patterns.py"

PROMPT = """\
You are a senior Python developer. Add comprehensive Google-style docstrings \
to every class, method, and module-level constant in the following Python file.

Rules:
- Keep ALL existing code exactly as-is (do not change logic, imports, or formatting)
- Add module docstring if missing or incomplete
- Add class docstrings explaining purpose and usage
- Add method docstrings with Args, Returns, and Examples sections
- Add inline comments for the _PATTERNS list explaining priority ordering
- Use Google docstring style (Args:, Returns:, Examples:)
- Output the COMPLETE file with docstrings added

File: {filename}

```python
{source}
```

Output ONLY the complete Python file with docstrings. No explanation before or after."""

# Provider configs
CLAUDE_MODEL = "claude-sonnet-4-5-20251001"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_PRICING = {"input": 3.0, "output": 15.0}  # $/MTok

MISTRAL_MODEL = "mistral-small-latest"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_PRICING = {"input": 0.1, "output": 0.3}  # $/MTok (EUR ~ USD for simplicity)


@dataclass
class BenchResult:
    """Result of a single benchmark run."""

    provider: str
    model: str
    output: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    cost_usd: float
    error: str | None = None


# ---------------------------------------------------------------------------
# API Callers
# ---------------------------------------------------------------------------


def call_claude(prompt: str, api_key: str) -> BenchResult:
    """Call Claude Sonnet via Anthropic Messages API."""
    t0 = time.monotonic()
    try:
        resp = httpx.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120.0,
        )
        latency = time.monotonic() - t0
        resp.raise_for_status()
        data = resp.json()

        output = data["content"][0]["text"]
        usage = data.get("usage", {})
        input_tok = usage.get("input_tokens", 0)
        output_tok = usage.get("output_tokens", 0)
        cost = (input_tok * CLAUDE_PRICING["input"] + output_tok * CLAUDE_PRICING["output"]) / 1_000_000

        return BenchResult(
            provider="claude",
            model=CLAUDE_MODEL,
            output=output,
            input_tokens=input_tok,
            output_tokens=output_tok,
            latency_s=latency,
            cost_usd=cost,
        )
    except Exception as e:
        return BenchResult(
            provider="claude",
            model=CLAUDE_MODEL,
            output="",
            input_tokens=0,
            output_tokens=0,
            latency_s=time.monotonic() - t0,
            cost_usd=0,
            error=str(e),
        )


def call_mistral(prompt: str, api_key: str) -> BenchResult:
    """Call Mistral Small via OpenAI-compatible API."""
    t0 = time.monotonic()
    try:
        resp = httpx.post(
            MISTRAL_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MISTRAL_MODEL,
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a senior Python developer. Follow instructions precisely.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=120.0,
        )
        latency = time.monotonic() - t0
        resp.raise_for_status()
        data = resp.json()

        output = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        input_tok = usage.get("prompt_tokens", 0)
        output_tok = usage.get("completion_tokens", 0)
        cost = (input_tok * MISTRAL_PRICING["input"] + output_tok * MISTRAL_PRICING["output"]) / 1_000_000

        return BenchResult(
            provider="mistral",
            model=MISTRAL_MODEL,
            output=output,
            input_tokens=input_tok,
            output_tokens=output_tok,
            latency_s=latency,
            cost_usd=cost,
        )
    except Exception as e:
        return BenchResult(
            provider="mistral",
            model=MISTRAL_MODEL,
            output="",
            input_tokens=0,
            output_tokens=0,
            latency_s=time.monotonic() - t0,
            cost_usd=0,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Quality Scoring
# ---------------------------------------------------------------------------


def score_docstring_quality(source: str, output: str) -> dict:
    """Score the quality of generated docstrings.

    Returns dict with individual scores and total (0-10).
    """
    scores = {}

    # 1. Completeness — did it add docstrings to all methods? (0-3)
    methods = ["mask_email", "mask_phone", "mask_iban", "mask_cc", "mask_ip", "mask_jwt", "mask_api_key", "mask_full"]
    docstring_count = sum(1 for m in methods if f"def {m}" in output and '"""' in _get_method_block(output, m))
    scores["completeness"] = round(3.0 * docstring_count / len(methods), 1)

    # 2. Preservation — is all original code still present? (0-2)
    key_fragments = [
        "class PIIType(StrEnum):",
        "class PIIPatterns:",
        "@dataclass(frozen=True)",
        "def get_all(cls)",
        "def get_enabled(cls",
        "PIIPattern(PIIType.JWT",
    ]
    preserved = sum(1 for f in key_fragments if f in output)
    scores["preservation"] = round(2.0 * preserved / len(key_fragments), 1)

    # 3. Google style — does it use Args/Returns/Examples? (0-2)
    style_markers = ["Args:", "Returns:", "Examples:", "Example:"]
    style_count = sum(1 for m in style_markers if m in output)
    scores["google_style"] = min(2.0, round(2.0 * style_count / 3, 1))

    # 4. Class docstrings — PIIType, PIIPattern, PIIPatterns (0-1.5)
    classes = ["class PIIType", "class PIIPattern:", "class PIIPatterns:"]
    class_docs = sum(1 for c in classes if _has_class_docstring(output, c))
    scores["class_docs"] = round(1.5 * class_docs / len(classes), 1)

    # 5. Module docstring quality (0-1.5)
    lines = output.strip().split("\n")
    # Check if first non-empty line starts a docstring
    first_content = next((l for l in lines if l.strip()), "")
    if first_content.strip().startswith('"""') or first_content.strip().startswith("'''"):
        # Count docstring length
        ds_lines = 0
        in_ds = False
        for l in lines:
            if '"""' in l or "'''" in l:
                if in_ds:
                    ds_lines += 1
                    break
                in_ds = True
            if in_ds:
                ds_lines += 1
        scores["module_doc"] = min(1.5, round(0.5 * ds_lines, 1))
    else:
        scores["module_doc"] = 0.0

    scores["total"] = round(sum(scores.values()), 1)
    return scores


def _get_method_block(source: str, method_name: str) -> str:
    """Extract the text block for a method (from def to next def/class)."""
    lines = source.split("\n")
    start = None
    for i, line in enumerate(lines):
        if f"def {method_name}" in line:
            start = i
        elif start is not None and (line.strip().startswith("def ") or line.strip().startswith("class ")):
            return "\n".join(lines[start:i])
    if start is not None:
        return "\n".join(lines[start:])
    return ""


def _has_class_docstring(source: str, class_marker: str) -> bool:
    """Check if a class has a docstring right after its definition."""
    lines = source.split("\n")
    for i, line in enumerate(lines):
        if class_marker in line and i + 1 < len(lines):
            # Check next non-empty line for docstring
            for j in range(i + 1, min(i + 4, len(lines))):
                stripped = lines[j].strip()
                if stripped:
                    return stripped.startswith('"""') or stripped.startswith("'''")
    return False


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------


def generate_report(
    results: list[BenchResult],
    scores: dict[str, dict],
    source_file: str,
) -> str:
    """Generate a markdown comparison report."""
    report = []
    report.append("# Coprocessor Benchmark T1 — Mistral Small vs Claude Sonnet\n")
    report.append(f"**Task**: Generate docstrings for `{source_file}`")
    report.append(f"**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    report.append(f"**Protocol**: Single run per provider, same prompt, quality scored 0-10\n")

    # Summary table
    report.append("## Results Summary\n")
    report.append("| Metric | " + " | ".join(r.provider.title() for r in results) + " |")
    report.append("|--------|" + "|".join("--------|" for _ in results))

    report.append(
        "| Model | " + " | ".join(f"`{r.model}`" for r in results) + " |"
    )
    report.append(
        "| Latency | " + " | ".join(f"{r.latency_s:.1f}s" for r in results) + " |"
    )
    report.append(
        "| Input tokens | " + " | ".join(f"{r.input_tokens:,}" for r in results) + " |"
    )
    report.append(
        "| Output tokens | " + " | ".join(f"{r.output_tokens:,}" for r in results) + " |"
    )
    report.append(
        "| Cost | " + " | ".join(f"${r.cost_usd:.4f}" for r in results) + " |"
    )

    # Quality scores
    if scores:
        report.append(
            "| **Quality (0-10)** | "
            + " | ".join(f"**{scores.get(r.provider, {}).get('total', 'N/A')}**" for r in results)
            + " |"
        )

    report.append("")

    # Detailed quality breakdown
    if scores:
        report.append("## Quality Breakdown\n")
        report.append("| Dimension | Max | " + " | ".join(r.provider.title() for r in results) + " |")
        report.append("|-----------|-----|" + "|".join("-----|" for _ in results))

        dimensions = [
            ("completeness", "Completeness (docstrings on all methods)", 3.0),
            ("preservation", "Code preservation (no changes)", 2.0),
            ("google_style", "Google docstring style", 2.0),
            ("class_docs", "Class docstrings", 1.5),
            ("module_doc", "Module docstring", 1.5),
        ]
        for key, label, max_val in dimensions:
            vals = " | ".join(
                str(scores.get(r.provider, {}).get(key, "N/A")) for r in results
            )
            report.append(f"| {label} | {max_val} | {vals} |")
        report.append("")

    # Cost comparison
    if len(results) == 2:
        r_claude = next((r for r in results if r.provider == "claude"), None)
        r_mistral = next((r for r in results if r.provider == "mistral"), None)
        if r_claude and r_mistral and r_claude.cost_usd > 0:
            ratio = r_claude.cost_usd / r_mistral.cost_usd if r_mistral.cost_usd > 0 else float("inf")
            speed_ratio = r_claude.latency_s / r_mistral.latency_s if r_mistral.latency_s > 0 else float("inf")
            report.append("## Cost & Speed Analysis\n")
            report.append(f"- Claude is **{ratio:.0f}x more expensive** than Mistral for this task")
            if speed_ratio > 1:
                report.append(f"- Claude is **{speed_ratio:.1f}x slower** than Mistral")
            else:
                report.append(f"- Claude is **{1/speed_ratio:.1f}x faster** than Mistral")
            report.append("")

    # Errors
    errors = [r for r in results if r.error]
    if errors:
        report.append("## Errors\n")
        for r in errors:
            report.append(f"- **{r.provider}**: `{r.error}`")
        report.append("")

    # Conclusion
    report.append("## Conclusion\n")
    if len(scores) == 2:
        s_claude = scores.get("claude", {}).get("total", 0)
        s_mistral = scores.get("mistral", {}).get("total", 0)
        if s_mistral >= 7.0:
            report.append(
                f"**Go** — Mistral Small scores {s_mistral}/10 (threshold: 7.0). "
                "Suitable for peripheral docstring generation tasks."
            )
        elif s_mistral >= 5.0:
            report.append(
                f"**Conditional Go** — Mistral Small scores {s_mistral}/10. "
                "Acceptable with prompt tuning. Needs adaptation before production use."
            )
        else:
            report.append(
                f"**No-Go** — Mistral Small scores {s_mistral}/10. "
                "Quality insufficient for this task type."
            )
        report.append(f"\nClaude reference score: {s_claude}/10")
    elif len(scores) == 1:
        provider = list(scores.keys())[0]
        score = scores[provider].get("total", 0)
        report.append(f"Single provider run: **{provider}** scored {score}/10")
    report.append("")

    # Raw outputs (truncated)
    report.append("## Output Samples (first 80 lines)\n")
    for r in results:
        if r.output:
            report.append(f"### {r.provider.title()} ({r.model})\n")
            lines = r.output.split("\n")[:80]
            report.append("```python")
            report.append("\n".join(lines))
            if len(r.output.split("\n")) > 80:
                report.append(f"# ... ({len(r.output.split(chr(10))) - 80} more lines)")
            report.append("```\n")

    return "\n".join(report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Coprocessor Benchmark T1")
    parser.add_argument(
        "--provider",
        choices=["claude", "mistral", "both"],
        default="both",
        help="Which provider(s) to benchmark (default: both)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save report to file (default: stdout)",
    )
    args = parser.parse_args()

    # Find repo root
    repo_root = Path(__file__).resolve().parent.parent.parent
    source_path = repo_root / TARGET_FILE

    if not source_path.exists():
        print(f"ERROR: Target file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    source = source_path.read_text()
    prompt = PROMPT.format(filename=TARGET_FILE, source=source)

    print(f"Target: {TARGET_FILE} ({len(source)} chars, {len(source.split(chr(10)))} lines)")
    print(f"Prompt: {len(prompt)} chars")
    print()

    results: list[BenchResult] = []
    scores: dict[str, dict] = {}

    # Run Claude
    if args.provider in ("claude", "both"):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("WARNING: ANTHROPIC_API_KEY not set, skipping Claude", file=sys.stderr)
        else:
            print(f"Running Claude ({CLAUDE_MODEL})...", end=" ", flush=True)
            result = call_claude(prompt, api_key)
            results.append(result)
            if result.error:
                print(f"ERROR: {result.error}")
            else:
                score = score_docstring_quality(source, result.output)
                scores["claude"] = score
                print(
                    f"done in {result.latency_s:.1f}s | "
                    f"{result.input_tokens}+{result.output_tokens} tok | "
                    f"${result.cost_usd:.4f} | "
                    f"quality: {score['total']}/10"
                )

    # Run Mistral
    if args.provider in ("mistral", "both"):
        api_key = os.environ.get("MISTRAL_API_KEY", "")
        if not api_key:
            print("WARNING: MISTRAL_API_KEY not set, skipping Mistral", file=sys.stderr)
        else:
            print(f"Running Mistral ({MISTRAL_MODEL})...", end=" ", flush=True)
            result = call_mistral(prompt, api_key)
            results.append(result)
            if result.error:
                print(f"ERROR: {result.error}")
            else:
                score = score_docstring_quality(source, result.output)
                scores["mistral"] = score
                print(
                    f"done in {result.latency_s:.1f}s | "
                    f"{result.input_tokens}+{result.output_tokens} tok | "
                    f"${result.cost_usd:.4f} | "
                    f"quality: {score['total']}/10"
                )

    if not results:
        print("\nERROR: No providers ran. Set ANTHROPIC_API_KEY and/or MISTRAL_API_KEY.", file=sys.stderr)
        sys.exit(1)

    # Generate report
    report = generate_report(results, scores, TARGET_FILE)

    if args.output:
        Path(args.output).write_text(report)
        print(f"\nReport saved to {args.output}")
    else:
        print("\n" + "=" * 80)
        print(report)

    # Also save raw JSON results for future analysis
    raw_path = repo_root / "scripts" / "ai-ops" / ".coprocessor-t1-results.json"
    raw_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task": "docstring_generation",
        "target": TARGET_FILE,
        "results": [
            {
                "provider": r.provider,
                "model": r.model,
                "latency_s": r.latency_s,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "quality_score": scores.get(r.provider, {}).get("total"),
                "quality_breakdown": scores.get(r.provider),
                "error": r.error,
            }
            for r in results
        ],
    }
    raw_path.write_text(json.dumps(raw_data, indent=2) + "\n")
    print(f"Raw results: {raw_path.relative_to(repo_root)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Anthropic Batch API processor for async AI Factory tasks.

Submits prompts to the Anthropic Message Batches API (50% discount)
and polls for results. Designed for CI jobs that don't need interactive
tool use (digests, capacity reports, backlog analysis, self-improvement).

Usage:
    python batch-processor.py \
        --prompt-file /tmp/prompt.txt \
        --context-file /tmp/context.txt \
        --model claude-haiku-4-5-20251001 \
        --output /tmp/result.json \
        --max-wait 1800

Environment:
    ANTHROPIC_API_KEY: Required. Anthropic API key.

Exit codes:
    0: Success, result written to --output
    1: Error (missing key, timeout, API failure)
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.anthropic.com/v1"
POLL_INTERVAL_INITIAL = 10  # seconds
POLL_INTERVAL_MAX = 60
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_BETA = "message-batches-2024-09-24"


def api_request(method: str, path: str, api_key: str, data: dict | None = None) -> dict:
    """Make an authenticated request to the Anthropic API."""
    url = f"{API_BASE}{path}"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": ANTHROPIC_BETA,
        "content-type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        print(f"API error {e.code}: {error_body}", file=sys.stderr)
        sys.exit(1)


def create_batch(api_key: str, model: str, prompt: str, max_tokens: int) -> str:
    """Create a message batch with a single request and return the batch ID."""
    payload = {
        "requests": [
            {
                "custom_id": "ai-factory-batch-0",
                "params": {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            }
        ],
    }
    result = api_request("POST", "/messages/batches", api_key, payload)
    batch_id = result["id"]
    print(f"Batch created: {batch_id}")
    return batch_id


def poll_batch(api_key: str, batch_id: str, max_wait: int) -> dict:
    """Poll batch status with exponential backoff until complete or timeout."""
    elapsed = 0
    interval = POLL_INTERVAL_INITIAL
    while elapsed < max_wait:
        status = api_request("GET", f"/messages/batches/{batch_id}", api_key)
        processing_status = status.get("processing_status", "unknown")
        print(f"  Status: {processing_status} ({elapsed}s elapsed)")
        if processing_status == "ended":
            return status
        time.sleep(interval)
        elapsed += interval
        interval = min(interval * 2, POLL_INTERVAL_MAX)
    print(f"Timeout after {max_wait}s. Batch {batch_id} still processing.", file=sys.stderr)
    sys.exit(1)


def fetch_results(api_key: str, batch_id: str) -> list[dict]:
    """Fetch batch results via the results endpoint."""
    result = api_request("GET", f"/messages/batches/{batch_id}/results", api_key)
    # The results endpoint returns JSONL; handle both list and single-object responses
    if isinstance(result, list):
        return result
    return [result]


def extract_text(results: list[dict]) -> str:
    """Extract text content from batch results."""
    for item in results:
        msg = item.get("result", {})
        if msg.get("type") == "succeeded":
            message = msg.get("message", {})
            for block in message.get("content", []):
                if block.get("type") == "text":
                    return block["text"]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Anthropic Batch API processor")
    parser.add_argument("--prompt-file", required=True, help="Path to prompt text file")
    parser.add_argument("--context-file", help="Path to context file (prepended to prompt)")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001", help="Model ID")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max output tokens")
    parser.add_argument("--max-wait", type=int, default=1800, help="Max poll wait (seconds)")
    parser.add_argument("--output", required=True, help="Output file path for result JSON")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY environment variable required", file=sys.stderr)
        sys.exit(1)

    # Build prompt from files
    with open(args.prompt_file) as f:
        prompt = f.read()
    if args.context_file:
        with open(args.context_file) as f:
            context = f.read()
        prompt = f"Context:\n{context}\n\n---\n\nTask:\n{prompt}"

    print(f"Model: {args.model}")
    print(f"Prompt length: {len(prompt)} chars")
    print(f"Max wait: {args.max_wait}s")

    # Create batch
    batch_id = create_batch(api_key, args.model, prompt, args.max_tokens)

    # Poll until complete
    status = poll_batch(api_key, batch_id, args.max_wait)

    # Fetch and extract results
    counts = status.get("request_counts", {})
    print(f"Batch complete: {counts.get('succeeded', 0)} succeeded, {counts.get('errored', 0)} errored")

    results = fetch_results(api_key, batch_id)
    text = extract_text(results)

    # Write output
    output = {
        "batch_id": batch_id,
        "model": args.model,
        "status": status.get("processing_status"),
        "request_counts": counts,
        "text": text,
    }
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Result written to {args.output} ({len(text)} chars)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Apply a council:<namespace>-* label to a Linear ticket and post a comment.

Phase 2a of CI-1 rewrite (CI-1-REWRITE-PLAN.md B.2). Replaces the two
83/78-line inline bash blocks in
.github/workflows/claude-issue-to-pr.yml ("Sync Council to Linear" and
"Sync Plan Council to Linear"), which are duplicated at 95% bar the
`council:ticket-*` vs `council:plan-*` namespace.

The GraphQL surface is preserved verbatim from the legacy bash:
    - issueSearch(filter: { identifier: { eq: $id } }) -> issue_id
    - issueLabels(filter: { name: { eq: $name } })     -> label_id
    - issue(id).labels.nodes                           -> existing
    - issueUpdate(input: { labelIds })                 -> dedup + replace
    - commentCreate(input: { issueId, body })          -> comment

Behaviour on edge cases (mirrors legacy bash with `|| true` fallbacks):
    - LINEAR_API_KEY missing     -> exit 0, skipped_reason="no_api_key"
    - Ticket id not found        -> exit 0, skipped_reason="ticket_not_found"
    - Target label not found     -> exit 0, skipped_reason="label_not_found"
    - HTTP / GraphQL error       -> exit 1 (caller is expected to
                                    `continue-on-error: true` at the
                                    workflow step level, per legacy)

NOTE: This script preserves the queries that the current workflow
sends. The strings are not modernized even if `issueSearch(filter:)`
behaves differently from `issues(filter:)` — see §K of the rewrite
plan, bug-fix work is explicitly out of scope here.

Comment body is passed through to GraphQL verbatim via json.dumps. The
legacy bash embedded a literal `\\n` (backslash-n, two chars) in the
body, which Linear's JSON parser then decoded as a newline because the
raw chars sat unescaped in the request payload. When callers migrate
to this script, they should pass real newlines ("\\n" as 1 character)
to obtain the same rendered output — document the change at the call
site.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from map_score_to_label import map_score

LINEAR_ENDPOINT = "https://api.linear.app/graphql"


def _graphql(query: str, variables: dict[str, Any], api_key: str, *, timeout: int = 10) -> dict[str, Any]:
    """POST a GraphQL request to Linear and return the decoded response.

    Raises urllib.error.HTTPError / URLError on network failures, and
    ValueError if the payload is not JSON or contains top-level errors.
    """
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        LINEAR_ENDPOINT,
        data=payload,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Linear returned non-JSON: {body!r}") from exc
    if parsed.get("errors"):
        raise ValueError(f"GraphQL errors: {parsed['errors']}")
    return parsed.get("data", {})


def _find_issue_id(ticket_id: str, api_key: str) -> str | None:
    query = (
        "query($id: String!) { issueSearch(filter: { identifier: { eq: $id } })"
        " { nodes { id } } }"
    )
    try:
        data = _graphql(query, {"id": ticket_id}, api_key)
    except ValueError:
        return None
    nodes = (data.get("issueSearch") or {}).get("nodes") or []
    if not nodes:
        return None
    return nodes[0].get("id")


def _find_label_id(label_name: str, api_key: str) -> str | None:
    query = (
        "query($name: String!) { issueLabels(filter: { name: { eq: $name } })"
        " { nodes { id } } }"
    )
    try:
        data = _graphql(query, {"name": label_name}, api_key)
    except ValueError:
        return None
    nodes = (data.get("issueLabels") or {}).get("nodes") or []
    if not nodes:
        return None
    return nodes[0].get("id")


def _get_issue_labels(issue_id: str, api_key: str) -> list[dict[str, Any]]:
    query = (
        "query($id: String!) { issue(id: $id) { labels { nodes { id name } } } }"
    )
    data = _graphql(query, {"id": issue_id}, api_key)
    issue = data.get("issue") or {}
    labels = (issue.get("labels") or {}).get("nodes") or []
    return [node for node in labels if isinstance(node, dict)]


def _update_issue_labels(issue_id: str, label_ids: list[str], api_key: str) -> bool:
    mutation = (
        "mutation($id: String!, $ids: [String!]!) {"
        " issueUpdate(id: $id, input: { labelIds: $ids }) { success } }"
    )
    data = _graphql(mutation, {"id": issue_id, "ids": label_ids}, api_key)
    return bool((data.get("issueUpdate") or {}).get("success"))


def _create_comment(issue_id: str, body: str, api_key: str) -> bool:
    mutation = (
        "mutation($id: String!, $body: String!) {"
        " commentCreate(input: { issueId: $id, body: $body }) { success } }"
    )
    data = _graphql(mutation, {"id": issue_id, "body": body}, api_key)
    return bool((data.get("commentCreate") or {}).get("success"))


def apply_label_and_comment(
    ticket_id: str,
    namespace: str,
    score: float,
    comment_body: str,
    api_key: str | None,
) -> dict[str, Any]:
    """Apply the computed label and post the comment.

    Returns a dict of the same shape as the script stdout output.
    """
    label_name = map_score(score, namespace)

    base_result: dict[str, Any] = {
        "applied_label": None,
        "issue_id": None,
        "comment_posted": False,
        "skipped_reason": None,
        "target_label": label_name,
    }

    if not api_key:
        base_result["skipped_reason"] = "no_api_key"
        return base_result

    issue_id = _find_issue_id(ticket_id, api_key)
    if not issue_id:
        base_result["skipped_reason"] = "ticket_not_found"
        return base_result
    base_result["issue_id"] = issue_id

    label_id = _find_label_id(label_name, api_key)
    if not label_id:
        base_result["skipped_reason"] = "label_not_found"
    else:
        prefix = f"council:{namespace}-"
        existing = _get_issue_labels(issue_id, api_key)
        kept_ids = [
            node["id"]
            for node in existing
            if node.get("id") and not (node.get("name") or "").startswith(prefix)
        ]
        if label_id not in kept_ids:
            kept_ids.append(label_id)
        if _update_issue_labels(issue_id, kept_ids, api_key):
            base_result["applied_label"] = label_name

    if comment_body:
        try:
            base_result["comment_posted"] = _create_comment(issue_id, comment_body, api_key)
        except ValueError as exc:
            print(f"warning: commentCreate failed: {exc}", file=sys.stderr)

    return base_result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Apply a council:<namespace>-{go|fix|redo} label to a Linear ticket.",
    )
    p.add_argument("--ticket-id", required=True, help="Linear ticket id (e.g. CAB-2166).")
    p.add_argument(
        "--namespace",
        required=True,
        choices=("ticket", "plan"),
        help="Council namespace for the label.",
    )
    p.add_argument("--score", required=True, help="Council score (float).")
    p.add_argument(
        "--comment-body",
        default="",
        help="Markdown comment body. Pass real newlines, not literal \\n.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        score = float(args.score)
    except ValueError:
        print(f"invalid score: {args.score!r}", file=sys.stderr)
        return 2

    api_key = os.environ.get("LINEAR_API_KEY") or None

    try:
        result = apply_label_and_comment(
            args.ticket_id, args.namespace, score, args.comment_body, api_key
        )
    except (urllib.error.URLError, ValueError) as exc:
        print(f"error: Linear sync failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

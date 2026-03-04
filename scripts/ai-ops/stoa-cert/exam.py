#!/usr/bin/env python3
"""STOA Certified Operator — Exam Runner.

Usage:
    python exam.py --tier associate --candidate "test@example.com"
    python exam.py --tier professional --candidate "ops@stoa.dev" --shuffle
    python exam.py --tier expert --dry-run
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


QUESTIONS_DIR = Path(__file__).parent / "questions"
RESULTS_DIR = Path(__file__).parent / "results"

TIER_FILES = {
    "associate": "associate.yaml",
    "professional": "professional.yaml",
    "expert": "expert.yaml",
}

# ANSI colors for terminal output.
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def load_tier(tier: str) -> dict:
    """Load question bank for the given tier."""
    filename = TIER_FILES.get(tier)
    if not filename:
        print(f"Unknown tier: {tier}. Choose from: {', '.join(TIER_FILES)}")
        sys.exit(1)

    path = QUESTIONS_DIR / filename
    if not path.exists():
        print(f"Question bank not found: {path}")
        sys.exit(1)

    with open(path) as f:
        return yaml.safe_load(f)


def run_exam(
    tier_data: dict,
    candidate: str,
    shuffle: bool = False,
    dry_run: bool = False,
) -> dict:
    """Run an interactive exam session. Returns results dict."""
    questions = tier_data["questions"]
    if shuffle:
        questions = random.sample(questions, len(questions))

    title = tier_data["title"]
    passing_score = tier_data["passing_score"]
    time_limit = tier_data.get("time_limit_minutes", 60)
    total = len(questions)
    required = int(total * passing_score / 100)

    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{CYAN}{'=' * 60}{RESET}")
    print(f"Candidate:     {candidate}")
    print(f"Questions:     {total}")
    print(f"Passing score: {passing_score}% ({required}/{total})")
    print(f"Time limit:    {time_limit} minutes")
    print(f"{CYAN}{'=' * 60}{RESET}\n")

    if dry_run:
        print(f"{YELLOW}DRY RUN — listing questions without interaction{RESET}\n")
        for i, q in enumerate(questions, 1):
            print(f"  {i:2d}. [{q['id']}] {q['category']}: {q['question']}")
            print(f"      Answer: {q['answer']}")
        return {"dry_run": True, "total": total}

    correct = 0
    wrong = []
    start_time = time.time()

    for i, q in enumerate(questions, 1):
        elapsed = time.time() - start_time
        remaining = max(0, time_limit * 60 - elapsed)
        mins_left = int(remaining // 60)

        print(f"{BOLD}Question {i}/{total}{RESET} [{q['id']}] ({q['category']}) — {mins_left}min left")
        print(f"  {q['question']}\n")
        for key in ("a", "b", "c", "d"):
            if key in q["choices"]:
                print(f"    {key}) {q['choices'][key]}")
        print()

        if remaining <= 0:
            print(f"\n{RED}TIME'S UP! Remaining questions marked incorrect.{RESET}")
            wrong.extend(questions[i - 1 :])
            break

        while True:
            answer = input("  Your answer (a/b/c/d): ").strip().lower()
            if answer in ("a", "b", "c", "d"):
                break
            print(f"  {YELLOW}Invalid input. Enter a, b, c, or d.{RESET}")

        if answer == q["answer"]:
            correct += 1
            print(f"  {GREEN}Correct!{RESET}\n")
        else:
            wrong.append(q)
            print(f"  {RED}Wrong.{RESET} Correct answer: {q['answer']}")
            print(f"  {YELLOW}{q['explanation']}{RESET}\n")

    elapsed_total = time.time() - start_time
    score_pct = round(correct / total * 100, 1)
    passed = score_pct >= passing_score

    # Results summary.
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}RESULTS{RESET}")
    print(f"{CYAN}{'=' * 60}{RESET}")
    print(f"Score:    {correct}/{total} ({score_pct}%)")
    print(f"Required: {required}/{total} ({passing_score}%)")
    print(f"Time:     {int(elapsed_total // 60)}m {int(elapsed_total % 60)}s")

    if passed:
        print(f"\n{GREEN}{BOLD}PASSED{RESET} {GREEN}— Congratulations!{RESET}")
    else:
        print(f"\n{RED}{BOLD}FAILED{RESET} {RED}— Review the topics below and try again.{RESET}")

    if wrong:
        print(f"\n{YELLOW}Topics to review:{RESET}")
        categories = {}
        for q in wrong:
            categories.setdefault(q["category"], []).append(q["id"])
        for cat, ids in sorted(categories.items()):
            print(f"  - {cat}: {', '.join(ids)}")

    return {
        "candidate": candidate,
        "tier": tier_data["tier"],
        "title": tier_data["title"],
        "date": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "correct": correct,
        "score_pct": score_pct,
        "passing_score": passing_score,
        "passed": passed,
        "elapsed_seconds": round(elapsed_total, 1),
        "wrong_ids": [q["id"] for q in wrong],
        "wrong_categories": list({q["category"] for q in wrong}),
    }


def save_results(results: dict) -> Path:
    """Save exam results to JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    candidate_slug = results["candidate"].replace("@", "_at_").replace(".", "_")
    filename = f"{ts}-{results['tier']}-{candidate_slug}.json"
    path = RESULTS_DIR / filename

    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="STOA Certified Operator Exam Runner")
    parser.add_argument(
        "--tier",
        required=True,
        choices=list(TIER_FILES),
        help="Certification tier",
    )
    parser.add_argument(
        "--candidate",
        default="anonymous@example.com",
        help="Candidate email address",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Randomize question order",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List questions without running exam",
    )
    args = parser.parse_args()

    tier_data = load_tier(args.tier)
    results = run_exam(
        tier_data,
        candidate=args.candidate,
        shuffle=args.shuffle,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        save_results(results)

    sys.exit(0 if results.get("passed", True) else 1)


if __name__ == "__main__":
    main()

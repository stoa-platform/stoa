"""Check public advisory metadata and dated dependency reviews."""

import argparse
import calendar
import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ACTIONABLE = {"FIX", "WITHDRAWN", "REVIEW_DUE", "REGISTER_ERROR"}


def evaluate(entry, advisory_json, pypi_json, today):
    """Return status names without I/O; absent feeds leave review checks active."""
    review = date.fromisoformat(entry["review_by"])
    month = today.month + 5
    year, month = today.year + month // 12, month % 12 + 1
    horizon = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    if review > min(horizon, date(2027, 2, 1)):
        raise ValueError("Review date exceeds the permitted horizon")
    signals = ["REVIEW_DUE"] if today > review else []
    if advisory_json is not None:
        if not isinstance(advisory_json, dict) or not isinstance(
            advisory_json.get("vulnerabilities"), list
        ):
            raise ValueError("Invalid advisory metadata")
        if advisory_json.get("withdrawn_at"):
            signals.append("WITHDRAWN")
        for item in advisory_json["vulnerabilities"]:
            package = item["package"]
            if (package["name"], package["ecosystem"]) == (entry["package"], entry["ecosystem"]):
                if item.get("first_patched_version"):
                    signals.append("FIX")
    if pypi_json is not None:
        version = pypi_json["info"]["version"]
        if not isinstance(version, str) or not version:
            raise ValueError("Invalid release metadata")
        if version != entry["pinned"]:
            signals.append("NEW_RELEASE")
    return signals


def fetch(url):
    request = Request(url, headers={"User-Agent": "advisory-fix-watch"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, required=True)
    args = parser.parse_args(argv)
    today = date.today()
    lines, statuses = [], set()
    try:
        entries = json.loads(args.register.read_text())
        if not isinstance(entries, list):
            raise ValueError("Invalid register")
        for entry in entries:
            signals = evaluate(entry, None, None, today)
            urls = [
                f"https://api.github.com/advisories/{quote(entry['ghsa'], safe='')}",
                f"https://pypi.org/pypi/{quote(entry['package'], safe='')}/json",
            ]
            for index, url in enumerate(urls):
                try:
                    payload = fetch(url)
                    if not isinstance(payload, dict):
                        raise ValueError("Invalid feed metadata")
                    signals.extend(
                        evaluate(
                            entry,
                            payload if index == 0 else None,
                            payload if index == 1 else None,
                            today,
                        )
                    )
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    signals.append("NETWORK_OR_DATA_ERROR")
            statuses.update(signals)
            lines.append(f"- {entry['ghsa']}: {', '.join(sorted(set(signals))) or 'UNCHANGED'}")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        statuses.add("REGISTER_ERROR")
        lines.append("- REGISTER_ERROR: check the register and mandatory review dates.")
    if "NETWORK_OR_DATA_ERROR" in statuses:
        lines.append("- Feed errors need review if present in three consecutive weekly summaries.")
    summary = "### Advisory tracking\n" + "\n".join(lines) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write(summary)
    for signal in sorted(statuses - ACTIONABLE):
        print(f"::warning::{signal}")
    return 2 if statuses & ACTIONABLE else 0


if __name__ == "__main__":
    raise SystemExit(main())

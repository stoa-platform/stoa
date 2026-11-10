#!/usr/bin/env python3
"""Fail a job unless each required step actually completed successfully."""

import json
import os
import sys


def main():
    try:
        steps = json.loads(os.environ["REQUIRED_STEP_RESULTS"])
        if not isinstance(steps, dict) or not sys.argv[1:]:
            raise ValueError("expected step results and at least one required step")
    except (KeyError, ValueError) as error:
        print(f"::error::Invalid required-step evidence: {error}")
        return 1
    failed = False
    for name in sys.argv[1:]:
        step = steps.get(name, {})
        if not isinstance(step, dict):
            step = {}
        outcome, conclusion = step.get("outcome"), step.get("conclusion")
        if outcome != "success" or conclusion != "success":
            print(f"::error::Required step {name}: outcome={outcome}, conclusion={conclusion}")
            failed = True
        else:
            print(f"Required step {name}: PASS (executed)")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())

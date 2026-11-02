#!/usr/bin/env python3
"""Fail closed unless every quality job succeeded with an approved runtime."""

import json
import os

from check_dependencies import POLICY, PolicyViolation, check_runtime

GATES = {"test", "lint", "dependency", "security", "lambda-modules"}


def verify(results: dict, policy: dict) -> None:
    if set(results) != GATES:
        raise PolicyViolation("missing or unexpected quality gate results")
    for name, result in results.items():
        if result.get("result") != "success":
            raise PolicyViolation(f"quality gate {name}: {result.get('result', 'missing')}; success is required")
    minimums = results["dependency"].get("outputs", {})
    for name, result in results.items():
        for kind, settings in policy["runtimes"].items():
            actual = result.get("outputs", {}).get(f"{kind}-version")
            minimum = minimums.get(f"required-{kind}")
            if not actual or not minimum:
                raise PolicyViolation(f"{name}: missing {kind} runtime evidence")
            check_runtime(kind, actual, minimum, settings["series"])


def main() -> None:
    verify(json.loads(os.environ["QUALITY_RESULTS"]), json.loads(POLICY.read_text()))
    print("All five quality gates succeeded with compliant runtimes.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None

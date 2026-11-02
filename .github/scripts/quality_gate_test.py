"""A skipped/cancelled/missing gate must never unlock deployment outputs."""

import copy
import unittest

from check_dependencies import PolicyViolation
from quality_gate import verify

POLICY = {"runtimes": {"python": {"series": "3.12"}, "node": {"series": "24"}}}


def success() -> dict:
    result = {name: {"result": "success", "outputs": {"python-version": "3.12.15", "node-version": "24.22.0"}}
              for name in ("test", "lint", "dependency", "security", "lambda-modules")}
    result["dependency"]["outputs"].update({"required-python": "3.12.15", "required-node": "24.22.0"})
    return result


class QualityGateTests(unittest.TestCase):
    def test_every_gate_must_succeed(self) -> None:
        verify(success(), POLICY)
        for gate in success():
            for state in ("failure", "skipped", "cancelled", None):
                results = success()
                results[gate]["result"] = state
                with self.subTest(gate=gate, state=state), self.assertRaises(PolicyViolation):
                    verify(results, POLICY)

    def test_missing_gate_and_runtime_outputs_fail(self) -> None:
        results = success()
        del results["security"]
        with self.assertRaises(PolicyViolation):
            verify(results, POLICY)
        for gate in success():
            results = success()
            results[gate]["outputs"] = {}
            with self.assertRaises(PolicyViolation):
                verify(results, POLICY)

    def test_lambda_module_gate_is_required(self) -> None:
        results = success()
        del results["lambda-modules"]
        with self.assertRaisesRegex(PolicyViolation, "missing or unexpected"):
            verify(results, POLICY)

    def test_actual_runtime_in_every_gate_is_checked(self) -> None:
        for gate in success():
            results = copy.deepcopy(success())
            results[gate]["outputs"]["python-version"] = "3.12.1"
            with self.assertRaisesRegex(PolicyViolation, "expired"):
                verify(results, POLICY)

"""The workflow graph preserves required checks and blocks deployment on skips."""

import json
import os
import re
import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def workflow(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text()


class QualityWorkflowTests(unittest.TestCase):
    def test_five_independent_jobs_feed_fail_closed_aggregate(self) -> None:
        content = workflow("reusable-ci.yml")
        for gate in ("test", "lint", "dependency", "security", "lambda-modules"):
            self.assertIn(f"\n  {gate}:\n", content)
        workers, aggregate = content.split("\n  ci:\n")
        self.assertEqual(workers.count("uses: ./.github/workflows/reusable-quality-gate.yml"), 5)
        for gate_name in ("test", "lint", "dependency", "security", "lambda-modules"):
            self.assertIn(f"gate: {gate_name}", workers)
        self.assertIn("GH_TOKEN: ${{ secrets.GH_TOKEN }}", workers)
        self.assertNotIn("continue-on-error", content)
        self.assertIn("if: always()", aggregate)
        self.assertIn("needs: [test, lint, dependency, security, lambda-modules]", aggregate)
        self.assertLess(aggregate.index("quality_gate.py"), aggregate.index("cicd_config.py"))
        gate = workflow("reusable-quality-gate.yml")
        self.assertIn("lambda-modules) python .github/scripts/check_lambda_modules.py", gate)
        self.assertEqual(gate.count("check-latest: true"), 2)
        self.assertIn("python-version: ${{ steps.python.outputs.python-version }}", gate)
        self.assertIn("GH_TOKEN: ${{ secrets.GH_TOKEN }}", gate)

    def test_required_check_names_and_outputs_are_preserved(self) -> None:
        caller, reusable = workflow("cicd.yml"), workflow("reusable-ci.yml")
        self.assertIn("  ci:\n    uses: ./.github/workflows/reusable-ci.yml", caller)
        self.assertIn("name: Regression tests", caller)
        self.assertIn("uses: ./.github/workflows/regression.yml", caller)
        self.assertIn("quality-result: ${{ needs.ci.result }}", caller)
        for name in ("cdk-enabled", "cdk-region", "preview-environment-enabled", "preview-orphan-audit-enabled", "development-enabled", "staging-enabled", "production-enabled"):
            self.assertIn(f"value: ${{{{ jobs.ci.outputs.{name} }}}}", reusable)
            self.assertIn(f"{name}: ${{{{ steps.config.outputs.{name.replace('-', '_')} }}}}", reusable)
        for environment in ("stg", "prod"):
            rules = json.loads((ROOT / f".github/rulesets/{environment}.json").read_text())
            checks = next(rule["parameters"]["required_status_checks"] for rule in rules["rules"] if rule["type"] == "required_status_checks")
            self.assertIn({"context": "Regression tests / regression"}, checks)

    def test_compatibility_check_rejects_failed_skipped_and_cancelled_results(self) -> None:
        script = textwrap.dedent(workflow("regression.yml").split("run: |\n", 1)[1])
        for state, expected in (("success", 0), ("failure", 1), ("skipped", 1), ("cancelled", 1), ("", 1)):
            result = subprocess.run(["bash", "-e", "-c", script], env={**os.environ, "QUALITY_RESULT": state}, capture_output=True)
            self.assertEqual(result.returncode, expected)

    def test_single_entrypoint_and_all_aws_jobs_depend_on_ci(self) -> None:
        caller = workflow("cicd.yml")
        self.assertIn("  push:\n  workflow_dispatch:", caller)
        self.assertIn("  pull_request:", caller)
        self.assertNotIn("  push:", workflow("regression.yml"))
        self.assertIn("test) python .github/scripts/run_regression.py", workflow("reusable-quality-gate.yml"))
        self.assertIn("lambda-modules) python .github/scripts/check_lambda_modules.py", workflow("reusable-quality-gate.yml"))
        self.assertIn("python .github/scripts/check_lambda_modules.py", workflow("reusable-quality-gate.yml"))
        for job in ("preview", "preview-environment", "deploy-development", "deploy-staging", "deploy-production"):
            section = re.split(r"\n  [\w-]+:\n", caller.split(f"\n  {job}:\n", 1)[1])[0]
            self.assertIn("needs: ", section)
            self.assertRegex(section, r"needs: (ci|\[ci, preview\])")
            self.assertNotIn("always()", section)
        self.assertIn("uses: ./.github/workflows/reusable-deploy-staging.yml", caller)
        self.assertIn("uses: ./.github/workflows/reusable-deploy-production.yml", caller)
        config = json.loads((ROOT / ".github/cicd/application.json").read_text())
        self.assertFalse(config["cdk"]["enabled"])
        self.assertFalse(config["cdk"]["previewEnvironmentEnabled"])
        self.assertFalse(config["cdk"]["previewOrphanAuditEnabled"])
        self.assertFalse(any(config["deployments"].values()))

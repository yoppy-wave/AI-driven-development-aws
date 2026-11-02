"""Tests for the AWS CDK CI/CD configuration contract."""

import json
import tempfile
import unittest
from pathlib import Path

import cicd_config


class CicdConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_path = self.root / ".github" / "cicd" / "application.json"

    def valid(self) -> dict[str, object]:
        return {"version": 1, "application": {"name": "app"}, "ci": {"enabled": True}, "cdk": {"enabled": False, "region": "us-east-1", "previewEnvironmentEnabled": False, "previewOrphanAuditEnabled": False}, "deployments": {"development": False, "staging": False, "production": False}}

    def write(self, config: dict[str, object], with_cdk: bool = False) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        if with_cdk:
            (self.root / "cdk.json").write_text("{}", encoding="utf-8")

    def test_disabled_cdk_is_valid_without_cdk_project(self) -> None:
        self.write(self.valid())
        self.assertEqual(cicd_config.load(self.config_path)["version"], 1)

    def test_preview_requires_cdk(self) -> None:
        config = self.valid()
        config["cdk"]["previewEnvironmentEnabled"] = True
        self.write(config)
        with self.assertRaisesRegex(ValueError, "requires cdk.enabled"):
            cicd_config.load(self.config_path)

    def test_orphan_audit_requires_cdk_but_not_preview_deployments(self) -> None:
        config = self.valid()
        config["cdk"]["enabled"] = True
        config["cdk"]["previewOrphanAuditEnabled"] = True
        self.write(config, with_cdk=True)
        self.assertEqual(cicd_config.values(cicd_config.load(self.config_path))["preview_orphan_audit_enabled"], "true")

        config["cdk"]["enabled"] = False
        self.write(config)
        with self.assertRaisesRegex(ValueError, "previewOrphanAuditEnabled requires cdk.enabled"):
            cicd_config.load(self.config_path)

    def test_enabled_deployment_requires_cdk(self) -> None:
        config = self.valid()
        config["deployments"]["development"] = True
        self.write(config)
        with self.assertRaisesRegex(ValueError, "require cdk.enabled"):
            cicd_config.load(self.config_path)

    def test_enabled_cdk_requires_cdk_json(self) -> None:
        config = self.valid()
        config["cdk"]["enabled"] = True
        self.write(config)
        with self.assertRaisesRegex(ValueError, "cdk.json"):
            cicd_config.load(self.config_path)

    def test_configuration_does_not_generate_pr_number_stack_names(self) -> None:
        self.assertNotIn("preview_stack", cicd_config.values(self.valid()))

    def test_application_name_cannot_drift_from_stack_namespace(self) -> None:
        config = self.valid()
        config["application"]["name"] = "other"
        self.write(config)
        with self.assertRaisesRegex(ValueError, "must be app"):
            cicd_config.load(self.config_path)

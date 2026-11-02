#!/usr/bin/env python3
"""Validate and expose the repository CI/CD configuration."""

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / ".github" / "cicd" / "application.json"
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


def fail(message: str) -> None:
    raise ValueError(message)


def required_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        fail(f"{name} must be an object")
    return value


def required_string(section: dict[str, object], key: str, name: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        fail(f"{name}.{key} must be a non-empty string")
    return value


def required_bool(section: dict[str, object], key: str, name: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        fail(f"{name}.{key} must be a boolean")
    return value


def load(path: Path = CONFIG_PATH) -> dict[str, object]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"CI/CD configuration is missing: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as error:
        fail(f"CI/CD configuration is not valid JSON: {error.msg}")
    return validate(required_object(config, "configuration"), path.parents[2])


def validate(config: dict[str, object], root: Path = ROOT) -> dict[str, object]:
    if config.get("version") != 1:
        fail("version must be 1")

    application = required_object(config.get("application"), "application")
    name = required_string(application, "name", "application")
    if name != "app":
        fail("application.name must be app so CDK and cleanup use the same stack namespace")

    ci = required_object(config.get("ci"), "ci")
    required_bool(ci, "enabled", "ci")

    cdk = required_object(config.get("cdk"), "cdk")
    enabled = required_bool(cdk, "enabled", "cdk")
    region = required_string(cdk, "region", "cdk")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]+", region):
        fail("cdk.region must be an AWS region identifier")
    preview_enabled = required_bool(cdk, "previewEnvironmentEnabled", "cdk")
    if preview_enabled and not enabled:
        fail("cdk.previewEnvironmentEnabled requires cdk.enabled to be true")
    orphan_audit_enabled = required_bool(cdk, "previewOrphanAuditEnabled", "cdk")
    if orphan_audit_enabled and not enabled:
        fail("cdk.previewOrphanAuditEnabled requires cdk.enabled to be true")
    if enabled and not (root / "cdk.json").is_file():
        fail("cdk.json must exist when cdk.enabled is true")

    deployments = required_object(config.get("deployments"), "deployments")
    for environment in ("development", "staging", "production"):
        required_bool(deployments, environment, "deployments")
    if any(deployments.values()) and not enabled:
        fail("enabled deployments require cdk.enabled to be true")

    return config


def values(config: dict[str, object]) -> dict[str, str]:
    application = required_object(config["application"], "application")
    ci = required_object(config["ci"], "ci")
    cdk = required_object(config["cdk"], "cdk")
    deployments = required_object(config["deployments"], "deployments")
    result = {
        "application_name": str(application["name"]),
        "ci_enabled": str(ci["enabled"]).lower(),
        "cdk_enabled": str(cdk["enabled"]).lower(),
        "cdk_region": str(cdk["region"]),
        "preview_environment_enabled": str(cdk["previewEnvironmentEnabled"]).lower(),
        "preview_orphan_audit_enabled": str(cdk["previewOrphanAuditEnabled"]).lower(),
        "development_enabled": str(deployments["development"]).lower(),
        "staging_enabled": str(deployments["staging"]).lower(),
        "production_enabled": str(deployments["production"]).lower(),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "github-output", "json"))
    args = parser.parse_args()
    config = load()
    output = values(config)
    if args.command == "validate":
        print("CI/CD configuration is valid.")
    elif args.command == "github-output":
        for key, value in output.items():
            print(f"{key}={value}")
    else:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error)) from None

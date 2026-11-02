#!/usr/bin/env python3
"""Report preview stacks whose owning pull request is closed or renamed."""

import json
import re

import preview_cleanup as preview


def audit(region: str, role_arn: str, repository: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    partition, account = preview.validate_identity(region, role_arn)
    response = json.loads(preview.aws(region, "cloudformation", "list-stacks"))
    findings: list[str] = []
    for summary in response.get("StackSummaries", []):
        if summary.get("StackStatus") in {"DELETE_COMPLETE", "DELETE_IN_PROGRESS"}:
            continue
        name = summary.get("StackName", "")
        if not isinstance(name, str) or not name.startswith("app-"):
            continue
        stack = preview.describe_stack(region, name)
        if stack is None:
            continue
        if stack.get("StackName") != name:
            raise ValueError(f"CloudFormation stack name does not match: {name}")
        stack_id = stack.get("StackId", "")
        if not stack_id.startswith(f"arn:{partition}:cloudformation:{region}:{account}:stack/{name}/"):
            raise ValueError(f"CloudFormation stack identity does not match: {name}")
        tags = {tag["Key"]: tag["Value"] for tag in stack.get("Tags", [])}
        if tags.get("app:managed-by") != preview.MANAGED_BY:
            continue
        environment = tags.get("app:environment", "")
        if not re.fullmatch(r"pr-[1-9][0-9]*", environment):
            continue
        pr_value = tags.get("app:preview-pr", "")
        if not re.fullmatch(r"[1-9][0-9]*", pr_value) or pr_value != environment.removeprefix("pr-"):
            findings.append(f"{name}: invalid or missing preview PR ownership tag")
            continue
        pr_number = int(pr_value)
        try:
            current = json.loads(preview.run([
                "gh", "api", f"repos/{repository}/pulls/{pr_number}"
            ]))
        except RuntimeError as error:
            if "HTTP 404" in str(error) or "Not Found" in str(error):
                findings.append(f"{name}: owning PR #{pr_number} no longer exists")
                continue
            raise
        if current.get("state") != "open":
            findings.append(f"{name}: owning PR #{pr_number} is {current.get('state', 'unknown')}")
        else:
            branch = current.get("head", {}).get("ref")
            if not isinstance(branch, str) or preview.preview_stack_name(branch) != name:
                findings.append(f"{name}: owning PR #{pr_number} now uses a different branch name")
    return findings


def main() -> None:
    import os

    findings = audit(
        os.environ["REGION"],
        os.environ["AWS_ROLE_TO_ASSUME"],
        os.environ["GITHUB_REPOSITORY"],
    )
    if findings:
        for finding in findings:
            print(finding)
        raise SystemExit(1)
    print("Preview stack audit passed; no orphaned managed stacks found.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
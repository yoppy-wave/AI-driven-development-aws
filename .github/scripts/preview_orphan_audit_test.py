"""The preview audit is read-only and reports ownership mismatches."""

import json
import unittest
from unittest.mock import patch

import preview_cleanup as preview
import preview_orphan_audit as audit_module


REGION = "us-east-1"
ACCOUNT = "123456789012"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/preview-audit"
NAME = "app-feature-login"
STACK = {
    "StackName": NAME,
    "StackId": f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{NAME}/unique-id",
    "StackStatus": "UPDATE_COMPLETE",
    "Tags": [
        {"Key": "app:managed-by", "Value": preview.MANAGED_BY},
        {"Key": "app:environment", "Value": "pr-42"},
        {"Key": "app:preview-pr", "Value": "42"},
    ],
}


class PreviewOrphanAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aws_patcher = patch.object(audit_module.preview, "aws", side_effect=self.call_aws)
        self.aws = self.aws_patcher.start()
        self.addCleanup(self.aws_patcher.stop)
        self.describe_patcher = patch.object(audit_module.preview, "describe_stack", return_value=STACK)
        self.describe = self.describe_patcher.start()
        self.addCleanup(self.describe_patcher.stop)
        self.github_patcher = patch.object(
            audit_module.preview,
            "run",
            return_value=json.dumps({"state": "open", "head": {"ref": "feature/login"}}),
        )
        self.github = self.github_patcher.start()
        self.addCleanup(self.github_patcher.stop)
        self.calls: list[tuple[str, ...]] = []

    def call_aws(self, region: str, *args: str) -> str:
        self.calls.append(args)
        if args == ("sts", "get-caller-identity"):
            return json.dumps({"Account": ACCOUNT})
        if args[0:2] == ("cloudformation", "list-stacks"):
            return json.dumps({"StackSummaries": [{"StackName": NAME, "StackStatus": "UPDATE_COMPLETE"}]})
        raise AssertionError(f"Unexpected AWS operation: {args}")

    def test_open_matching_pr_has_no_findings_and_never_mutates_cloudformation(self) -> None:
        with patch.object(audit_module.preview, "preview_stack_name", return_value=NAME):
            self.assertEqual(audit_module.audit(REGION, ROLE, "owner/repo"), [])
        self.assertTrue(all("delete" not in call for call in self.calls))

    def test_closed_pr_is_reported_without_deleting_stack(self) -> None:
        self.github.return_value = json.dumps({"state": "closed", "head": {"ref": "feature/login"}})
        result = audit_module.audit(REGION, ROLE, "owner/repo")
        self.assertEqual(result, [f"{NAME}: owning PR #42 is closed"])
        self.assertTrue(all("delete" not in call for call in self.calls))

    def test_invalid_identity_and_repository_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "repository"):
            audit_module.audit(REGION, ROLE, "invalid")
        with self.assertRaisesRegex(ValueError, "AWS account"):
            with patch.object(audit_module.preview, "aws", return_value=json.dumps({"Account": "999999999999"})):
                audit_module.audit(REGION, ROLE, "owner/repo")

    def test_shared_stack_is_ignored_even_when_managed_by_this_application(self) -> None:
        shared = {
            **STACK,
            "StackName": "app-production",
            "StackId": f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/app-production/id",
            "Tags": [
                {"Key": "app:managed-by", "Value": preview.MANAGED_BY},
                {"Key": "app:environment", "Value": "production"},
            ],
        }
        self.aws.side_effect = lambda region, *args: (
            json.dumps({"Account": ACCOUNT})
            if args == ("sts", "get-caller-identity")
            else json.dumps({"StackSummaries": [{"StackName": "app-production", "StackStatus": "UPDATE_COMPLETE"}]})
        )
        self.describe.return_value = shared
        self.assertEqual(audit_module.audit(REGION, ROLE, "owner/repo"), [])
        self.github.assert_not_called()

    def test_deleted_stack_summary_is_ignored(self) -> None:
        self.aws.side_effect = lambda region, *args: (
            json.dumps({"Account": ACCOUNT})
            if args == ("sts", "get-caller-identity")
            else json.dumps({"StackSummaries": [{"StackName": NAME, "StackStatus": "DELETE_COMPLETE"}]})
        )
        self.assertEqual(audit_module.audit(REGION, ROLE, "owner/repo"), [])
        self.describe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
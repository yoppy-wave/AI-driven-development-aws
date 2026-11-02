"""The AWS CI/CD workflow contract must preserve preview safety boundaries."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(path: str) -> str:
    return (WORKFLOWS / path).read_text(encoding="utf-8")


class CicdWorkflowTests(unittest.TestCase):
    def test_reusable_workflows_are_supported_and_called(self) -> None:
        for name in ("reusable-ci.yml", "reusable-aws-cdk.yml"):
            self.assertIn("workflow_call:", workflow(name))
        self.assertEqual(workflow("cicd.yml").count("uses: ./.github/workflows/reusable-aws-cdk.yml"), 3)
        for name, stack, environment in (
            ("reusable-deploy-staging.yml", "app-staging", "staging"),
            ("reusable-deploy-production.yml", "app-production", "production"),
        ):
            deployment = workflow(name)
            self.assertIn("uses: ./.github/workflows/reusable-aws-cdk.yml", deployment)
            self.assertIn(f"stack-name: {stack}", deployment)
            self.assertIn(f"github-environment: {environment}", deployment)
            self.assertIn("workflow_call:", deployment)

    def test_update_and_close_cleanup_share_a_queued_pr_lock(self) -> None:
        for content in (workflow("cicd.yml"), workflow("cicd-preview-cleanup.yml")):
            self.assertIn("group: preview-${{ github.event.pull_request.number", content)
            self.assertIn("cancel-in-progress: false", content)
            self.assertIn("queue: max", content)

    def test_preview_requires_trusted_pr_and_environment_gate(self) -> None:
        content = workflow("cicd.yml")
        self.assertEqual(content.count("head.repo.fork == false"), 2)
        self.assertIn("contains(fromJSON('[\"OWNER\",\"MEMBER\",\"COLLABORATOR\"]')", content)
        self.assertIn("github-environment: preview", content)
        self.assertNotIn("secrets: inherit", content)

    def test_aws_oidc_is_limited_to_aws_operation_jobs(self) -> None:
        self.assertIn("aws-actions/configure-aws-credentials@v5", workflow("reusable-aws-cdk.yml"))
        self.assertEqual(workflow("cicd.yml").count("id-token: write"), 5)
        self.assertIn("      id-token: write", workflow("cicd-preview-cleanup.yml"))

    def test_preview_does_not_need_comment_write_permissions(self) -> None:
        adapter = workflow("reusable-aws-cdk.yml")
        self.assertNotIn("permissions:", adapter)
        cicd = workflow("cicd.yml")
        for content in (cicd, workflow("cicd-preview-cleanup.yml")):
            self.assertNotIn("issues: write", content)
            self.assertNotIn("pull-requests: write", content)
            self.assertIn("pull-requests: read", content)

    def test_preview_rechecks_pr_state_and_head_before_aws(self) -> None:
        adapter = workflow("reusable-aws-cdk.yml")
        self.assertEqual(adapter.count("Confirm pull request is current"), 3)
        self.assertLess(adapter.index("Confirm pull request is current before AWS operation"), adapter.index("Configure AWS credentials with OIDC"))

    def test_cleanup_never_checks_out_or_executes_pr_source(self) -> None:
        cleanup = workflow("cicd-preview-cleanup.yml")
        self.assertIn("pull_request_target:", cleanup)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", cleanup)
        self.assertIn("management-ref: ${{ steps.management.outputs.commit }}", cleanup)
        self.assertIn("ref: ${{ needs.cleanup-target.outputs.management-ref }}", cleanup)
        self.assertNotIn("github.event.pull_request.head.sha", cleanup)
        self.assertNotIn("npm ci", cleanup)
        self.assertNotIn("npm run cdk", cleanup)

    def test_weekly_preview_audit_is_read_only_and_disabled_before_aws_auth(self) -> None:
        audit = workflow("preview-orphan-audit.yml")
        helper = (ROOT / ".github/scripts/preview_orphan_audit.py").read_text(encoding="utf-8")
        self.assertIn("schedule:", audit)
        self.assertIn("preview_orphan_audit_enabled", audit)
        self.assertIn("if: needs.configuration.outputs.enabled == 'true'", audit)
        self.assertLess(audit.index("outputs.enabled"), audit.index("configure-aws-credentials"))
        self.assertIn("environment:\n      name: preview-audit", audit)
        self.assertIn("id-token: write", audit)
        for forbidden in ("delete-stack", "cdk deploy", "cdk destroy"):
            self.assertNotIn(forbidden, helper)

    def test_pull_request_policy_checks_out_and_executes_the_trusted_base_commit(self) -> None:
        policy = workflow("pull-request-policy.yml")
        checkout = "uses: actions/checkout@v7\n        with:\n          ref: ${{ github.event.pull_request.base.sha }}\n          persist-credentials: false"
        self.assertIn("pull_request_target:", policy)
        self.assertIn(checkout, policy)
        self.assertLess(policy.index(checkout), policy.index("run: python .github/scripts/pr_policy.py"))
        self.assertNotIn("github.event.pull_request.head.sha", policy)

    def test_cleanup_validates_cloudformation_identity_and_tags_before_delete(self) -> None:
        cleanup = workflow("cicd-preview-cleanup.yml")
        self.assertIn("python .github/scripts/preview_cleanup.py cleanup", cleanup)
        helper = (ROOT / ".github/scripts/preview_cleanup.py").read_text(encoding="utf-8")
        for required in ("get-caller-identity", "describe-stacks", "app:managed-by", "app:preview-pr", "DELETE_IN_PROGRESS", "delete-stack", "stack-delete-complete"):
            self.assertIn(required, helper)

    def test_cleanup_handles_reopened_pr_and_missing_stack_idempotently(self) -> None:
        cleanup = workflow("cicd-preview-cleanup.yml")
        for required in ("Confirm pull request remains closed", "steps.current-pr.outputs.allowed == 'true'"):
            self.assertIn(required, cleanup)

    def test_disabled_cleanup_never_reaches_environment_or_aws_authentication(self) -> None:
        cleanup = workflow("cicd-preview-cleanup.yml")
        self.assertIn("python .github/scripts/cicd_config.py github-output", cleanup)
        self.assertIn("if: needs.cleanup-target.outputs.enabled == 'true' && needs.cleanup-target.outputs.cleanup-allowed == 'true'", cleanup)
        target, aws_job = cleanup.split("\n  cleanup:\n")
        self.assertNotIn("configure-aws-credentials", target)
        self.assertNotIn("id-token: write", target)
        self.assertIn("environment:\n      name: preview", aws_job)

    def test_preview_stack_is_resolved_from_branch_and_passed_to_cdk(self) -> None:
        caller = workflow("cicd.yml")
        self.assertEqual(caller.count("preview-branch: ${{ github.event.pull_request.head.ref }}"), 2)
        self.assertIn("needs: [ci, preview]", caller)
        self.assertIn("operation: diff", caller)
        self.assertIn("operation: deploy", caller)
        adapter = workflow("reusable-aws-cdk.yml")
        self.assertIn('preview_cleanup.py stack-name --branch "$PREVIEW_BRANCH"', adapter)
        self.assertIn('cdk_args+=(--context "previewBranch=$PREVIEW_BRANCH")', adapter)
        self.assertIn("STACK_NAME: ${{ steps.target.outputs.stack_name }}", adapter)
        self.assertLess(adapter.index("Verify preview stack ownership"), adapter.index("- name: Run CDK operation"))

    def test_preview_has_no_comment_state_recording_or_restoration(self) -> None:
        for name in ("cicd.yml", "cicd-preview-cleanup.yml", "reusable-aws-cdk.yml"):
            content = workflow(name)
            for forbidden in ("/comments", "record-preview-cleanup", "record-body", "update-body", "app-pr-", "trusted-workflow-ref"):
                self.assertNotIn(forbidden, content)
        helper = (ROOT / ".github/scripts/preview_cleanup.py").read_text(encoding="utf-8")
        for forbidden in ("MARKER", "comment_body", "latest_target", "STATUSES"):
            self.assertNotIn(forbidden, helper)

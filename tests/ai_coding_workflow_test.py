"""The AI coding workflow must use Azure OpenAI through Cline CLI."""

import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ai-coding.yml"


class AiCodingWorkflowTests(unittest.TestCase):
    def test_trusted_pr_comment_can_request_a_follow_up_fix(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("issue_comment:", content)
        self.assertIn("github.event.comment.body == '/cline fix'", content)
        self.assertIn("startsWith(github.event.comment.body, '/cline fix ')", content)
        self.assertIn("github.event.issue.pull_request != null", content)
        self.assertIn("github.event.comment.author_association", content)
        self.assertIn("github.event.comment.user.type != 'Bot'", content)
        self.assertIn("github.event.comment.user.login != 'github-actions[bot]'", content)
        self.assertIn("Validate PR and retrieve its changed files", content)
        self.assertIn(".head.repo.full_name == $repository", content)
        self.assertIn('if [[ -n "$PR_NUMBER" ]]', content)
        self.assertIn('cp .github/scripts/ai_coding.py "$HOME/.cline/hooks/PreToolUse.py"', content)

    def test_pr_source_is_not_checked_out_or_executed(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", content)
        self.assertIn("gh api --paginate --slurp", content)
        self.assertNotIn("ref: ${{ github.event.pull_request.head.sha }}", content)
        self.assertNotIn("checkout@v7\n        with:\n          ref: ${{ github.event.issue.pull_request", content)

    def test_azure_openai_is_configured_for_headless_cline(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("AZURE_OPENAI_API_KEY: ${{ secrets.AZURE_OPENAI_API_KEY }}", content)
        self.assertIn("AZURE_OPENAI_ENDPOINT: ${{ vars.AZURE_OPENAI_ENDPOINT }}", content)
        self.assertIn("AZURE_OPENAI_DEPLOYMENT: ${{ vars.AZURE_OPENAI_DEPLOYMENT }}", content)
        self.assertIn("cline auth --provider openai-native --apikey", content)
        self.assertIn("--modelid \"$AZURE_OPENAI_DEPLOYMENT\"", content)
        self.assertIn("--baseurl \"$AZURE_OPENAI_ENDPOINT\"", content)
        self.assertIn("--provider openai-native --model \"$AZURE_OPENAI_DEPLOYMENT\"", content)
        self.assertNotIn("secrets.OPENAI_API_KEY", content)
        self.assertNotIn("--provider openai --model", content)


if __name__ == "__main__":
    unittest.main()
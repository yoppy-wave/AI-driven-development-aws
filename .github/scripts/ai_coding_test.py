"""Regression checks for ai_coding helpers."""

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_coding


class AiCodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.temp_path = Path(self.temp.name)
        self.environment = patch.dict(
            os.environ,
            {
                "RUNNER_TEMP": self.temp.name,
                "GITHUB_WORKSPACE": self.temp.name,
                "ISSUE_NUMBER": "42",
                "ISSUE_TITLE": "境界値を確認",
                "ISSUE_BODY": "0件の場合は？",
                "AZURE_OPENAI_API_KEY": "test-secret-token",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write_events(self, text: str) -> None:
        events = [
            {"type": "agent_event", "event": {"type": "content_end", "text": "途中経過"}},
            {"type": "agent_event", "event": {"type": "done", "reason": "completed", "text": text}},
            {"type": "run_result", "finishReason": "completed", "text": text},
        ]
        (self.temp_path / "ai-coding-events.ndjson").write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in events),
            encoding="utf-8",
        )

    def test_extract_rejects_github_configuration_changes(self) -> None:
        self.write_events("変更内容: 実装しました。")
        with patch.object(
            ai_coding, "changed_paths", return_value=[Path(".github/workflows/ai-coding.yml")]
        ):
            with self.assertRaises(SystemExit):
                ai_coding.extract()
        self.assertFalse((self.temp_path / "ai-coding-pr-body.md").exists())

    def test_extract_rejects_token_in_summary(self) -> None:
        self.write_events("test-secret-token")
        with self.assertRaises(SystemExit):
            ai_coding.extract()
        self.assertFalse((self.temp_path / "ai-coding-pr-body.md").exists())

    def test_prepare_and_extract_create_reviewable_pr_body(self) -> None:
        ai_coding.prepare()
        prompt = (self.temp_path / "ai-coding-prompt.txt").read_text(encoding="utf-8")
        self.assertIn('"number": "42"', prompt)
        self.write_events("変更内容: 境界値を修正。\n確認: テスト成功。")
        with patch.object(ai_coding, "changed_paths", return_value=[]):
            ai_coding.extract()
        body = (self.temp_path / "ai-coding-pr-body.md").read_text(encoding="utf-8")
        self.assertIn("対象issue: #42", body)
        self.assertIn("確認: テスト成功。", body)

    def test_prepare_pr_mode_uses_comment_and_patch_as_untrusted_data(self) -> None:
        (self.temp_path / "ai-coding-pr-files.json").write_text(
            json.dumps([{"filename": "src/example.py", "patch": "@@ -1 +1 @@"}]),
            encoding="utf-8",
        )
        with patch.dict(
            os.environ,
            {"PR_NUMBER": "42", "PR_COMMENT_BODY": "/cline fix handle empty input"},
        ):
            ai_coding.prepare()
        prompt = (self.temp_path / "ai-coding-prompt.txt").read_text(encoding="utf-8")
        self.assertIn('"pull_request"', prompt)
        self.assertIn("/cline fix handle empty input", prompt)
        self.assertIn('"filename": "src/example.py"', prompt)
        self.assertIn("PRブランチをcheckoutせず", prompt)

    def test_extract_pr_mode_does_not_require_issue_number(self) -> None:
        self.write_events("変更内容: PRの問題を修正しました。")
        with patch.dict(os.environ, {"PR_NUMBER": "42"}, clear=False), patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("ISSUE_NUMBER", None)
            with patch.object(ai_coding, "changed_paths", return_value=[]):
                ai_coding.extract()
        body = (self.temp_path / "ai-coding-pr-body.md").read_text(encoding="utf-8")
        self.assertIn("対象PR: #42", body)

    def test_prepare_pr_mode_rejects_missing_or_oversized_file_data(self) -> None:
        with patch.dict(os.environ, {"PR_NUMBER": "42"}), self.assertRaises(SystemExit):
            ai_coding.prepare()

    def test_pr_guard_blocks_commands_and_allows_only_workspace_edits(self) -> None:
        allowed_write = {
            "tool_call": {
                "name": "write_to_file",
                "input": {"path": str(self.temp_path / "src" / "fix.py"), "content": "ok"},
            }
        }
        blocked = (
            {"tool_call": {"name": "execute_command", "input": {"command": "env"}}},
            {"tool_call": {"name": "write_to_file", "input": {"path": "/tmp/outside.py"}}},
            {"tool_call": {"name": "write_to_file", "input": {"path": str(self.temp_path / ".github/workflows/ci.yml")}}},
            {"tool_call": {"name": "browser", "input": {"url": "https://example.com"}}},
        )
        for event in blocked:
            with self.subTest(event=event), patch("sys.stdin", io.StringIO(json.dumps(event))), patch(
                "sys.stdout", new_callable=io.StringIO
            ) as output:
                ai_coding.guard_tool()
                self.assertTrue(json.loads(output.getvalue())["cancel"])
        with patch("sys.stdin", io.StringIO(json.dumps(allowed_write))), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as output:
            ai_coding.guard_tool()
            self.assertFalse(json.loads(output.getvalue())["cancel"])

    def test_hook_script_defaults_to_pre_tool_use_mode(self) -> None:
        event = {"tool_call": {"name": "execute_command", "input": {"command": "env"}}}
        result = subprocess.run(
            [sys.executable, str(Path(ai_coding.__file__))],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            env={**os.environ, "GITHUB_WORKSPACE": self.temp.name},
            check=True,
        )
        self.assertTrue(json.loads(result.stdout)["cancel"])


if __name__ == "__main__":
    unittest.main()
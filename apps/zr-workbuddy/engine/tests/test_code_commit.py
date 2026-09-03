"""code_commit P0-2 单元测试（不真正 push / 不依赖 LLM）。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class CodeCommitTests(unittest.TestCase):
    def test_intent_commit(self):
        from app.code_commit.intent import is_code_commit_question

        self.assertTrue(is_code_commit_question("提交代码"))
        self.assertTrue(is_code_commit_question("提交今天的代码"))
        self.assertTrue(is_code_commit_question("请帮我 git commit"))
        self.assertFalse(is_code_commit_question("审核代码"))
        self.assertFalse(is_code_commit_question("帮我写一个消息中心页面"))
        self.assertFalse(is_code_commit_question("今天产量多少"))

    def test_gate_blocks_env(self):
        from app.code_commit.gate import run_commit_review_gate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            out = run_commit_review_gate(
                root,
                [".env", "app.py"],
                use_skill_review=False,
                allow_blocked_override=False,
            )
            self.assertTrue(out.get("ok"))
            self.assertFalse(out.get("can_commit"))
            self.assertGreaterEqual(out.get("blocking_count") or 0, 1)
            paths = [f.get("path") for f in (out.get("findings") or []) if f.get("blocking")]
            self.assertTrue(any(p == ".env" or (p or "").endswith(".env") for p in paths))

    def test_branch_rejects_refspec_injection(self):
        from app.code_commit.git_ops import validate_branch_name

        self.assertFalse(validate_branch_name("feature:main")[0])
        self.assertFalse(validate_branch_name("main")[0])
        self.assertFalse(validate_branch_name("-evil")[0])
        self.assertTrue(validate_branch_name("feature/demo")[0])

    def test_gate_content_regex_even_with_fake_skill(self):
        """Skill 返回空 findings 时仍须本地正则拦住 eval。"""
        from app.code_commit import gate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _eval_fn = "ev" + "al"
            (root / "bad.py").write_text(f"{_eval_fn}(user_input)\n", encoding="utf-8")

            def fake_skill(_ws, _files):
                return {
                    "ok": True,
                    "provider": "commit-batch-review-skill",
                    "review_method": "fake",
                    "process_steps": [],
                    "findings": [],
                    "file_scans": [{"path": "bad.py", "status": "pass", "steps": [], "issues": []}],
                    "summary": "假通过",
                    "verdict": "pass",
                }

            with mock.patch(
                "app.code_commit.skill_review.run_commit_batch_skill_review",
                side_effect=fake_skill,
            ):
                out = gate.run_commit_review_gate(
                    root,
                    ["bad.py"],
                    use_skill_review=True,
                    allow_blocked_override=False,
                )
            self.assertFalse(out.get("can_commit"))
            self.assertTrue(any(f.get("blocking") for f in (out.get("findings") or [])))
            self.assertIn("禁止提交", out.get("summary") or "")
            self.assertNotIn("确认后可提交", out.get("summary") or "")
            self.assertNotIn("假通过", out.get("summary") or "")

    def test_resolve_branch_prefers_current(self):
        from app.code_commit.git_ops import resolve_work_branch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import subprocess

            subprocess.run(["git", "init", "-b", "feature/demo"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
            (root / "a.txt").write_text("1\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

            self.assertEqual(resolve_work_branch(workspace=root, work_branch=""), "feature/demo")
            self.assertEqual(resolve_work_branch(workspace=root, work_branch="my/feat"), "my/feat")

    def test_preview_commit_branch_priority(self):
        from app.code_commit.ops import preview_commit_branch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import subprocess

            subprocess.run(["git", "init", "-b", "feature/demo"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
            (root / "a.txt").write_text("1\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

            cur = preview_commit_branch(str(root))
            self.assertEqual(cur.get("work_branch"), "feature/demo")
            self.assertEqual(cur.get("branch_source"), "current")
            self.assertFalse(cur.get("need_user_branch"))

            user = preview_commit_branch(str(root), user_branch="feat/manual")
            self.assertEqual(user.get("work_branch"), "feat/manual")
            self.assertEqual(user.get("branch_source"), "user")

            # 保护分支：无配置 → 需手填；有配置 → 用配置
            subprocess.run(["git", "checkout", "-b", "main"], cwd=root, check=True, capture_output=True)
            with mock.patch("app.code_commit.ops.get_config") as gc:
                cfg = mock.Mock()
                cfg.work_branch = ""
                gc.return_value = cfg
                prot = preview_commit_branch(str(root))
                self.assertTrue(prot.get("need_user_branch"))
                self.assertEqual(prot.get("work_branch"), "")

                cfg.work_branch = "dev/from-config"
                cfg2 = preview_commit_branch(str(root))
                self.assertEqual(cfg2.get("work_branch"), "dev/from-config")
                self.assertEqual(cfg2.get("branch_source"), "config")
                self.assertFalse(cfg2.get("need_user_branch"))

    def test_chinese_message_validation(self):
        from app.code_commit.git_ops import validate_chinese_commit_message

        ok, err = validate_chinese_commit_message("")
        self.assertFalse(ok)
        self.assertIn("中文", err)

        ok, err = validate_chinese_commit_message("fix bug")
        self.assertFalse(ok)

        ok, err = validate_chinese_commit_message("修复登录超时问题")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_fix_from_gate_intent_and_prepare(self):
        from app.code_commit.intent import is_fix_from_gate_question, is_code_commit_question
        from app.code_commit.ops import build_fix_requirement, prepare_fix_from_gate
        from app.code_commit.store import save_job

        self.assertTrue(is_fix_from_gate_question("修复这些问题"))
        self.assertTrue(is_fix_from_gate_question("【门禁阻断修复】job_id=cc-abc"))
        self.assertFalse(is_code_commit_question("修复这些问题"))

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            job = {
                "id": "cc-testfix001",
                "status": "blocked",
                "workspace": str(data / "proj"),
                "work_branch": "feature/fix",
                "findings": [
                    {
                        "severity": "P0",
                        "path": "app/bad.py",
                        "message": "发现 eval 调用",
                        "blocking": True,
                        "rule": "eval",
                    }
                ],
                "files": ["app/bad.py"],
            }
            (data / "proj").mkdir(parents=True, exist_ok=True)
            save_job(data, job)
            req, paths, goal = build_fix_requirement(job)
            self.assertIn("门禁阻断修复", req)
            self.assertEqual(paths, ["app/bad.py"])
            self.assertIn("cc-testfix001", goal)

            with mock.patch("app.code_commit.ops.default_data_dir", return_value=data):
                with mock.patch(
                    "app.plugins_store.require_enabled",
                    return_value=None,
                ):
                    with mock.patch(
                        "app.code_dev.config.availability",
                        return_value={"ok": True, "detail": "ready"},
                    ):
                        out = prepare_fix_from_gate(job_id="cc-testfix001")
            self.assertTrue(out.get("ok"), out)
            self.assertEqual(out.get("code_dev_ui", {}).get("kind"), "propose")
            self.assertIn("app/bad.py", out.get("code_dev_ui", {}).get("write_scope") or [])

    def test_chat_disabled_when_feature_off(self):
        from app import cli_ops
        from app import plugins_store

        async def _run():
            with mock.patch.object(
                plugins_store,
                "is_enabled",
                side_effect=lambda fid: fid in ("mes-ask", "code-dev", "code-review", "mes-pcb"),
            ):
                return await cli_ops.chat("提交代码")

        out = asyncio.run(_run())
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("source"), "disabled")
        self.assertIn("code-commit", out.get("reply") or "")
        self.assertIn("功能插件", out.get("reply") or "")
        self.assertIsNone(out.get("code_commit_ui"))
        self.assertIsNone(out.get("code_dev_ui"))


class FeatureGateCommitTests(unittest.TestCase):
    def test_chat_stream_blocks_code_commit_when_disabled(self):
        from app import cli_ops
        from app import plugins_store

        async def _run():
            events = []
            with mock.patch.object(
                plugins_store,
                "is_enabled",
                side_effect=lambda fid: fid in ("mes-ask", "code-dev", "code-review"),
            ):
                async for ev in cli_ops.chat_stream("提交今天的代码"):
                    events.append(ev)
            return events

        events = asyncio.run(_run())
        done = next(e for e in events if e.get("type") == "done")
        self.assertEqual(done.get("source"), "disabled")
        self.assertIn("code-commit", done.get("reply") or "")
        self.assertIsNone(done.get("code_commit_ui"))


if __name__ == "__main__":
    unittest.main()

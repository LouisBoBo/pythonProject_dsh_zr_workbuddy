"""code_dev P0-1 单元测试（不调 Cursor、不改真实工程）。"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class CodeDevTests(unittest.TestCase):
    def test_validate_workspace_rejects_home(self):
        from app.code_dev.workspace import validate_workspace

        home = str(Path.home())
        out = validate_workspace(home)
        self.assertFalse(out.get("ok"))
        self.assertTrue(out.get("error"))

    def test_validate_workspace_accepts_project(self):
        from app.code_dev.workspace import validate_workspace

        # macOS tempfile 在 /private/var 下会被敏感前缀拒绝；用引擎 data 下临时目录
        root = Path(_ENG) / "data" / "_test_code_dev_ws"
        root.mkdir(parents=True, exist_ok=True)
        try:
            (root / "package.json").write_text('{"name":"t"}', encoding="utf-8")
            out = validate_workspace(str(root))
            self.assertTrue(out.get("ok"), out.get("error"))
            self.assertTrue(out.get("looks_like_project"))
        finally:
            for p in root.iterdir():
                if p.is_file():
                    p.unlink()
            try:
                root.rmdir()
            except OSError:
                pass

    def test_start_blocked_when_disabled(self):
        from app.code_dev import ops

        with mock.patch.object(ops, "get_config") as gc:
            from app.code_dev.config import CodeDevConfig

            gc.return_value = CodeDevConfig(enabled=False)
            out = ops.start(workspace="/tmp/x", message="hi")
        self.assertFalse(out.get("ok"))
        self.assertIn("未开启", out.get("detail") or "")

    def test_is_code_dev_question(self):
        from app.code_dev.intent import is_code_dev_question

        self.assertTrue(is_code_dev_question("MES系统开发消息中心菜单界面"))
        self.assertTrue(is_code_dev_question("在 /Users/a/b 开发一个登录页"))
        self.assertTrue(is_code_dev_question("【写码需求选项已确认】\n工程路径：/x\n范围：菜单"))
        self.assertTrue(
            is_code_dev_question("消息中心消息列表增加读消息功能 点击消息时查看消息详细内容并标记已读")
        )
        self.assertFalse(is_code_dev_question("今天完工工单有多少个"))
        self.assertFalse(is_code_dev_question("最近7天良率趋势"))

    def test_chat_code_dev_asks_for_path(self):
        from app.code_dev import chat_bridge
        from app.code_dev.config import CodeDevConfig

        with mock.patch.object(chat_bridge.plugins_store, "is_enabled", return_value=True):
            with mock.patch.object(
                chat_bridge,
                "availability",
                return_value={"ok": True, "detail": "就绪"},
            ):
                with mock.patch.object(
                    chat_bridge,
                    "get_config",
                    return_value=CodeDevConfig(enabled=True, cursor_api_key="x", default_workspace=""),
                ):
                    out = asyncio.run(chat_bridge.handle_chat_code_dev("MES系统开发消息中心菜单界面"))
        self.assertTrue(out.get("ok"))
        self.assertIn("绝对路径", out.get("reply") or "")
        self.assertEqual(out.get("data_source"), "code_dev")
        self.assertIsNone(out.get("job_id"))
        self.assertIsNone(out.get("code_dev_ui"))

    def test_chat_with_workspace_returns_options_not_start(self):
        from app.code_dev import chat_bridge
        from app.code_dev.config import CodeDevConfig

        async def fake_discuss(*_a, **_k):
            return {
                "ok": True,
                "thinking": "先收集范围",
                "reply": "请勾选",
                "options": {
                    "title": "范围",
                    "groups": [{"id": "scope", "label": "范围", "multi": True, "options": [{"id": "a", "label": "A"}]}],
                },
                "propose": None,
                "detail": "options",
            }

        with mock.patch.object(chat_bridge.plugins_store, "is_enabled", return_value=True):
            with mock.patch.object(
                chat_bridge,
                "availability",
                return_value={"ok": True, "detail": "就绪"},
            ):
                with mock.patch.object(
                    chat_bridge,
                    "get_config",
                    return_value=CodeDevConfig(
                        enabled=True,
                        cursor_api_key="x",
                        default_workspace="/Users/hebo/Desktop/中软项目/pythonProject_zr_aicoding",
                    ),
                ):
                    with mock.patch.object(chat_bridge, "discuss_requirement", side_effect=fake_discuss):
                        with mock.patch.object(chat_bridge, "code_dev_start") as start_mock:
                            out = asyncio.run(
                                chat_bridge.handle_chat_code_dev("MES系统开发消息中心菜单界面")
                            )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("code_dev_ui", {}).get("kind"), "options")
        self.assertTrue(out.get("thinking"))
        self.assertIsNone(out.get("job_id"))
        start_mock.assert_not_called()

    def test_parse_machine_blocks(self):
        from app.code_dev.fence import parse_machine_blocks

        raw = (
            "先确认范围。\n"
            ":::cursor_dev_options\n"
            '{"title":"T","groups":[{"id":"g","label":"G","multi":true,"options":[{"id":"1","label":"一"}]}]}\n'
            ":::"
        )
        p = parse_machine_blocks(raw)
        self.assertIn("确认", p.get("prose") or "")
        self.assertEqual(p["options"]["title"], "T")
        self.assertIsNone(p.get("propose"))

    def test_cli_code_dev_status_gated(self):
        from app import cli_ops
        from app import plugins_store

        with mock.patch.object(
            plugins_store,
            "require_enabled",
            return_value={"ok": False, "detail": "已停用"},
        ):
            out = asyncio.run(cli_ops.run_async("code-dev-status", []))
        self.assertFalse(out.get("ok"))

    def test_cli_code_dev_status_ok_path(self):
        from app import cli_ops
        from app import plugins_store

        with mock.patch.object(plugins_store, "require_enabled", return_value=None):
            with mock.patch("app.code_dev.status", return_value={"ok": True, "detail": "就绪"}):
                out = asyncio.run(cli_ops.run_async("code-dev-status", []))
        self.assertTrue(out.get("ok"))


    def test_brief_preserves_original_goal(self):
        from app.code_dev.brief import CodeDevBrief, build_requirement, merge_brief, validate_synced_files

        b = merge_brief(
            None,
            "报表中心菜单新增员工工时报表",
            workspace="/Users/he/proj",
        )
        self.assertIn("员工工时", b.original_goal)
        b = merge_brief(
            b.to_dict(),
            "【写码需求选项已确认】\n工程路径：/Users/he/proj\n本轮范围：界面+接口",
            workspace="/Users/he/proj",
        )
        req = build_requirement(b)
        self.assertIn("【原始诉求】", req)
        self.assertIn("员工工时", req)
        self.assertIn("报表中心", req)
        check = validate_synced_files(
            b,
            req,
            ["frontend/src/api/messages.js", "frontend/src/views/messages/Index.vue"],
        )
        self.assertTrue(check.get("mismatch"))

    def test_generic_requirement_blocked(self):
        from app.code_dev.brief import CodeDevBrief, validate_requirement_for_start

        b = CodeDevBrief(
            original_goal="报表中心菜单新增员工工时报表",
            workspace="/Users/he/proj",
            option_rounds=2,
        )
        generic = "在项目内实现一个列表页，对接查询、新增/编辑、删除接口。"
        v = validate_requirement_for_start(b, generic)
        self.assertFalse(v.get("ok"))

    def test_brief_from_dict_rejects_bad_rounds(self):
        from app.code_dev.brief import CodeDevBrief

        b = CodeDevBrief.from_dict({"option_rounds": "not-a-number", "original_goal": "x" * 5000})
        self.assertEqual(b.option_rounds, 0)
        self.assertEqual(len(b.original_goal), 4000)

    def test_canonical_requirement_not_generic(self):
        from app.code_dev.brief import CodeDevBrief, build_requirement, is_generic_requirement

        b = CodeDevBrief(original_goal="报表中心新增员工工时报表")
        req = build_requirement(b)
        self.assertFalse(is_generic_requirement(req))

    def test_sandbox_skips_engine_data_and_sparse_scope(self):
        import tempfile

        from app.code_dev.config import CodeDevConfig
        from app.code_dev.sandbox import _should_skip_dirname, prepare_sandbox

        self.assertTrue(_should_skip_dirname("data", Path("apps/zr-workbuddy/engine")))
        self.assertFalse(_should_skip_dirname("data", Path("frontend/src")))

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "proj"
            (ws / "engine" / "data" / "local_dev").mkdir(parents=True)
            (ws / "engine" / "data" / "local_dev" / "x.bin").write_bytes(b"1" * 40)
            (ws / "a").mkdir(parents=True)
            (ws / "a" / "__init__.py").write_text("", encoding="utf-8")
            _eval_fn = "ev" + "al"
            (ws / "a" / "bad.py").write_text(f"{_eval_fn}(x)\n", encoding="utf-8")
            (ws / "noise.txt").write_text("n\n", encoding="utf-8")
            data = Path(tmp) / "data"
            cfg = CodeDevConfig(
                copy_max_files=100,
                copy_max_total_bytes=10_000_000,
                max_file_bytes=1_000_000,
            )
            full = prepare_sandbox(data, "ldj-full", ws, empty_target=False, cfg=cfg)
            self.assertEqual(full.get("mode"), "copy")
            sb_full = Path(full["sandbox"])
            self.assertTrue((sb_full / "a" / "bad.py").is_file())
            self.assertFalse((sb_full / "engine" / "data" / "local_dev" / "x.bin").exists())

            sparse = prepare_sandbox(
                data,
                "ldj-sparse",
                ws,
                empty_target=False,
                cfg=cfg,
                include_rels=["a/bad.py"],
            )
            self.assertEqual(sparse.get("mode"), "sparse")
            sb = Path(sparse["sandbox"])
            self.assertTrue((sb / "a" / "bad.py").is_file())
            self.assertFalse((sb / "noise.txt").exists())


if __name__ == "__main__":
    unittest.main()

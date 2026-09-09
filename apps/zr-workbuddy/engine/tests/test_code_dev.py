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

    def test_sandbox_deletes_are_applied_to_target(self):
        import tempfile

        from app.code_dev.fs_snapshot import deleted_from_snapshots, diff_snapshots, snapshot_sandbox
        from app.code_dev.sandbox import apply_deletes_to_target, sync_changed_to_target

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            sandbox = Path(tmp) / "sb"
            (target / "frontend" / "src").mkdir(parents=True)
            (sandbox / "frontend" / "src").mkdir(parents=True)
            keep = "frontend/src/keep.vue"
            gone = "frontend/src/OverviewView.vue"
            (target / keep).write_text("keep", encoding="utf-8")
            (target / gone).write_text("old", encoding="utf-8")
            (sandbox / keep).write_text("keep", encoding="utf-8")
            (sandbox / gone).write_text("old", encoding="utf-8")
            before = snapshot_sandbox(sandbox)
            (sandbox / gone).unlink()
            (sandbox / keep).write_text("keep-2", encoding="utf-8")
            after = snapshot_sandbox(sandbox)
            changed = diff_snapshots(before, after)
            deleted = deleted_from_snapshots(before, after)
            self.assertEqual(changed, [keep])
            self.assertEqual(deleted, [gone])
            written = sync_changed_to_target(sandbox, target, changed)
            removed = apply_deletes_to_target(target, deleted)
            self.assertEqual(written, [keep])
            self.assertEqual(removed, [gone])
            self.assertEqual((target / keep).read_text(encoding="utf-8"), "keep-2")
            self.assertFalse((target / gone).exists())

    def test_partition_promotes_views_when_router_changed(self):
        """窄 scope 误指向 production 时，路由变更须强制带上 warehouse 视图。"""
        from app.code_dev.path_scope import partition_by_scope

        changed = [
            "frontend/src/router/index.js",
            "frontend/src/layouts/AppLayout.vue",
            "frontend/src/views/warehouse/MaterialOutboundRecordsView.vue",
            "frontend/src/views/warehouse/MaterialOutboundView.vue",
            "README.md",
        ]
        scope = [
            "frontend/src/views/production/",
            "frontend/src/router/",
            "frontend/src/layouts/",
        ]
        inside, outside = partition_by_scope(changed, scope)
        self.assertIn("frontend/src/router/index.js", inside)
        self.assertIn(
            "frontend/src/views/warehouse/MaterialOutboundRecordsView.vue",
            inside,
        )
        self.assertIn(
            "frontend/src/views/warehouse/MaterialOutboundView.vue",
            inside,
        )
        self.assertIn("README.md", outside)

    def test_partition_import_closure_from_sandbox(self):
        from app.code_dev.path_scope import partition_by_scope

        root = Path(_ENG) / "data" / "_test_partition_sb"
        router = root / "frontend" / "src" / "router"
        views = root / "frontend" / "src" / "views" / "warehouse"
        router.mkdir(parents=True, exist_ok=True)
        views.mkdir(parents=True, exist_ok=True)
        (router / "index.js").write_text(
            "import X from '../views/warehouse/MaterialOutboundRecordsView.vue'\n",
            encoding="utf-8",
        )
        (views / "MaterialOutboundRecordsView.vue").write_text("<template/>", encoding="utf-8")
        try:
            # 故意不让 shell_touched 用 views 前缀规则以外的路径——用假 router 路径
            # 实际：router 在 inside，view 在 outside，靠 import 闭包提升
            changed = [
                "frontend/src/router/index.js",
                "frontend/src/views/warehouse/MaterialOutboundRecordsView.vue",
            ]
            # scope 只含 router，无 views；shell wiring 会把 router 放 inside，
            # promote_shell_companions 因 shell_touched 也会直接提升 views
            inside, outside = partition_by_scope(
                changed,
                ["frontend/src/router/"],
                sandbox_root=root,
            )
            self.assertIn(
                "frontend/src/views/warehouse/MaterialOutboundRecordsView.vue",
                inside,
            )
            self.assertEqual(outside, [])
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)

    def test_warehouse_module_beats_production_for_outbound(self):
        from app.code_dev.brief import CodeDevBrief, infer_target

        hints = infer_target(
            CodeDevBrief(original_goal="MES系统仓库管理菜单新增物料出库记录")
        )
        self.assertEqual(hints.get("module"), "仓库管理")
        paths = hints.get("expected_paths") or []
        self.assertTrue(any("warehouse" in p for p in paths), paths)

    def test_thinking_from_sdk_message(self):
        from app.code_dev.cursor_agent import _thinking_from_message

        class Msg:
            type = "thinking"
            text = "先看路由再改菜单"
            thinking_duration_ms = 67000

        text, dur = _thinking_from_message(Msg())
        self.assertEqual(text, "先看路由再改菜单")
        self.assertEqual(dur, 67000)
        text2, dur2 = _thinking_from_message(
            {"type": "thinking", "text": "delta", "thinkingDurationMs": 1200}
        )
        self.assertEqual(text2, "delta")
        self.assertEqual(dur2, 1200)

    def test_record_event_thinking(self):
        import shutil
        import tempfile

        from app.code_dev import jobs as job_store

        td = Path(tempfile.mkdtemp())
        try:
            job = job_store.create_job(
                td,
                user_id="",
                username="",
                thread_id="t",
                workspace=str(td),
                message="改菜单",
            )
            jid = job["id"]
            job_store.record_event(td, jid, {"type": "thinking", "text": "先"})
            job_store.record_event(td, jid, {"type": "thinking", "text": "先看目录", "thinking_duration_ms": 1500})
            got = job_store.get_job(td, jid)
            self.assertEqual(got.get("thinking_text"), "先看目录")
            self.assertEqual(got.get("thinking_duration_ms"), 1500)
            thinks = [e for e in (got.get("events") or []) if e.get("type") == "thinking"]
            self.assertEqual(len(thinks), 1)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_assistant_text_from_nested_sdk(self):
        from app.code_dev.cursor_agent import _assistant_text_from_message

        class Block:
            type = "text"
            text = "改了菜单"

        class Inner:
            content = (Block(),)

        class Msg:
            type = "assistant"
            message = Inner()

        self.assertEqual(_assistant_text_from_message(Msg()), "改了菜单")

    def test_tool_activity_and_stream_sink(self):
        from app.code_dev.cursor_agent import _CursorStreamSink, _public_relpath, _tool_activity_line

        sandbox = "/tmp/sandboxes/ldj-abc123"
        line = _tool_activity_line(
            name="Read",
            args={"path": sandbox + "/frontend/src/App.vue"},
            sandbox=sandbox,
        )
        self.assertIn("阅读", line)
        self.assertIn("frontend/src/App.vue", line)
        self.assertNotIn("/tmp/", line)
        self.assertEqual(
            _public_relpath(sandbox + "/backend/app/main.py", sandbox),
            "backend/app/main.py",
        )
        nested = _tool_activity_line(
            args={"readToolCall": {"args": {"path": sandbox + "/models.py"}}},
            sandbox=sandbox,
        )
        self.assertIn("阅读", nested)
        self.assertIn("models.py", nested)

        events = []
        bus = _CursorStreamSink(events.append, sandbox=sandbox)
        bus.flush_think()
        bus.add_reasoning_delta("先看路由再决定改哪个页面。")
        bus.add_tool(name="Read", status="running", args={"path": sandbox + "/src/a.py"}, call_id="c1")
        bus.handle_delta(type("U", (), {"type": "thinking-completed", "thinking_duration_ms": 1500})())
        texts = [e.get("text") for e in events if e.get("type") == "thinking"]
        self.assertTrue(any("先看路由" in (t or "") for t in texts))
        self.assertFalse(any("/tmp/" in (t or "") for t in texts))
        self.assertFalse(any("src/a.py" in (t or "") for t in texts))
        tools = [e for e in events if e.get("type") == "tool_call"]
        self.assertTrue(tools)
        self.assertIn("阅读", tools[0].get("text") or "")
        self.assertIn("src/a.py", tools[0].get("text") or "")
        self.assertIsNone(bus.think_ms)

    def test_absorb_text_collapses_duplicate_blocks(self):
        from app.code_dev.cursor_agent import _absorb_text, _collapse_repeated, _CursorStreamSink

        para = "正在探索工作区结构，定位品质管理相关模块与现有接口。"
        self.assertEqual(_absorb_text("配的", "，再按现有"), "配的，再按现有")
        self.assertNotIn("\n", _absorb_text("接下来按", "现有 MES 模式落地"))
        self.assertEqual(_absorb_text("接入加班管理。", "加班管理。已有页面"), "接入加班管理。已有页面")
        self.assertEqual(_collapse_repeated("加班管理。加班管理。两种权限。两种权限。"), "加班管理。两种权限。")
        self.assertEqual(_collapse_repeated("apply apply schemaschema"), "apply schema")
        events = []
        bus = _CursorStreamSink(events.append)
        bus.add_reasoning_delta(para)
        bus.add_reasoning_delta(para)
        bus.add_reasoning_delta(para + "\n\n正在实现品质概览：新增后端聚合接口。")
        self.assertEqual(bus.reasoning.count("正在探索工作区结构"), 1)
        bus.add_assistant_piece("正在", from_delta=True)
        bus.add_assistant_piece("正在探索工作区结构，定位品质管理相关模块与现有接口。", from_delta=True)
        self.assertEqual(bus.final_text.count("正在探索"), 0)
        self.assertIn("正在探索", bus.reasoning)
        long_explore = para * 20
        events2: list[dict] = []
        bus2 = _CursorStreamSink(events2.append)
        bus2.seed_process("正在沙箱内改码。")
        bus2.add_assistant_piece(long_explore, from_delta=True)
        self.assertNotIn(long_explore[:80], bus2.final_text)
        self.assertIn("沙箱", bus2.final_text)
        think_texts = [e.get("text") for e in events2 if e.get("type") == "thinking"]
        self.assertTrue(any("正在探索工作区结构" in (t or "") for t in think_texts))
        self.assertIn("正在探索工作区结构", bus2.reasoning)
        self.assertFalse(bus2._assistant_body.strip())

    def test_extract_delivery_keeps_last_clean_copy(self):
        from app.code_dev.cursor_agent import extract_delivery_markdown, split_delivery_markdown

        messy = (
            "先摸清现有工程结构，重点看考勤模块。加班管理」。加班管理」。\n"
            "已有`OvertimeView.vue，但后端表被删了。\n"
            "##一句话一句话\n结论\n已在\n结论\n"
            "已在考勤管理下完整接入「加班管理」：含菜单/路由。\n"
            "##改动文件表改动文件表\n"
            "| 文件\n| 说明\n"
        )
        clean = (
            "一句话结论\n"
            "已在考勤管理下完整接入「加班管理」：含菜单/路由、加班申请、审批。\n\n"
            "改动文件表\n"
            "文件\t说明\n"
            "backend/app/models.py\t新增 AttendanceOvertime 数据模型\n"
        )
        process, delivery = split_delivery_markdown(messy + "\n" + clean)
        self.assertIn("先摸清", process)
        self.assertTrue(delivery.startswith("一句话结论"))
        self.assertNotIn("改动文件表改动文件表", delivery)
        out = extract_delivery_markdown(messy + "\n" + clean)
        self.assertTrue(out.startswith("一句话结论"))
        self.assertNotIn("先摸清", out)
        self.assertIn("AttendanceOvertime", out)
        self.assertEqual(extract_delivery_markdown(clean), clean.strip())
        self.assertEqual(split_delivery_markdown(clean), ("", clean.strip()))

        colon = (
            "先在沙箱里定位考勤模块。\n"
            "一句话结论：已从考勤管理模块完整移除「加班管理」。\n"
            "列列\n说明\n---\t---\n"
            "一句话结论：已从考勤管理模块完整移除「加班管理」子项。\n"
            "列\t说明\n"
            "改动文件\tfrontend/src/layouts/AppLayout.vue — 删除菜单\n"
        )
        p2, d2 = split_delivery_markdown(colon)
        self.assertEqual(p2, "先在沙箱里定位考勤模块。")
        self.assertTrue(d2.startswith("一句话结论：已从考勤管理模块完整移除「加班管理」子项"))
        self.assertNotIn("列列", d2)
        self.assertIn("AppLayout.vue", d2)

        inline = (
            "已定位相关代码，开始移除品质概览入口并停用对应接口。"
            "。一句话结论：草稿叠字做了什么 做了什么。\n"
            "改动 改动。验收步骤 1. 步骤 1.\n"
            "一句话结论：已从品质管理模块移除品质概览。\n"
            "改动文件\n"
            "- `frontend/src/router/index.js`：改为重定向到检验方案\n"
        )
        p3, d3 = split_delivery_markdown(inline)
        self.assertEqual(p3, "已定位相关代码，开始移除品质概览入口并停用对应接口")
        self.assertTrue(d3.startswith("一句话结论：已从品质管理模块移除品质概览"))
        self.assertNotIn("草稿叠字", d3)
        self.assertNotIn("草稿叠字", p3)

        glued_title = (
            "菜单里已无品质概览，接下来清理残留页面。"
            "搜索。查找文件。查看 frontend/src/layouts/AppLayout.vue。"
            "说明方案结论已从品质管理模块完整移除品质概览。\n"
            "改动文件\n"
            "- `frontend/src/router/index.js`：重定向到检验方案\n"
        )
        p4, d4 = split_delivery_markdown(glued_title)
        self.assertIn("清理残留", p4)
        self.assertTrue(d4.startswith("说明方案"))
        self.assertIn("router/index.js", d4)

    def test_absorb_keeps_last_delivery_only(self):
        from app.code_dev.cursor_agent import _absorb_text

        prev = "先看路由。一句话结论：第一稿。\n改动文件\n- `a.py`：改了"
        nxt = "先看路由和菜单。一句话结论：终稿只留这一份。\n改动文件\n- `a.py`：删除概览"
        got = _absorb_text(prev, nxt)
        self.assertIn("先看路由", got)
        self.assertEqual(got.count("一句话结论"), 1)
        self.assertIn("终稿只留这一份", got)
        self.assertNotIn("第一稿", got)

    def test_format_cursor_dialog_dedupes_and_pretty_plan(self):
        from app.code_dev.cursor_agent import format_cursor_dialog
        from app.code_dev.delete_enforce import parse_delete_plan_from_text

        raw = (
            "正在本机工程只读定位「看板管理→综合看板」菜单入口。"
            "正在本机工程只读定位「看板管理 → 综合看板」菜单入口。"
            "已命中「综合看板」关键字；接着核对路由注册与页面/API文件是否独立成模块。"
            "已命中「综合看板」关键字；接着核对路由注册与页面/API 文件是否独立成模块。"
            "菜单/路由引擎修补，本清单只列页面与API。"
            "菜单/路由由引擎修补，本清单只列页面与 API。"
            "##删除清单-`frontend/src/views/kanban/ComprehensiveKanbanView.vue`：页面组件"
            "-`frontend/src/api/kanbanGeneral.js`：API封装"
            "结论：下线「看板管理→综合看板」只需去掉该菜单/路由入口并删除上述前端页面与API；后端接口保留即可满足验收。"
        )
        proc, deliv = format_cursor_dialog(raw)
        self.assertEqual(proc.count("正在本机工程只读定位"), 1)
        self.assertEqual(proc.count("已命中「综合看板」"), 1)
        self.assertEqual(proc.count("本清单只列"), 1)
        self.assertIn("## 删除清单", proc)
        paths = parse_delete_plan_from_text(proc)
        self.assertIn("frontend/src/views/kanban/ComprehensiveKanbanView.vue", paths)
        self.assertIn("frontend/src/api/kanbanGeneral.js", paths)
        plan = proc.split("## 删除清单", 1)[1]
        self.assertLess(plan.index("ComprehensiveKanbanView"), plan.index("kanbanGeneral"))
        self.assertIn("下线", deliv)
        self.assertNotIn("正在本机工程只读定位", deliv)

    def test_read_only_seed_not_fake_plan_and_thinking_promoted(self):
        from app.code_dev.cursor_agent import (
            _CursorStreamSink,
            is_engine_seed_text,
            looks_like_delete_plan_reply,
        )

        self.assertTrue(is_engine_seed_text("正在只读定位待删文件，输出删除清单。"))
        self.assertTrue(is_engine_seed_text("正在只读定位待删文件。"))
        self.assertFalse(looks_like_delete_plan_reply("正在只读定位待删文件，输出删除清单。"))
        self.assertTrue(
            looks_like_delete_plan_reply("## 删除清单\n- `frontend/src/views/x.vue`")
        )

        events = []
        bus = _CursorStreamSink(events.append, read_only=True)
        bus.seed_process("正在只读定位待删文件。")
        self.assertTrue(is_engine_seed_text(bus.final_text))
        bus.add_reasoning_delta("对照 AppLayout 与 router，准备下线物料出库菜单项。")
        self.assertIn("物料出库", bus.final_text)
        self.assertNotIn("正在只读定位", bus.final_text)
        dlg = bus.export_dialog()
        self.assertIn("物料出库", dlg["process"])
        self.assertFalse(is_engine_seed_text(dlg["process"]))
        self.assertFalse(looks_like_delete_plan_reply(dlg["process"]))

        from app.code_dev.service import _LiveProcess

        live = _LiveProcess(events.append, chunk_delay_sec=0, cursor_only=True)
        live.apply_cursor_dialog(
            {
                "process": "正在只读定位待删文件。",
                "thinking": "对照菜单后确认删除物料出库。",
                "text": "正在只读定位待删文件。",
            }
        )
        self.assertIn("物料出库", live.text())
        self.assertNotIn("正在只读定位", live.text())

    def test_seed_process_and_skip_fence_break(self):
        from app.code_dev.cursor_agent import _CursorStreamSink, _absorb_text

        events = []
        bus = _CursorStreamSink(events.append)
        bus.seed_process("正在启动 Cursor，开始对照工作区定位相关代码")
        self.assertTrue(bus.final_text.startswith("正在启动 Cursor"))
        self.assertTrue(any(e.get("type") == "replace_text" for e in events))
        bus.add_tool(name="Read", status="running", args={"path": "/tmp/sandboxes/x/frontend/src/App.vue"}, call_id="c1")
        # 工具行进正文时改为中性说明（避免路径被 tool-echo 清扫后正文空）
        self.assertIn("正在对照工作区定位相关文件", bus.final_text)
        self.assertTrue(any(e.get("type") == "tool_call" for e in events))
        bus.add_tool(name="Read", status="running", args={"path": "/tmp/sandboxes/x/frontend/src/App.vue"}, call_id="c2")
        self.assertEqual(bus.final_text.count("正在对照工作区定位相关文件"), 1)
        bus.add_tool(name="Read", status="completed", args={"path": "/tmp/sandboxes/x/frontend/src/App.vue"}, call_id="c1")
        self.assertEqual(bus.final_text.count("正在对照工作区定位相关文件"), 1)
        bus.add_reasoning_delta("先定位品质管理菜单，再改路由。")
        self.assertIn("品质管理", bus.reasoning)
        self.assertNotIn("品质管理", bus.final_text)
        glued = _absorb_text("接下来改路由。", "```javascript\nconst a = 1\n```")
        self.assertIn("```javascript", glued)
        self.assertNotIn("。\n\n```", glued)

        from app.code_dev.cursor_agent import _is_tool_echo_sentence, _scrub_tool_echo_in_process

        self.assertTrue(_is_tool_echo_sentence("查看 frontend/src/App.vue"))
        self.assertTrue(_is_tool_echo_sentence("查找文件"))
        self.assertTrue(_is_tool_echo_sentence("查看 pythonProject_zr_aicoding"))
        self.assertFalse(_is_tool_echo_sentence("查看现有菜单结构后再改路由"))
        dumped = (
            "正在启动 Cursor，开始对照工作区定位相关代码。"
            "搜索。查找文件。查看 frontend/src/layouts/AppLayout.vue。"
            "菜单里已无品质概览，接下来清理残留。"
            "说明方案结论已删除概览页。\n"
        )
        cleaned = _scrub_tool_echo_in_process(dumped)
        self.assertNotIn("查找文件", cleaned)
        self.assertNotIn("AppLayout.vue", cleaned)
        self.assertNotIn("查看 frontend", cleaned)
        self.assertIn("清理残留", cleaned)
        mixed = "先在沙箱里定位品质管理。查看 frontend 查看 backend 再改路由。"
        mixed2 = _scrub_tool_echo_in_process(mixed)
        self.assertIn("定位品质管理", mixed2)
        self.assertNotIn("查看 frontend", mixed2)
        self.assertNotIn("查看 backend", mixed2)

    def test_gate_stream_process_strips_code_keeps_prose(self):
        from app.code_dev.cursor_agent import _gate_stream_process, split_assistant_channels

        body = "已改路由。\n\n```vue\n<template>\n  <div class=\"page\">"
        _, process, _ = split_assistant_channels(body)
        out = _gate_stream_process(body, process)
        self.assertIn("已改路由", out)
        self.assertNotIn("```", out)
        self.assertNotIn("<template>", out)

    def test_strip_bare_code_keeps_fences(self):
        from app.code_dev.cursor_agent import _finalize_process_body, _strip_bare_code_from_process

        mixed = (
            "已更新模型字段。\n"
            "import annotations\n"
            "class Foo:\n"
            "    pass\n\n"
            "```python\n"
            "from datetime import datetime\n"
            "TASK_STATUS_PENDING = 0\n"
            "```"
        )
        bare = _strip_bare_code_from_process(mixed)
        self.assertIn("已更新模型字段", bare)
        self.assertIn("```python", bare)
        self.assertIn("TASK_STATUS_PENDING", bare)
        self.assertNotIn("import annotations", bare)
        self.assertNotIn("class Foo", bare)
        final = _finalize_process_body(mixed)
        self.assertIn("已更新模型字段", final)
        self.assertNotIn("```", final)
        self.assertNotIn("class Foo", final)
        self.assertNotIn("TASK_STATUS_PENDING", final)

    def test_finalize_strips_bare_vue_script(self):
        from app.code_dev.cursor_agent import _finalize_process_body, sanitize_delivery_text

        bare = (
            "已改侧栏。\n"
            "<script setup>\n"
            "import { computed, ref } from 'vue'\n"
            "const sidebarCollapsed = ref(false)\n"
            "</script>\n"
        )
        out = _finalize_process_body(bare)
        self.assertIn("已改侧栏", out)
        self.assertNotIn("```", out)
        self.assertNotIn("<script setup>", out)
        self.assertNotIn("sidebarCollapsed", out)
        delivery = sanitize_delivery_text(
            "## 说明方案\n**结论**\n侧栏已更新。\n<script setup>\nimport { ref } from 'vue'\n</script>\n"
        )
        self.assertIn("结论", delivery)
        self.assertIn("侧栏已更新", delivery)
        self.assertNotIn("```", delivery)
        self.assertNotIn("<script setup>", delivery)

    def test_prompt_asks_for_prose_not_tables(self):
        from app.code_dev.cursor_agent import build_prompt

        prompt = build_prompt(requirement="删掉生产概览", workspace_hint="/tmp/ws", empty_target=False)
        self.assertIn("禁止表格", prompt)
        self.assertIn("## 说明方案", prompt)
        self.assertIn("此阶段禁止出现", prompt)
        self.assertIn("每段最多两句", prompt)
        self.assertIn("禁止贴代码块", prompt)
        self.assertIn("同步从本机工程删掉", prompt)
        self.assertIn("- `path/to/file`", prompt)
        self.assertNotIn("| 列 |", prompt)
        self.assertNotIn("改动文件表", prompt)
        self.assertNotIn("完整相关代码", prompt)

    def test_merge_changed_code_when_fences_missing(self):
        import tempfile

        from app.code_dev.service import merge_changed_code_into_text, substantial_code_fences

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rel = "frontend/src/App.vue"
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<template>\n  <div>hello</div>\n</template>\n" + ("const x = 1\n" * 20), encoding="utf-8")
            short = "已改 App.vue，去掉概览入口。\n\n## 说明方案\n**结论**\n删了概览。"
            self.assertFalse(substantial_code_fences(short))
            out = merge_changed_code_into_text(short, root, [rel])
            self.assertIn("```vue", out)
            self.assertIn("<template>", out)
            self.assertIn("说明方案", out)
            self.assertTrue(out.index("```vue") < out.index("说明方案"))
            long_proc = "说明。\n```javascript\n" + ("const a = 1;\n" * 30) + "```\n"
            kept = merge_changed_code_into_text(long_proc + "\n## 说明方案\n结论", root, [rel])
            self.assertNotIn("## 改动代码", kept)

    def test_record_event_thinking_snapshot_and_tool(self):
        import shutil
        import tempfile

        from app.code_dev import jobs as job_store

        td = Path(tempfile.mkdtemp())
        try:
            job = job_store.create_job(
                td,
                user_id="",
                username="",
                thread_id="t",
                workspace=str(td),
                message="改菜单",
            )
            jid = job["id"]
            job_store.record_event(td, jid, {"type": "thinking", "text": "占位", "snapshot": True})
            job_store.record_event(
                td,
                jid,
                {
                    "type": "thinking",
                    "text": "先看目录，确认品质模块现有接口。",
                    "snapshot": True,
                    "thinking_duration_ms": 2100,
                },
            )
            job_store.record_event(td, jid, {"type": "tool_call", "name": "Read", "text": "阅读 `backend/app/main.py`"})
            got = job_store.get_job(td, jid)
            self.assertIn("先看目录", got.get("thinking_text") or "")
            self.assertNotIn("main.py", got.get("thinking_text") or "")
            self.assertEqual(got.get("current_action"), "阅读 `backend/app/main.py`")
            self.assertEqual(got.get("thinking_duration_ms"), 2100)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_write_scope_includes_router_for_menu_ops(self):
        from app.code_dev.brief import write_scope_from_hints

        scope = write_scope_from_hints({"confidence": "medium", "expected_paths": []}, "删除品质管理菜单里的品质概览")
        self.assertIn("frontend/src/router/", scope)
        self.assertIn("frontend/src/layouts/", scope)
        self.assertIn("frontend/src/views/", scope)

    def test_warehouse_kanban_floor_and_scope(self):
        """仓储看板：引擎白名单含页面；删除诉求 write_scope 须含 views/board。"""
        import tempfile
        from pathlib import Path

        from app.code_dev.brief import infer_target_from_text, write_scope_from_hints
        from app.code_dev.delete_enforce import plan_delete_file_targets, validate_delete_plan

        req = "看板管理菜单删除仓储看板子项"
        hints = infer_target_from_text(req)
        self.assertEqual(hints.get("module"), "看板管理")
        scope = write_scope_from_hints(hints, req)
        self.assertTrue(
            any(p.startswith("frontend/src/views") for p in scope),
            scope,
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rel = "frontend/src/views/board/WarehouseDashboard.vue"
            (root / rel).parent.mkdir(parents=True)
            (root / rel).write_text("<template>仓储看板</template>\n", encoding="utf-8")
            floor = plan_delete_file_targets(req, root)
            self.assertEqual(floor, [rel], floor)
            approved, rejected = validate_delete_plan([rel], req, root, write_scope=scope)
            self.assertIn(rel, approved, (approved, rejected))
            self.assertFalse(any(rel in r for r in rejected), rejected)

    def test_comprehensive_kanban_floor_includes_api_backend(self):
        """综合看板：过程删除清单中的专属 API/后端应批准；结论按过程顺序列出。"""
        import tempfile
        from pathlib import Path

        from app.code_dev.brief import write_scope_from_hints, infer_target_from_text
        from app.code_dev.delete_enforce import (
            align_delivery_files_with_process,
            build_engine_delete_delivery,
            parse_delete_plan_from_text,
            validate_delete_plan,
            _strip_main_router_hooks,
        )

        req = "看板管理菜单删除综合看板子项"
        scope = write_scope_from_hints(infer_target_from_text(req), req)
        process = """
已确认综合看板页面与 API。
## 删除清单
- `frontend/src/views/kanban/ComprehensiveKanbanView.vue`：页面组件
- `frontend/src/api/kanbanGeneral.js`：API 封装
- `backend/app/routers/kanban_general.py`：综合看板路由整文件
"""
        cursor_paths = parse_delete_plan_from_text(process)
        self.assertEqual(
            cursor_paths,
            [
                "frontend/src/views/kanban/ComprehensiveKanbanView.vue",
                "frontend/src/api/kanbanGeneral.js",
                "backend/app/routers/kanban_general.py",
            ],
            cursor_paths,
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in cursor_paths:
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x\n", encoding="utf-8")
            approved, rejected = validate_delete_plan(
                cursor_paths, req, root, write_scope=scope
            )
            for rel in cursor_paths:
                self.assertIn(rel, approved, (approved, rejected))
            dels, pats = align_delivery_files_with_process(
                process,
                deleted=approved,
                patched=[
                    "frontend/src/layouts/AppLayout.vue",
                    "frontend/src/router/index.js",
                    "backend/app/main.py",
                ],
            )
            self.assertEqual(dels, cursor_paths)
            delivery = build_engine_delete_delivery(
                req,
                forced_deletes=approved,
                patched=pats,
                mode="cursor_plan",
                process_text=process,
            )
            # 过程顺序：先页面再 API 再后端
            pos = [delivery.index(r) for r in cursor_paths]
            self.assertEqual(pos, sorted(pos), delivery)
            self.assertIn("backend/app/main.py", delivery)
        sample = (
            "from .routers import (\n"
            "    foo,\n"
            "    kanban_general,\n"
            "    bar,\n"
            ")\n"
            "app.include_router(foo.router)\n"
            "app.include_router(kanban_general.router)\n"
            "app.include_router(bar.router)\n"
        )
        out, changed = _strip_main_router_hooks(sample, ["kanban_general"])
        self.assertTrue(changed)
        self.assertNotIn("kanban_general", out)
        self.assertIn("foo", out)
        self.assertIn("bar", out)

    def test_delete_plan_rejects_path_traversal(self):
        """过程清单不得夹带路径穿越。"""
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_enforce import validate_delete_plan

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 工程外诱饵
            outside = Path(td).resolve().parent / f"_wb_probe_{Path(td).name}.txt"
            try:
                outside.write_text("x", encoding="utf-8")
                # 相对穿越指向该文件（若未做 resolve 门禁会误判存在）
                sneaky = "frontend/../../" + outside.name
                (root / "frontend").mkdir(parents=True, exist_ok=True)
                approved, rejected = validate_delete_plan(
                    [sneaky],
                    "看板管理菜单删除综合看板子项",
                    root,
                    write_scope=["frontend/src/views/", "frontend/"],
                )
                self.assertNotIn(sneaky, approved, (approved, rejected))
                self.assertTrue(
                    any(
                        ("非法" in r)
                        or ("越出" in r)
                        or ("不存在" in r)
                        or ("保护" in r)
                        or ("敏感" in r)
                        for r in rejected
                    ),
                    rejected,
                )
            finally:
                try:
                    outside.unlink()
                except OSError:
                    pass

    def test_write_scope_delete_does_not_blanket_backend_app(self):
        from app.code_dev.brief import write_scope_from_hints

        scope = write_scope_from_hints(
            {"confidence": "high", "expected_paths": []},
            "看板管理菜单删除设备看板子项",
        )
        self.assertNotIn("backend/app/", scope)
        self.assertIn("backend/app/routers/", scope)
        self.assertIn("backend/app/main.py", scope)

    def test_infer_quality_module(self):
        from app.code_dev.brief import CodeDevBrief, infer_target

        hints = infer_target(CodeDevBrief(original_goal="品质管理去掉品质概览菜单"))
        self.assertEqual(hints.get("module"), "品质管理")
        self.assertIn("quality-management", " ".join(hints.get("expected_paths") or []))

    def test_delete_intent_skips_rename_only_requirement(self):
        from app.code_dev.brief import is_delete_intent

        self.assertFalse(
            is_delete_intent("将菜单项改名，不在菜单/页面新增或删除任何功能"),
        )
        self.assertTrue(is_delete_intent("从品质管理模块完整移除品质概览页面与菜单入口"))

    def test_validate_delete_completion_catches_orphans(self):
        import tempfile

        from app.code_dev.brief import validate_delete_completion

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "frontend/src/views/quality-management/QualityOverviewView.vue"
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text("x", encoding="utf-8")
            text = (
                "说明方案\n**改动文件**\n"
                "- `frontend/src/views/quality-management/QualityOverviewView.vue`：已删除\n"
            )
            err = validate_delete_completion(
                "从品质管理移除品质概览页面",
                text,
                [],
                target_root=root,
            )
            self.assertIn("删除未完成", err)

    def test_build_prompt_includes_delete_block(self):
        from app.code_dev.cursor_agent import build_prompt

        p = build_prompt(
            requirement="从考勤管理删除加班管理页面与菜单",
            workspace_hint="/tmp/proj",
            empty_target=False,
        )
        self.assertIn("删除/下线任务", p)
        self.assertIn("读盘预算", p)

    def test_delete_preflight_skips_when_clean(self):
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_preflight import audit_delete_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "frontend/src/layouts").mkdir(parents=True)
            (root / "frontend/src/router").mkdir(parents=True)
            (root / "frontend/src/layouts/AppLayout.vue").write_text(
                "export default { menu: ['检验方案'] }\n", encoding="utf-8"
            )
            (root / "frontend/src/router/index.js").write_text(
                "{ path: '/quality-management/inspection-plans' }\n", encoding="utf-8"
            )
            out = audit_delete_target(
                root,
                "从品质管理菜单删除品质概览功能",
            )
            self.assertTrue(out.get("skip_cursor"))
            self.assertIn("说明方案", out.get("delivery") or "")

    def test_extract_ignores_canonical_brief_noise(self):
        from app.code_dev.brief import CodeDevBrief, build_requirement
        from app.code_dev.delete_verify import extract_delete_features

        brief = CodeDevBrief(original_goal="删除考勤管理菜单下的请假管理")
        req = build_requirement(brief, "在考勤管理下删除请假管理页面与菜单")
        self.assertEqual(extract_delete_features(req), ["请假管理"])
        self.assertNotIn("原始诉求", extract_delete_features(req))

    def test_live_process_streams_growing_replace_text(self):
        from app.code_dev.service import _LiveProcess

        events: list[dict] = []
        live = _LiveProcess(
            events.append,
            chunk_chars=10,
            chunk_delay_sec=0,
            buffer_then_stream=True,
            cursor_only=True,
        )
        # Cursor 对话框正文实时透传
        live.wrap_sink()({"type": "replace_text", "text": "正在查看菜单 AppLayout。"})
        live.wrap_sink()({"type": "replace_text", "text": "正在查看菜单 AppLayout。\n\n## 删除清单\n- `frontend/src/x.vue`"})
        live.wrap_sink()({"type": "thinking", "text": "思考中"})
        live.wrap_sink()({"type": "replace_delivery", "text": "## 说明方案\n\n**结论**\n已定位待删文件。"})
        # 引擎步骤只走 status，不得进正文
        live.push("正在本机验尸，确认菜单/路由/页面已消失")
        live.push("本机验尸通过，删除流程完成")
        statuses = [e for e in events if e.get("type") == "status"]
        self.assertGreaterEqual(len(statuses), 2, statuses)
        cursor_replaces = [e for e in events if e.get("type") == "replace_text"]
        self.assertGreaterEqual(len(cursor_replaces), 2, cursor_replaces)
        self.assertIn("删除清单", cursor_replaces[-1]["text"])
        thinks = [e for e in events if e.get("type") == "thinking"]
        self.assertEqual(len(thinks), 1)
        live.flush_reveal()
        joined = live.text()
        self.assertIn("删除清单", joined)
        # 引擎套话不得进正文
        self.assertNotIn("引擎执行", joined)
        self.assertNotIn("验尸通过", joined)
        live.flush_delivery()
        deliv = "".join(
            e["text"]
            for e in events
            if e.get("type") in ("token_delivery", "replace_delivery") and e.get("text")
        )
        self.assertIn("说明方案", deliv)
        self.assertIn("已定位待删文件", deliv)

    def test_live_process_set_fact_when_no_cursor(self):
        from app.code_dev.service import _LiveProcess

        events: list[dict] = []
        live = _LiveProcess(
            events.append,
            chunk_chars=8,
            chunk_delay_sec=0,
            cursor_only=True,
        )
        live.push("开始处理删除诉求：下线「仓库出料」")
        live.set_fact("本机已无「仓库出料」，本次未调用 Cursor。")
        live.push("正在同步到本机工程并验尸")
        live.flush_reveal()
        body = live.text()
        self.assertEqual(body, "本机已无「仓库出料」，本次未调用 Cursor。")
        self.assertNotIn("开始处理", body)
        self.assertNotIn("同步到本机", body)
        statuses = [e["text"] for e in events if e.get("type") == "status"]
        self.assertTrue(any("开始处理" in s for s in statuses), statuses)

    def test_delete_job_emits_streaming_live_text(self):
        import shutil
        from pathlib import Path

        from app.code_dev import jobs as job_store
        from app.code_dev.brief import CodeDevBrief, build_requirement
        from app.code_dev.config import CodeDevConfig
        from app.code_dev.service import run_job

        # 系统 /var/folders 会被 workspace 门禁拒绝；落在仓内临时目录
        base = Path(__file__).resolve().parents[1] / "data" / "_test_stream_delete"
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
        try:
            root = base / "proj"
            data = base / "data"
            data.mkdir()
            root.mkdir()
            (root / "package.json").write_text('{"name":"t"}', encoding="utf-8")
            (root / "frontend/src/layouts").mkdir(parents=True)
            (root / "frontend/src/router").mkdir(parents=True)
            (root / "frontend/src/views/attendance").mkdir(parents=True)
            (root / "frontend/src/layouts/AppLayout.vue").write_text(
                "children: [\n"
                "  { path: '/attendance/leave', title: '请假管理', icon: Document },\n"
                "  { path: '/attendance/records', title: '考勤记录', icon: List },\n"
                "],\n",
                encoding="utf-8",
            )
            (root / "frontend/src/router/index.js").write_text(
                "const routes = [\n"
                "  {\n"
                "    path: 'attendance/leave',\n"
                "    name: 'attendance-leave',\n"
                "    component: AttendanceLeaveView,\n"
                "    meta: { title: '请假管理' },\n"
                "  },\n"
                "  {\n"
                "    path: 'attendance/records',\n"
                "    name: 'attendance-records',\n"
                "    component: AttendanceRecordsView,\n"
                "    meta: { title: '考勤记录' },\n"
                "  },\n"
                "]\n",
                encoding="utf-8",
            )
            (root / "frontend/src/views/attendance/LeaveView.vue").write_text(
                "<template>请假管理</template>",
                encoding="utf-8",
            )
            brief = CodeDevBrief(original_goal="删除考勤管理菜单下的请假管理")
            req = build_requirement(brief, "删除请假管理")
            job = job_store.create_job(
                data,
                user_id=None,
                username="test",
                thread_id="t1",
                workspace=str(root),
                message=req,
                write_scope=["frontend/src"],
            )
            live_snapshots: list[str] = []

            def sink(ev: dict) -> None:
                job_store.record_event(data, job["id"], ev)
                if ev.get("type") == "replace_text":
                    live_snapshots.append(str(ev.get("text") or ""))

            cfg = CodeDevConfig(
                enabled=True,
                delete_mode="engine_first",
                delete_preflight_auto_skip=False,
                live_stream_delay_sec=0,
            )
            out = run_job(data, job, sink=sink, cfg=cfg)
            self.assertEqual(out.get("status"), "succeeded", out.get("error"))
            tokens = []
            statuses = []
            for ev in (job_store.get_job(data, job["id"]) or {}).get("events") or []:
                if ev.get("type") == "token":
                    tokens.append(str(ev.get("text") or ""))
                if ev.get("type") == "status":
                    statuses.append(str(ev.get("text") or ""))
            final_job = job_store.get_job(data, job["id"]) or {}
            final_live = str(final_job.get("live_text") or "")
            # engine_first：正文只有一句事实；引擎旁白走 status
            self.assertGreaterEqual(len(tokens), 1, tokens[:20])
            self.assertIn("未调用 Cursor", final_live)
            self.assertIn("请假管理", final_live)
            self.assertNotIn("开始处理删除诉求", final_live)
            self.assertNotIn("原始诉求", final_live)
            self.assertTrue(any("开始处理删除诉求" in s for s in statuses), statuses)
            # 菜单已无请假管理
            layout = (root / "frontend/src/layouts/AppLayout.vue").read_text(encoding="utf-8")
            self.assertNotIn("请假管理", layout)
            self.assertFalse((root / "frontend/src/views/attendance/LeaveView.vue").is_file())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_extract_delete_features_prefers_leaf_menu(self):
        from app.code_dev.delete_verify import extract_delete_features, verify_delete_on_target

        feats = extract_delete_features("删除生产管理菜单下的生产排产子项")
        self.assertEqual(feats, ["生产排产"])
        self.assertNotIn("生产管理菜单下的生产排产", feats)

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = root / "frontend/src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                "children: [\n"
                "  { path: '/production/scheduling', title: '生产排产', icon: Calendar },\n"
                "  { path: '/work-orders', title: '生产工单', icon: Document },\n"
                "],\n",
                encoding="utf-8",
            )
            router = root / "frontend/src/router/index.js"
            router.parent.mkdir(parents=True)
            router.write_text(
                "path: 'production/scheduling',\nmeta: { title: '生产排产' },\n",
                encoding="utf-8",
            )
            view = root / "frontend/src/views/production/ProductionSchedulingView.vue"
            view.parent.mkdir(parents=True)
            view.write_text("<template><h1 class=\"page-title\">生产排产</h1></template>", encoding="utf-8")
            out = verify_delete_on_target(root, "删除生产管理菜单下的生产排产子项")
            self.assertFalse(out.get("ok"), out)
            self.assertIn("生产排产", out.get("detail") or "")

    def test_verify_delete_inconclusive_without_feature_name(self):
        from app.code_dev.delete_verify import verify_delete_on_target
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "frontend/src/layouts").mkdir(parents=True)
            (root / "frontend/src/layouts/AppLayout.vue").write_text("export default {}\n", encoding="utf-8")
            out = verify_delete_on_target(root, "完整移除相关页面与菜单入口")
            self.assertFalse(out.get("ok"))
            self.assertTrue(out.get("inconclusive"))

    def test_delete_preflight_finds_orphan(self):
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_preflight import audit_delete_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "frontend/src/views/quality-management/Index.vue"
            p.parent.mkdir(parents=True)
            p.write_text("<template>品质概览</template>", encoding="utf-8")
            (root / "frontend/src/layouts").mkdir(parents=True)
            (root / "frontend/src/layouts/AppLayout.vue").write_text(
                "{ title: '品质概览' }\n", encoding="utf-8"
            )
            (root / "frontend/src/router").mkdir(parents=True)
            (root / "frontend/src/router/index.js").write_text(
                "path: 'quality-management/overview'\n", encoding="utf-8"
            )
            out = audit_delete_target(root, "删除品质概览页面")
            self.assertFalse(out.get("skip_cursor"))
            self.assertTrue(out.get("checks"))

    def test_delete_preflight_no_skip_without_enough_probes(self):
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_preflight import audit_delete_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = audit_delete_target(root, "删除品质概览功能")
            self.assertFalse(out.get("skip_cursor"))
            self.assertEqual(out.get("reason"), "probe_insufficient")

    def test_streamable_public_body_blocks_partial_stream(self):
        from app.code_dev.cursor_agent import _CursorStreamSink, sanitize_public_live_text, streamable_public_body

        explore = "正在分析需求：需要从品质管理模块移除「品质概览」。接下来查看工作区结构。"
        broken = explore + "\n里对 `/quality-management` 的特殊高亮判断。\n```javascript\nconst x = 1\n"
        partial = streamable_public_body(broken)
        self.assertNotIn("正在分析需求", partial)
        self.assertIn("特殊高亮判断", partial)
        self.assertNotIn("```", partial)
        self.assertNotIn("const x", partial)
        self.assertEqual(streamable_public_body(explore), "")
        full = broken + "\n```"
        pub = streamable_public_body(full)
        self.assertIn("特殊高亮判断", pub)
        self.assertNotIn("```", pub)
        self.assertNotIn("正在分析需求", pub)
        events: list[dict] = []
        bus = _CursorStreamSink(events.append)
        bus.add_assistant_piece(broken, from_delta=True)
        self.assertNotIn("正在分析", bus.final_text)
        self.assertIn("正在分析", bus.reasoning)
        self.assertIn("特殊高亮判断", bus.final_text)
        self.assertNotIn("```", bus.final_text)
        cleaned = sanitize_public_live_text(broken)
        self.assertNotIn("正在分析", cleaned)
        self.assertNotIn("特殊。高", cleaned)
        short = "先定位「品质概览」在前端菜单、路由、页面与后端接口中的引用。"
        events3: list[dict] = []
        bus3 = _CursorStreamSink(events3.append)
        bus3.add_assistant_piece(short, from_delta=True)
        self.assertNotIn("品质概览", bus3.final_text)
        self.assertIn("先定位", bus3.reasoning)

    def test_exploration_routes_to_thinking_and_strips_fence_prefix(self):
        from app.code_dev.cursor_agent import _CursorStreamSink, sanitize_public_live_text

        explore = "开始处理 ZR-WorkBuddy 沙箱中的改码任务。正在定位「品质概览」在前端路由、菜单和页面中的定义位置。"
        code = explore + "\n\n已改路由入口。\n\n```javascript\nconst x = 1\n```"
        events: list[dict] = []
        bus = _CursorStreamSink(events.append)
        bus.add_assistant_piece(code, from_delta=True)
        self.assertIn("正在定位", bus.reasoning)
        self.assertIn("已改路由入口", bus.final_text)
        self.assertNotIn("```", bus.final_text)
        self.assertNotIn("const x", bus.final_text)
        self.assertNotIn("正在定位", bus.final_text)
        cleaned = sanitize_public_live_text(code)
        self.assertIn("已改路由入口", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertNotIn("正在定位", cleaned)

    def test_partial_delivery_routes_to_replace_delivery_not_live(self):
        from app.code_dev.cursor_agent import _CursorStreamSink, _split_process_delivery

        proc, delivery = _split_process_delivery("说明方")
        self.assertEqual(proc, "")
        self.assertEqual(delivery, "说明方")
        doc = (
            "说明方案\n**结论**\n已从品质管理移除「品质概览」。\n"
            "**改动文件**\n- 无\n"
        )
        events: list[dict] = []
        bus = _CursorStreamSink(events.append)
        bus.seed_process("正在沙箱内改码。")
        bus.add_assistant_piece("说明方", from_delta=True)
        bus.add_assistant_piece(doc, from_delta=True)
        self.assertNotIn("说明方案", bus.final_text)
        self.assertTrue(any(e.get("type") == "replace_delivery" for e in events))
        del_events = [e for e in events if e.get("type") == "replace_delivery"]
        self.assertIn("结论", del_events[-1].get("text") or "")

    def test_dedupe_spaced_sentences_and_word_overlap(self):
        from app.code_dev.cursor_agent import (
            _absorb_text,
            _collapse_phrase_dups,
            _collapse_repeated,
            _concat_overlap,
            _dedupe_spaced_sentences,
            _ensure_code_fences,
            _line_looks_like_code,
            _repair_smashed_code,
        )

        messy = (
            "开始分析删除「品质概览」的需求。需要清理前端页面、路由、布局组件，以及后端接口和菜单数据。"
            " 开始分析删除「品质概览」的需求。需要清理前端页面、路由、布局组件，以及后端接口和菜单数据。"
        )
        deduped = _dedupe_spaced_sentences(messy)
        self.assertEqual(deduped.count("开始分析删除"), 1)
        glued = _concat_overlap("正在查看 Qual", "ityOverviewView.vue")
        self.assertEqual(glued, "正在查看 QualityOverviewView.vue")
        code_glued = _concat_overlap("from datetime", "import date, datetime")
        self.assertEqual(code_glued, "from datetime\nimport date, datetime")
        fenced = (
            "```python\nfrom datetime import date\nfrom sqlalchemy import Base\nclass Foo:\n    pass\n```"
        )
        collapsed = _collapse_repeated(fenced + "\n\n" + fenced)
        self.assertIn("from datetime import date\nfrom sqlalchemy import Base", collapsed)
        self.assertEqual(collapsed.count("from datetime import date"), 1)
        broken = _collapse_phrase_dups("定位「。品质概览」在菜单、路由。")
        self.assertNotIn("「。", broken)
        self.assertIn("定位", broken)
        self.assertFalse(_line_looks_like_code(""))
        self.assertFalse(_line_looks_like_code("```"))
        smashed = _repair_smashed_code("from __future__ importannotationsrelationshipfrom app.database importBase")
        self.assertIn("import annotations", smashed)
        self.assertIn("from app.database import Base", smashed)
        empty_fences = _ensure_code_fences("说明如下。\n\n```text\n\n```\n\n```text\n\n```")
        self.assertNotIn("```text", empty_fences)
        vue = _ensure_code_fences("`import { ref } from 'vue'`\n`const TYPE_MAP = {`")
        self.assertIn("```", vue)
        self.assertIn("import { ref }", vue)

    def test_delete_verify_passes_when_menu_removed(self):
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_verify import verify_delete_on_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = root / "frontend/src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                "children: [\n"
                "  { path: '/quality-management/inspection-tasks', title: '检验任务' },\n"
                "],\n",
                encoding="utf-8",
            )
            router = root / "frontend/src/router/index.js"
            router.parent.mkdir(parents=True, exist_ok=True)
            router.write_text(
                "redirect: '/quality-management/inspection-tasks'\n",
                encoding="utf-8",
            )
            out = verify_delete_on_target(root, "品质管理菜单删除检验方案功能")
            self.assertTrue(out.get("ok"))

    def test_delete_verify_fails_when_menu_remains(self):
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_verify import verify_delete_on_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = root / "frontend/src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                "{ path: '/quality-management/inspection-plans', title: '检验方案' },\n",
                encoding="utf-8",
            )
            out = verify_delete_on_target(root, "删除检验方案功能")
            self.assertFalse(out.get("ok"))
            self.assertIn("检验方案", out.get("detail") or "")

    def test_delete_verify_fails_when_inspection_tasks_route_remains(self):
        """只改菜单、路由/页面仍在时，删除检验任务不得验尸通过。"""
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_verify import verify_delete_on_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = root / "frontend/src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                "children: [\n"
                "  { path: '/quality-management/inspection-entry', title: '录入检验' },\n"
                "],\n",
                encoding="utf-8",
            )
            router = root / "frontend/src/router/index.js"
            router.parent.mkdir(parents=True, exist_ok=True)
            router.write_text(
                "import InspectionTasksView from '../views/quality-management/InspectionTasksView.vue'\n"
                "path: 'quality-management/inspection-tasks',\n"
                "name: 'quality-inspection-tasks',\n",
                encoding="utf-8",
            )
            view = root / "frontend/src/views/production/InspectionTasksView.vue"
            view.parent.mkdir(parents=True, exist_ok=True)
            view.write_text("<template>检验任务</template>", encoding="utf-8")
            out = verify_delete_on_target(root, "品质管理删除检验任务功能")
            self.assertFalse(out.get("ok"), out)
            detail = out.get("detail") or ""
            self.assertTrue(
                "inspection-tasks" in detail
                or "InspectionTasksView" in detail
                or "页面/API" in detail,
                detail,
            )

    def test_plan_delete_rejects_uncertain_cursor_paths(self):
        """不确定路径拒绝删除：Cursor 乱报兄弟页/共用 API 不得批准。"""
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_enforce import plan_delete_file_targets, validate_delete_plan

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "frontend/src/views/production").mkdir(parents=True)
            (root / "frontend/src/api").mkdir(parents=True)
            (root / "frontend/src/views/production/InspectionRecordsView.vue").write_text(
                '<template><h1 class="page-title">检验记录</h1></template>\n',
                encoding="utf-8",
            )
            (root / "frontend/src/views/production/InspectionEntryView.vue").write_text(
                '<template><h1 class="page-title">录入检验</h1></template>\n',
                encoding="utf-8",
            )
            (root / "frontend/src/api/qualityInspectionRecords.js").write_text(
                "export function fetchQualityInspectionRecords() {}\n",
                encoding="utf-8",
            )
            (root / "frontend/src/api/inspection.js").write_text(
                "export async function fetchInspectionRecords() {}\n",
                encoding="utf-8",
            )
            req = "品质管理删除检验记录功能"
            floor = plan_delete_file_targets(req, root)
            self.assertEqual(
                floor,
                ["frontend/src/views/production/InspectionRecordsView.vue"],
                floor,
            )
            approved, rejected = validate_delete_plan(
                [
                    "frontend/src/views/production/InspectionEntryView.vue",
                    "frontend/src/api/qualityInspectionRecords.js",
                    "frontend/src/api/inspection.js",
                    "frontend/src/views/production/InspectionRecordsView.vue",
                ],
                req,
                root,
            )
            self.assertEqual(
                approved,
                ["frontend/src/views/production/InspectionRecordsView.vue"],
                approved,
            )
            joined = "；".join(rejected)
            self.assertIn("InspectionEntryView", joined)
            self.assertIn("不确定", joined)
            self.assertTrue(
                "qualityInspectionRecords.js" in joined or "保护" in joined,
                rejected,
            )

    def test_plan_delete_inspection_records_keeps_entry_and_shared_api(self):
        """删检验记录：只删列表页，保留录入检验页与共用/设备 API。"""
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_enforce import plan_delete_file_targets, reconcile_delete_artifacts
        from app.code_dev.delete_verify import verify_delete_on_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "frontend/src/layouts").mkdir(parents=True)
            (root / "frontend/src/router").mkdir(parents=True)
            (root / "frontend/src/views/production").mkdir(parents=True)
            (root / "frontend/src/api").mkdir(parents=True)
            (root / "frontend/src/layouts/AppLayout.vue").write_text(
                "children: [\n"
                "  { path: '/quality-management/inspection-records', title: '检验记录' },\n"
                "  { path: '/quality-management/inspection-entry', title: '录入检验' },\n"
                "],\n",
                encoding="utf-8",
            )
            (root / "frontend/src/router/index.js").write_text(
                "import InspectionRecordsView from '../views/production/InspectionRecordsView.vue'\n"
                "path: 'quality-management/inspection-records',\n"
                "name: 'quality-inspection-records',\n",
                encoding="utf-8",
            )
            (root / "frontend/src/views/production/InspectionRecordsView.vue").write_text(
                '<template><h1 class="page-title">检验记录</h1></template>\n',
                encoding="utf-8",
            )
            (root / "frontend/src/views/production/InspectionEntryView.vue").write_text(
                '<template><h1 class="page-title">录入检验</h1></template>\n'
                "router.push('/quality-management/inspection-records')\n",
                encoding="utf-8",
            )
            (root / "frontend/src/api/qualityInspectionRecords.js").write_text(
                "export function fetchQualityInspectionRecords() {}\n",
                encoding="utf-8",
            )
            (root / "frontend/src/api/inspection.js").write_text(
                "export async function fetchInspectionRecords() {}\n",
                encoding="utf-8",
            )

            req = "品质管理删除检验记录功能"
            plan = plan_delete_file_targets(req, root)
            self.assertEqual(
                plan,
                ["frontend/src/views/production/InspectionRecordsView.vue"],
                plan,
            )
            import shutil

            sb = root / "_sb"
            shutil.copytree(root / "frontend", sb / "frontend")
            rec = reconcile_delete_artifacts(
                sandbox=sb,
                target=root,
                requirement=req,
                explicit_planned=plan,
            )
            self.assertIn("frontend/src/views/production/InspectionRecordsView.vue", rec["forced_deletes"])
            self.assertTrue((root / "frontend/src/views/production/InspectionEntryView.vue").is_file())
            self.assertTrue((root / "frontend/src/api/qualityInspectionRecords.js").is_file())
            self.assertTrue((root / "frontend/src/api/inspection.js").is_file())
            entry = (root / "frontend/src/views/production/InspectionEntryView.vue").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("/quality-management/inspection-records", entry)
            self.assertTrue(verify_delete_on_target(root, req).get("ok"))

    def test_strip_router_keeps_neighbor_with_nested_meta(self):
        from app.code_dev.delete_enforce import _js_syntax_ok, _strip_router_blocks

        raw = (
            "const routes = [\n"
            "  {\n"
            "    path: 'production/scheduling',\n"
            "    name: 'production-scheduling',\n"
            "    component: ProductionSchedulingView,\n"
            "    meta: { title: '生产排产', ...authRequired },\n"
            "  },\n"
            "  {\n"
            "    path: 'work-orders/:id?',\n"
            "    name: 'work-orders',\n"
            "    component: WorkOrdersView,\n"
            "    meta: { title: '生产工单', ...authRequired },\n"
            "  },\n"
            "]\n"
        )
        out, changed = _strip_router_blocks(raw, "生产排产")
        self.assertTrue(changed)
        self.assertNotIn("production/scheduling", out)
        self.assertNotIn("ProductionSchedulingView", out)
        self.assertIn("work-orders", out)
        self.assertIn("生产工单", out)
        self.assertTrue(_js_syntax_ok(out), out)
        self.assertFalse(
            bool(__import__("re").search(r"component:\s*\w+\s*,?\s*\n\s*\{", out)),
            out,
        )

    def test_delete_enforce_removes_files_and_menu(self):
        import shutil
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_enforce import reconcile_delete_artifacts

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            view = root / "frontend/src/views/quality-management/QualityOverviewView.vue"
            view.parent.mkdir(parents=True)
            view.write_text("<template>品质概览</template>", encoding="utf-8")
            layout = root / "frontend/src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                "children: [\n"
                "  { path: '/quality-management/overview', title: '品质概览', icon: Document },\n"
                "  { path: '/quality-management/inspection-tasks', title: '检验任务', icon: Document },\n"
                "],\n",
                encoding="utf-8",
            )
            router = root / "frontend/src/router/index.js"
            router.parent.mkdir(parents=True)
            router.write_text(
                "path: 'quality-management/overview',\ncomponent: QualityOverviewView,\n",
                encoding="utf-8",
            )
            sb = root / "sandbox"
            sb.mkdir()
            shutil.copytree(root / "frontend", sb / "frontend")
            rec = reconcile_delete_artifacts(
                sandbox=sb,
                target=root,
                requirement="品质管理菜单删除品质概览功能",
                assistant_text="已删除 `frontend/src/views/quality-management/QualityOverviewView.vue`",
            )
            self.assertTrue(rec.get("forced_deletes"))
            self.assertFalse(view.is_file())
            body = layout.read_text(encoding="utf-8")
            self.assertNotIn("品质概览", body)

    def test_run_job_no_local_shadow_of_run_cursor_local_agent(self):
        """回归：delete 分支内重复 import run_cursor_local_agent 会导致普通写码 UnboundLocalError。"""
        from pathlib import Path

        text = Path(_ENG, "app/code_dev/service.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "from .cursor_agent import build_delete_plan_prompt, run_cursor_local_agent",
            text,
        )
        self.assertIn("from .cursor_agent import build_prompt, run_cursor_local_agent", text)

    def test_verify_passes_when_inspection_plan_already_gone(self):
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_verify import verify_delete_on_target

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            layout = root / "frontend/src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                "children: [\n"
                "  { path: '/quality-management/inspection-tasks', title: '检验任务' },\n"
                "],\n",
                encoding="utf-8",
            )
            router = root / "frontend/src/router/index.js"
            router.parent.mkdir(parents=True)
            router.write_text("path: 'quality-management/inspection-tasks',\n", encoding="utf-8")
            out = verify_delete_on_target(root, "品质管理菜单删除检验方案功能")
            self.assertTrue(out.get("ok"), out.get("detail"))

    def test_resolve_delete_mode_defaults(self):
        from app.code_dev.config import _resolve_delete_mode

        self.assertEqual(_resolve_delete_mode({}), "cursor_plan")
        self.assertEqual(_resolve_delete_mode({"delete_mode": "cursor_plan"}), "cursor_plan")
        self.assertEqual(_resolve_delete_mode({"delete_engine_first": True}), "engine_first")
        self.assertEqual(_resolve_delete_mode({"delete_engine_first": False}), "cursor_full")

    def test_get_config_kwargs_match_dataclass(self):
        """防止 get_config 传了 dataclass 没有的字段（线上 TypeError）。"""
        import ast
        import inspect
        from dataclasses import fields

        from app.code_dev import config as cfg_mod

        tree = ast.parse(inspect.getsource(cfg_mod.get_config))
        call = next(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "CodeDevConfig"
            ),
            None,
        )
        self.assertIsNotNone(call)
        passed = {kw.arg for kw in call.keywords if kw.arg}
        declared = {f.name for f in fields(cfg_mod.CodeDevConfig)}
        self.assertFalse(
            passed - declared,
            f"get_config 传了未声明字段: {sorted(passed - declared)}",
        )
        # 冒烟：真实构造不得抛 TypeError
        cfg = cfg_mod.CodeDevConfig(
            delete_plan_timeout_sec=120,
            live_stream_delay_sec=0.045,
        )
        self.assertEqual(cfg.delete_plan_timeout_sec, 120)
        self.assertEqual(cfg.live_stream_delay_sec, 0.045)

    def test_parse_delete_plan_from_text(self):
        from app.code_dev.delete_enforce import parse_delete_plan_from_text

        text = (
            "定位完成。\n\n"
            "## 删除清单\n"
            "- `frontend/src/views/quality-management/InspectionPlansView.vue`：页面\n"
            "- frontend/src/api/qualityInspectionPlans.js\n"
        )
        paths = parse_delete_plan_from_text(text)
        self.assertIn("frontend/src/views/quality-management/InspectionPlansView.vue", paths)
        self.assertIn("frontend/src/api/qualityInspectionPlans.js", paths)

    def test_validate_delete_plan_blocks_menu_and_merges_engine_floor(self):
        import tempfile
        from pathlib import Path

        from app.code_dev.delete_enforce import validate_delete_plan

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            view = root / "frontend/src/views/quality-management/InspectionPlansView.vue"
            view.parent.mkdir(parents=True)
            view.write_text("<template>检验方案</template>", encoding="utf-8")
            layout = root / "frontend/src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text("title: '检验方案'", encoding="utf-8")

            approved, rejected = validate_delete_plan(
                [
                    "frontend/src/layouts/AppLayout.vue",
                    "frontend/src/views/quality-management/InspectionPlansView.vue",
                    "frontend/src/views/missing.vue",
                ],
                "删除检验方案功能",
                root,
                write_scope=["frontend/src/views/quality-management"],
            )
            self.assertIn("frontend/src/views/quality-management/InspectionPlansView.vue", approved)
            self.assertTrue(any("菜单/路由" in r for r in rejected))
            self.assertTrue(any("不存在" in r for r in rejected))

    def test_nudge_vite_touches_index_html(self):
        import tempfile
        import time
        from pathlib import Path

        from app.code_dev.vite_reload import (
            nudge_vite_after_sync,
            read_vite_dev_port,
            resolve_vite_frontend_root,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fe = root / "frontend"
            fe.mkdir()
            (fe / "vite.config.js").write_text(
                "export default { server: { port: 5179 } }\n",
                encoding="utf-8",
            )
            index = fe / "index.html"
            index.write_text("<html></html>\n", encoding="utf-8")
            layout = fe / "src/layouts/AppLayout.vue"
            layout.parent.mkdir(parents=True)
            layout.write_text("<template></template>\n", encoding="utf-8")
            cache = fe / "node_modules/.vite"
            cache.mkdir(parents=True)
            (cache / "deps").mkdir()
            (cache / "deps/x").write_text("1", encoding="utf-8")

            self.assertEqual(resolve_vite_frontend_root(root), fe.resolve())
            self.assertEqual(read_vite_dev_port(fe), 5179)
            before = index.stat().st_mtime
            time.sleep(0.02)
            out = nudge_vite_after_sync(
                root,
                synced_files=["frontend/src/layouts/AppLayout.vue"],
                deleted_files=["frontend/src/views/production/InspectionTasksView.vue"],
                force=True,
            )
            self.assertTrue(out.get("ok"), out)
            self.assertFalse(out.get("skipped"), out)
            # 无本机 Vite 进程时不会软重启，仍清缓存并触碰入口
            self.assertFalse(out.get("restarted"))
            self.assertGreaterEqual(index.stat().st_mtime, before)
            self.assertFalse(cache.exists())
            self.assertTrue(layout.exists())

            skip = nudge_vite_after_sync(root, synced_files=["README.md"], force=False)
            self.assertTrue(skip.get("skipped"))

    def test_reconcile_stale_jobs_marks_orphans_cancelled(self):
        import shutil
        import tempfile

        from app.code_dev import jobs as job_store
        from app.code_dev.service import reconcile_stale_jobs

        td = Path(tempfile.mkdtemp())
        try:
            job = job_store.create_job(
                td,
                user_id="",
                username="",
                thread_id="t",
                workspace=str(td),
                message="测试孤儿任务",
            )
            jid = job["id"]
            job_store.update_job(td, jid, status="running", progress="Cursor 工作中")
            n = reconcile_stale_jobs(td)
            self.assertEqual(n, 1)
            got = job_store.get_job(td, jid)
            self.assertEqual(got.get("status"), "cancelled")
            self.assertIn("引擎重启", str(got.get("error") or ""))
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

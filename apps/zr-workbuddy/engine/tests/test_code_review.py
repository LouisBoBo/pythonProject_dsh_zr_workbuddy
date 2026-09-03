"""code_review P0-3 单元测试（不调 LLM、不读用户真实工程）。"""
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


class CodeReviewTests(unittest.TestCase):
    def test_validate_rejects_home(self):
        from app.code_review.workspace import validate_review_root

        out = validate_review_root(str(Path.home()))
        self.assertFalse(out.get("ok"))

    def test_list_skips_sensitive(self):
        from app.code_review.config import CodeReviewConfig
        from app.code_review.local_files import select_files_for_review

        root = Path(_ENG) / "data" / "_test_cr_ws"
        root.mkdir(parents=True, exist_ok=True)
        try:
            (root / "app.py").write_text("x=1\n", encoding="utf-8")
            (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
            cfg = CodeReviewConfig(max_files=10)
            selected, warnings = select_files_for_review(root, scope_root=root, explicit_files=None, cfg=cfg)
            self.assertIn("app.py", selected)
            self.assertTrue(all(".env" not in p for p in selected))
        finally:
            for p in root.iterdir():
                if p.is_file():
                    p.unlink()
            try:
                root.rmdir()
            except OSError:
                pass

    def test_loads_viprasol_skill_prompt(self):
        from app.code_review.skill_prompt import (
            build_review_system_prompt,
            clear_skill_cache,
            skill_dir,
        )

        clear_skill_cache()
        self.assertTrue(skill_dir().is_dir())
        self.assertTrue((skill_dir() / "references" / "viprasol-skill.md").is_file())
        self.assertTrue((skill_dir() / "references" / "workbuddy-gate-90.md").is_file())
        prompt = build_review_system_prompt()
        self.assertGreater(len(prompt), 5000)
        self.assertIn(":::code_review_findings", prompt)
        self.assertTrue("OWASP" in prompt or "Viprasol" in prompt or "viprasol" in prompt.lower())
        self.assertIn("workbuddy-gate-90", prompt)

    def test_format_strips_batch_notes(self):
        from app.code_review.findings import format_findings_report

        report = format_findings_report(
            [],
            summary="已审 3 文件。\n\n**分批纪要**：\n- 第 1 批：xxx\n- 第 2 批：yyy",
            files_reviewed=["a.py"],
            local_path="/tmp/x",
        )
        self.assertNotIn("分批纪要", report)
        self.assertNotIn("第 1 批", report)
        self.assertIn("代码审核汇总报告", report)
        self.assertIn("已审 3 文件", report)

    def test_parse_findings(self):
        from app.code_review.findings import format_findings_report, parse_findings

        text = (
            "摘要：发现一个 SQL 风险。\n"
            ":::code_review_findings\n"
            '[{"file":"a.py","line":3,"severity":"high","title":"SQL","description":"未参数化","code_snippet":"q=f\\"select {x}\\"","fix_suggestion":"用参数化"}]\n'
            ":::\n"
        )
        prose, findings = parse_findings(text)
        self.assertIn("摘要", prose)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "high")
        report = format_findings_report(findings, summary=prose, files_reviewed=["a.py"], local_path="/tmp/x")
        self.assertIn("代码审核汇总报告", report)
        self.assertIn("🔴 高危", report)
        self.assertIn("// ❌ 当前代码", report)
        self.assertIn("四、审核结论", report)
        self.assertNotIn("分批纪要", report)

    def test_select_skips_markdown(self):
        from app.code_review.config import CodeReviewConfig
        from app.code_review.local_files import select_files_for_review

        root = Path(_ENG) / "data" / "_test_cr_md"
        root.mkdir(parents=True, exist_ok=True)
        try:
            (root / "README.md").write_text("# hi\n", encoding="utf-8")
            (root / "Main.java").write_text("class Main {}\n", encoding="utf-8")
            cfg = CodeReviewConfig(max_files=10)
            selected, _warnings = select_files_for_review(root, scope_root=root, explicit_files=None, cfg=cfg)
            self.assertIn("Main.java", selected)
            self.assertTrue(all(not p.endswith(".md") for p in selected))
        finally:
            for p in root.iterdir():
                if p.is_file():
                    p.unlink()
            try:
                root.rmdir()
            except OSError:
                pass

    def test_select_skips_vendor_and_prioritizes_openapi(self):
        from app.code_review.config import CodeReviewConfig
        from app.code_review.local_files import is_security_hot_file, select_files_for_review

        root = Path(_ENG) / "data" / "_test_cr_vendor"
        (root / "web" / "static" / "vendor").mkdir(parents=True, exist_ok=True)
        (root / "deploy").mkdir(parents=True, exist_ok=True)
        (root / "api").mkdir(parents=True, exist_ok=True)
        try:
            (root / "web" / "static" / "vendor" / "vis-network.min.js").write_text("x" * 100, encoding="utf-8")
            (root / "api" / "main.py").write_text("print(1)\n", encoding="utf-8")
            (root / "deploy" / "openapi_tools.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
            cfg = CodeReviewConfig(max_files=10)
            selected, _ = select_files_for_review(root, scope_root=root, explicit_files=None, cfg=cfg)
            self.assertTrue(all("vendor" not in p and not p.endswith(".min.js") for p in selected))
            self.assertIn("deploy/openapi_tools.yaml", selected)
            self.assertTrue(is_security_hot_file("deploy/openapi_tools.yaml"))
            self.assertEqual(selected[0], "deploy/openapi_tools.yaml")
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)

    def test_parse_findings_from_json_fence(self):
        from app.code_review.findings import parse_findings, prose_claims_issues

        text = (
            "发现公网未鉴权。\n"
            "```json\n"
            '[{"file":"deploy/openapi.yaml","line":16,"severity":"P0","title":"无鉴权","description":"公网匿名"}]\n'
            "```\n"
        )
        prose, findings = parse_findings(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "critical")
        self.assertEqual(findings[0].priority, "P0")
        self.assertTrue(prose_claims_issues("存在公网未鉴权风险"))
        self.assertFalse(prose_claims_issues("本批未发现安全问题"))

    def test_severity_p1_p2_not_collapsed_to_p0(self):
        from app.code_review.enrich import seed_findings_from_files
        from app.code_review.findings import format_findings_report, parse_findings

        text = (
            ":::code_review_findings\n"
            "["
            '{"file":"a.py","line":1,"severity":"P1","title":"规范","description":"中危"},'
            '{"file":"b.py","line":2,"severity":"P2","title":"命名","description":"低危"},'
            '{"file":"c.py","line":3,"severity":"medium","title":"性能","description":"中危2"}'
            "]\n"
            ":::\n"
        )
        _, findings = parse_findings(text)
        self.assertEqual(findings[0].severity, "medium")
        self.assertEqual(findings[0].priority, "P1")
        self.assertEqual(findings[1].severity, "low")
        self.assertEqual(findings[1].priority, "P2")
        self.assertEqual(findings[2].priority, "P1")

        seeded = seed_findings_from_files(
            [
                {
                    "path": "cfg.py",
                    "content": 'password = "SuperSecret123"\nTODO: cleanup\nexcept:\n  pass\n',
                }
            ]
        )
        bands = {f.priority for f in seeded}
        self.assertIn("P1", bands, seeded)
        self.assertIn("P2", bands, seeded)
        report = format_findings_report(seeded + findings, files_reviewed=["a.py"])
        self.assertIn("🟡 中危", report)
        self.assertIn("🟢 低危", report)
    def test_enrich_openapi_public_http_and_no_auth(self):
        from app.code_review.enrich import seed_findings_from_files

        yaml_text = (
            "openapi: 3.0.3\n"
            "servers:\n"
            "  - url: http://175.178.238.31\n"
            "    description: public\n"
            "paths:\n"
            "  /api/defect/query:\n"
            "    get:\n"
            "      summary: q\n"
            "      responses:\n"
            '        "200":\n'
            "          description: ok\n"
        )
        seeded = seed_findings_from_files(
            [{"path": "deploy/openapi_graphrag_tools.yaml", "content": yaml_text}]
        )
        titles = " ".join(f.title for f in seeded)
        self.assertTrue(any(f.severity == "critical" for f in seeded), seeded)
        self.assertIn("HTTP", titles)
        self.assertTrue("鉴权" in titles or "security" in titles.lower() or "匿名" in " ".join(f.description for f in seeded))

    def test_enrich_skips_loopback_and_env_secret(self):
        from app.code_review.enrich import seed_findings_from_files

        seeded = seed_findings_from_files(
            [
                {
                    "path": "deploy/start.sh",
                    "content": (
                        'curl http://127.0.0.1:8000/health\n'
                        'docker exec -e NEO4J_PASSWORD="$NEO4J_PASSWORD" c \\\n'
                    ),
                }
            ]
        )
        self.assertEqual(seeded, [], [f.title for f in seeded])

    def test_enrich_internal_http_nginx_not_critical(self):
        from app.code_review.enrich import seed_findings_from_files

        yaml_text = (
            "openapi: 3.0.3\n"
            "servers:\n"
            "  - url: http://nginx/v1\n"
            "paths:\n"
            "  /api/x:\n"
            "    get:\n"
            "      summary: q\n"
            "      responses:\n"
            '        "200":\n'
            "          description: ok\n"
        )
        seeded = seed_findings_from_files(
            [{"path": "tools/query-openapi.yaml", "content": yaml_text}]
        )
        http_hits = [f for f in seeded if "HTTP" in f.title]
        self.assertTrue(http_hits, seeded)
        self.assertTrue(all(f.severity == "medium" for f in http_hits), http_hits)
        self.assertTrue(all(f.priority == "P1" for f in http_hits), http_hits)

    def test_enrich_skips_private_lan_ip(self):
        from app.code_review.enrich import seed_findings_from_files

        seeded = seed_findings_from_files(
            [
                {
                    "path": "backend/app/config.py",
                    "content": 'mes_api_base: str = "http://192.168.49.11:6682"\n',
                }
            ]
        )
        self.assertEqual(seeded, [], [f.title for f in seeded])

    def test_run_blocked_when_disabled(self):
        from app.code_review import ops

        with mock.patch.object(ops, "get_config") as gc:
            from app.code_review.config import CodeReviewConfig

            gc.return_value = CodeReviewConfig(enabled=False)
            out = ops.run_review(local_path="/tmp/x")
        self.assertFalse(out.get("ok"))
        self.assertIn("未开启", out.get("detail") or "")

    def test_is_code_review_question(self):
        from app.code_review.intent import is_code_review_question

        self.assertTrue(is_code_review_question("审核代码 /Users/a/project"))
        self.assertTrue(is_code_review_question("帮我审查一下代码有没有安全问题"))
        self.assertFalse(is_code_review_question("今天产量多少"))
        self.assertFalse(is_code_review_question("在 /Users/a/b 开发员工工时报表页面"))

    def test_chat_code_review_returns_pick_card(self):
        from app.code_review import chat_bridge
        from app.code_review.config import CodeReviewConfig

        with mock.patch.object(chat_bridge.plugins_store, "is_enabled", return_value=True):
            with mock.patch.object(chat_bridge, "get_config") as gc:
                gc.return_value = CodeReviewConfig(
                    enabled=True, default_workspace="/Users/a/demo"
                )
                with mock.patch.object(chat_bridge, "availability", return_value={"ok": True}):
                    out = asyncio.run(chat_bridge.handle_chat_code_review("审核代码"))
        ui = out.get("code_review_ui") or {}
        self.assertEqual(ui.get("kind"), "pick")
        self.assertEqual(ui.get("workspace"), "/Users/a/demo")
        self.assertIn("确认卡", out.get("reply") or "")

    def test_run_review_async_mock_llm(self):
        from app.code_review.config import CodeReviewConfig
        from app.code_review import ops

        root = Path(_ENG) / "data" / "_test_cr_run"
        root.mkdir(parents=True, exist_ok=True)
        try:
            (root / "package.json").write_text("{}", encoding="utf-8")
            (root / "main.py").write_text("def f():\n  return 1\n", encoding="utf-8")
            cfg = CodeReviewConfig(enabled=True, max_files=5)

            async def fake_llm(**kwargs):
                return {
                    "ok": True,
                    "reply": "ok",
                    "summary": "无问题",
                    "findings": [],
                    "files_reviewed": ["main.py"],
                    "file_count": 1,
                    "bytes_read": 20,
                    "warnings": [],
                    "local_path": str(root),
                    "scope": "",
                    "focus": "",
                    "source": "code_review",
                    "data_source": "code_review",
                }

            with mock.patch.object(ops, "get_config", return_value=cfg):
                with mock.patch.object(ops, "availability", return_value={"ok": True}):
                    with mock.patch("app.code_review.review.run_llm_review", side_effect=fake_llm):
                        out = asyncio.run(
                            ops.run_review_async(local_path=str(root), persist=False)
                        )
            self.assertTrue(out.get("ok"), out)
        finally:
            for p in root.iterdir():
                if p.is_file():
                    p.unlink()
            try:
                root.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()

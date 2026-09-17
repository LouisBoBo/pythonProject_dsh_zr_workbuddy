"""本机「我的空间」单测：catalog / 报告入库 / 删除 / 保留清理；钩子 fail-soft。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class SpaceCatalogTests(unittest.TestCase):
    def setUp(self):
        # 落在引擎目录下，避免沙箱写 /tmp 导致 catalog 与直连 sqlite 路径不一致
        base = os.path.join(_ENG, "data", "_test_space")
        os.makedirs(base, exist_ok=True)
        self._tmpdir = tempfile.TemporaryDirectory(dir=base)
        from app.space import catalog

        self.catalog = catalog
        catalog.set_data_dir(self._tmpdir.name)

    def tearDown(self):
        self.catalog.set_data_dir(None)
        self._tmpdir.cleanup()

    def test_session_body_and_report_artifact(self):
        s = self.catalog.upsert_session(
            session_id="sess-1",
            user_id="u_hebo",
            title="审码一次",
            body_text="摘要：修好了登录",
            body_kind="summary",
        )
        self.assertEqual(s["id"], "sess-1")
        self.assertIn("修好了", s["body_text"])
        rel, n = self.catalog.write_report_file(
            user_id="u_hebo",
            artifact_id="cr-abc",
            body="# 报告\n通过",
        )
        self.assertTrue(rel.startswith("space/files/"))
        art = self.catalog.upsert_artifact(
            artifact_id="cr-abc",
            session_id="sess-1",
            user_id="u_hebo",
            kind="code_review_report",
            title="报告",
            relpath=rel,
            bytes_n=n,
        )
        self.assertEqual(art["kind"], "code_review_report")
        sess = self.catalog.get_session("sess-1")
        self.assertEqual(sess["artifact_count"], 1)
        body = self.catalog.read_artifact_body(art)
        self.assertIn("通过", body)
        listed = self.catalog.list_sessions(user_id="u_hebo")
        self.assertEqual(len(listed), 1)

    def test_user_isolation_and_delete(self):
        self.catalog.upsert_session(session_id="s-a", user_id="u_a", title="A")
        self.catalog.upsert_session(session_id="s-b", user_id="u_b", title="B")
        self.assertEqual(len(self.catalog.list_sessions(user_id="u_a")), 1)
        self.assertFalse(self.catalog.delete_session("s-b", user_id="u_a"))
        self.assertTrue(self.catalog.delete_session("s-a", user_id="u_a"))
        self.assertIsNone(self.catalog.get_session("s-a"))

    def test_purge_expired(self):
        from app.space import purge_expired

        r = self.catalog.upsert_session(session_id="old", user_id="u_hebo", title="旧")
        self.assertIsNotNone(r)
        # 把 updated_at 拨到很久以前（走 catalog API，避免直连路径不一致）
        import sqlite3

        db = str(self.catalog._db_path())
        self.assertTrue(os.path.isfile(db), f"missing db at {db} tmp={self._tmpdir.name}")
        conn = sqlite3.connect(db)
        try:
            tables = [x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            self.assertIn("sessions", tables, f"tables={tables} db={db}")
            conn.execute("UPDATE sessions SET updated_at = 1 WHERE id = 'old'")
            conn.commit()
        finally:
            conn.close()
        out = purge_expired(user_id="u_hebo", dry_run=False, retention_days=1)
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(int(out.get("purged_sessions") or 0), 1)
        self.assertIsNone(self.catalog.get_session("old"))

    def test_ingest_report_fail_soft_and_redact(self):
        from app.space.hooks import ingest_code_review_report

        ingest_code_review_report(
            {
                "id": "cr-test01",
                "ok": True,
                "reply": "结论通过\napi_key=" + ("sk-" + "abcdefghijklmnopqrstuvwxyz"),
                "session_id": "session-11111111-1111-1111-1111-111111111111",
                "user_id": "u_hebo",
            }
        )
        sess = self.catalog.get_session("session-11111111-1111-1111-1111-111111111111")
        self.assertIsNotNone(sess)
        self.assertEqual(sess.get("dsh_path"), "session-11111111-1111-1111-1111-111111111111")
        self.assertNotIn("sk-abcdefghijklmnop", sess.get("body_text") or "")
        art = self.catalog.get_artifact("cr-test01")
        self.assertEqual(art["kind"], "code_review_report")
        body = self.catalog.read_artifact_body(art)
        self.assertIn("结论通过", body)

    def test_ingest_never_raises(self):
        from app.space.hooks import ingest_code_dev_job, ingest_code_review_report

        ingest_code_review_report(None)  # type: ignore[arg-type]
        ingest_code_dev_job({"id": "ldj-x", "status": "running"})  # 非终态忽略
        # 仅有交付文案、无真实源码 → 不写资料库
        ingest_code_dev_job(
            {
                "id": "ldj-ok1",
                "status": "succeeded",
                "user_id": "u_hebo",
                "ui_session_id": "session-22222222-2222-2222-2222-222222222222",
                "delivery_text": "已同步 2 个文件",
                "synced_files": ["a.js", "b.js"],
                "messages": [{"role": "user", "content": "改一下按钮"}],
            }
        )
        self.assertIsNone(
            self.catalog.get_session("session-22222222-2222-2222-2222-222222222222")
        )
        arts = self.catalog.list_artifacts(user_id="u_hebo", limit=20)
        self.assertFalse(any(a.get("kind") == "delivery_summary" for a in arts))

    def test_ingest_synced_code_files(self):
        from pathlib import Path

        from app.space.hooks import ingest_code_dev_job

        ws = Path(self._tmpdir.name) / "ws"
        (ws / "src").mkdir(parents=True)
        (ws / "src" / "chat.py").write_text("print('hi')\n", encoding="utf-8")
        (ws / "src" / "untouched.py").write_text("KEEP\n", encoding="utf-8")
        (ws / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (ws / "bin.dat").write_bytes(b"\x00\x01\x02")
        sid = "session-44444444-4444-4444-4444-444444444444"
        ingest_code_dev_job(
            {
                "id": "ldj-code1",
                "status": "succeeded",
                "user_id": "u_hebo",
                "ui_session_id": sid,
                "workspace": str(ws),
                "delivery_text": "写完了",
                "changed_files": ["src/chat.py"],
                "synced_files": [
                    "src/chat.py",
                    "src/untouched.py",  # 误入同步列表但未在 changed → 不应入库
                    ".env",
                    "bin.dat",
                    "删除 old.py",
                    "../escape.py",
                ],
                "messages": [{"role": "user", "content": "开发专业的Web界面"}],
            }
        )
        arts = self.catalog.list_artifacts(user_id="u_hebo", limit=50)
        kinds = {a.get("kind") for a in arts}
        self.assertNotIn("delivery_summary", kinds)
        self.assertIn("code_file", kinds)
        code_arts = [a for a in arts if a.get("kind") == "code_file"]
        self.assertEqual(len(code_arts), 1)
        self.assertIn("chat.py", code_arts[0].get("title") or "")
        self.assertNotIn("untouched", (code_arts[0].get("title") or ""))
        body = self.catalog.read_artifact_body(code_arts[0])
        self.assertIn("print('hi')", body)
        # 失败任务不收源码
        ingest_code_dev_job(
            {
                "id": "ldj-fail1",
                "status": "failed",
                "user_id": "u_hebo",
                "ui_session_id": sid,
                "workspace": str(ws),
                "synced_files": ["src/chat.py"],
                "messages": [{"role": "user", "content": "失败任务"}],
            }
        )
        codes_after = [
            a
            for a in self.catalog.list_artifacts(user_id="u_hebo", limit=50)
            if a.get("kind") == "code_file"
        ]
        self.assertEqual(len(codes_after), 1)

    def test_ingest_from_delivery_text_fallback(self):
        from pathlib import Path

        from app.space.hooks import ingest_code_dev_job

        ws = Path(self._tmpdir.name) / "ws2"
        (ws / "frontend/src/api/reports").mkdir(parents=True)
        target = ws / "frontend/src/api/reports/employeeWorkHours.js"
        target.write_text("export const dim = 'employee_date'\n", encoding="utf-8")
        sid = "session-55555555-5555-5555-5555-555555555555"
        ingest_code_dev_job(
            {
                "id": "ldj-deliv1",
                "status": "succeeded",
                "user_id": "u_hebo",
                "ui_session_id": sid,
                "workspace": str(ws),
                "delivery_text": (
                    "**改动文件**\n"
                    "- `frontend/src/api/reports/employeeWorkHours.js`：默认 dimension\n"
                ),
                "changed_files": [],
                "synced_files": [],
                "messages": [{"role": "user", "content": "员工工时报表"}],
            }
        )
        codes = [
            a
            for a in self.catalog.list_artifacts(user_id="u_hebo", limit=50)
            if a.get("kind") == "code_file"
        ]
        self.assertTrue(any("employeeWorkHours" in (a.get("title") or "") for a in codes))

    def test_backfill_cursor_coding_ccj(self):
        import os
        from pathlib import Path

        from app.space.hooks import backfill_cursor_coding_files, _job_dict_from_ccj

        ws = Path(self._tmpdir.name) / "ws"
        (ws / "src").mkdir(parents=True)
        (ws / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
        ccj_home = Path(self._tmpdir.name) / "cursor-coding"
        (ccj_home / "jobs").mkdir(parents=True)
        raw = {
            "id": "ccj-20260915-test0001-abcd",
            "status": "succeeded",
            "workspace": str(ws),
            "dsh_session_id": "session-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "requirement": "加一列班别",
            "changed_files": ["src/a.py", "backend/erp.db"],
            "synced_files": ["src/a.py"],
        }
        (ccj_home / "jobs" / "ccj-20260915-test0001-abcd.json").write_text(
            __import__("json").dumps(raw), encoding="utf-8"
        )
        mapped = _job_dict_from_ccj(raw, user_id="u_hebo")
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped["ui_session_id"], raw["dsh_session_id"])
        no_sid = dict(raw)
        no_sid["dsh_session_id"] = ""
        self.assertIsNone(_job_dict_from_ccj(no_sid, user_id="u_hebo"))
        old = os.environ.get("CURSOR_CODING_HOME")
        os.environ["CURSOR_CODING_HOME"] = str(ccj_home)
        try:
            out = backfill_cursor_coding_files(user_id="u_hebo", limit=10)
        finally:
            if old is None:
                os.environ.pop("CURSOR_CODING_HOME", None)
            else:
                os.environ["CURSOR_CODING_HOME"] = old
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(int(out.get("ingested_jobs") or 0), 1)
        sess = self.catalog.get_session("session-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertIsNotNone(sess)
        codes = [
            a
            for a in self.catalog.list_artifacts(user_id="u_hebo", limit=50)
            if a.get("kind") == "code_file" and "a.py" in (a.get("title") or "")
        ]
        self.assertTrue(codes)

    def test_upsert_artifact_no_reassign_user(self):
        self.catalog.upsert_artifact(
            artifact_id="art-own-1",
            session_id="sess-a",
            user_id="u_hebo",
            kind="pcb_8d_report",
            title="A",
            relpath="space/files/u_hebo/reports/x.md",
            bytes_n=10,
        )
        out = self.catalog.upsert_artifact(
            artifact_id="art-own-1",
            session_id="sess-b",
            user_id="u_admin",
            kind="pcb_8d_report",
            title="Stolen",
            relpath="space/files/u_admin/reports/x.md",
            bytes_n=99,
        )
        self.assertEqual(out.get("user_id"), "u_hebo")
        self.assertEqual(out.get("title"), "A")

    def test_backfill_partial_code_files_and_secret_skip(self):
        from pathlib import Path

        from app.space.hooks import ingest_code_dev_job, _backfill_should_skip_job, _is_secret_rel

        self.assertTrue(_is_secret_rel("engine/config/config.yaml"))
        self.assertTrue(_is_secret_rel(".env.local"))
        ws = Path(self._tmpdir.name) / "ws_partial"
        (ws / "src").mkdir(parents=True)
        (ws / "src" / "a.py").write_text("a=1\n", encoding="utf-8")
        (ws / "src" / "b.py").write_text("b=2\n", encoding="utf-8")
        job = {
            "id": "ldj-partial01",
            "status": "succeeded",
            "user_id": "u_hebo",
            "ui_session_id": "session-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "workspace": str(ws),
            "changed_files": ["src/a.py"],
            "synced_files": ["src/a.py"],
            "messages": [{"role": "user", "content": "先改 a"}],
        }
        ingest_code_dev_job(job)
        self.assertTrue(_backfill_should_skip_job(job, user_id="u_hebo"))
        job2 = dict(job)
        job2["changed_files"] = ["src/a.py", "src/b.py"]
        job2["synced_files"] = ["src/a.py", "src/b.py"]
        self.assertFalse(_backfill_should_skip_job(job2, user_id="u_hebo"))
        ingest_code_dev_job(job2)
        codes = [
            a
            for a in self.catalog.list_artifacts(user_id="u_hebo", limit=80)
            if a.get("kind") == "code_file" and "partial" in str(a.get("id") or "")
        ]
        titles = " ".join(a.get("title") or "" for a in codes)
        self.assertIn("a.py", titles)
        self.assertIn("b.py", titles)


class SpaceApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        from app.auth import paths as auth_paths
        from app.space import catalog

        self._auth_paths = auth_paths
        self.catalog = catalog
        auth_paths.set_data_dir(os.path.join(self._tmpdir.name, "auth"))
        catalog.set_data_dir(os.path.join(self._tmpdir.name, "space"))

    def tearDown(self):
        self._auth_paths.set_data_dir(None)
        self.catalog.set_data_dir(None)
        self._tmpdir.cleanup()

    def test_api_list_delete_requires_login(self):
        from fastapi.testclient import TestClient

        from app.auth.users import ensure_seed_users
        from app.main import app
        from app.space.hooks import ingest_code_review_report

        ensure_seed_users()
        ingest_code_review_report(
            {
                "id": "cr-api01",
                "ok": True,
                "reply": "API 测试报告",
                "session_id": "session-33333333-3333-3333-3333-333333333333",
                "user_id": "u_hebo",
            }
        )
        with TestClient(app) as client:
            bare = client.get("/api/space/sessions")
            self.assertEqual(bare.status_code, 401)
            login = client.post(
                "/api/auth/login",
                json={"username": "hebo", "password": "hebo123"},
            )
            # 种子账号可能须改密
            token = login.json().get("token")
            if login.json().get("must_change_password"):
                client.post(
                    "/api/auth/change-password",
                    json={
                        "username": "hebo",
                        "old_password": "hebo123",
                        "new_password": "hebo12345",
                    },
                )
                login = client.post(
                    "/api/auth/login",
                    json={"username": "hebo", "password": "hebo12345"},
                )
                token = login.json().get("token")
            headers = {"Authorization": "Bearer " + token}
            lst = client.get("/api/space/sessions", headers=headers)
            self.assertEqual(lst.status_code, 200)
            self.assertTrue(lst.json().get("ok"))
            arts = client.get(
                "/api/space/artifacts?kind=code_review_report",
                headers=headers,
            )
            self.assertTrue(arts.json().get("ok"))
            self.assertGreaterEqual(len(arts.json().get("artifacts") or []), 1)
            one = client.get("/api/space/artifacts/cr-api01", headers=headers)
            self.assertIn("API 测试报告", one.json().get("body") or "")
            # 无档案行不得凭 UUID 打开会话
            ghost = client.get(
                "/api/space/sessions/session-99999999-9999-9999-9999-999999999999/locate-dsh",
                headers=headers,
            )
            self.assertEqual(ghost.status_code, 404)
            deleted = client.delete("/api/space/artifacts/cr-api01", headers=headers)
            self.assertTrue(deleted.json().get("ok"))


class SpacePcb8dSyncTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._drafts = tempfile.TemporaryDirectory()
        from app.space import catalog

        self.catalog = catalog
        catalog.set_data_dir(self._tmpdir.name)

    def tearDown(self):
        self.catalog.set_data_dir(None)
        self._tmpdir.cleanup()
        self._drafts.cleanup()

    def test_sync_md_into_space(self):
        from pathlib import Path
        from unittest import mock

        from app.space.sync_external import sync_pcb_8d_drafts

        md = Path(self._drafts.name) / "8D-20260915-1357-d106.md"
        md.write_text(
            "# PCB 8D 报告：焊盘虚焊\n\n- 报告编号：8D-20260915-1357-d106\n",
            encoding="utf-8",
        )
        with mock.patch("app.space.sync_external.pcb_8d_drafts_dir", return_value=Path(self._drafts.name)):
            out = sync_pcb_8d_drafts(user_id="u_hebo")
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(out.get("ingested") or 0, 1)
        art = self.catalog.get_artifact("8D-20260915-1357-d106")
        self.assertIsNotNone(art)
        self.assertEqual(art.get("kind"), "pcb_8d_report")
        body = self.catalog.read_artifact_body(art)
        self.assertIn("焊盘虚焊", body)
        self.assertEqual(art.get("title"), "PCB 8D 报告：焊盘虚焊")
        sess = self.catalog.get_session("pcb8d:8D-20260915-1357-d106")
        self.assertIsNotNone(sess)
        self.assertEqual(sess.get("title"), "PCB 8D · 8D-20260915-1357-d106")
        self.assertAlmostEqual(int(sess["updated_at"]), int(md.stat().st_mtime), delta=2)
        tree = self.catalog.list_library(user_id="u_hebo")
        sessions = tree.get("sessions") if isinstance(tree, dict) else tree
        self.assertTrue(any(r.get("id") == "pcb8d:8D-20260915-1357-d106" for r in sessions))
        hit = next(r for r in sessions if r.get("id") == "pcb8d:8D-20260915-1357-d106")
        self.assertTrue(any(a.get("id") == "8D-20260915-1357-d106" for a in hit.get("artifacts") or []))
        self.assertEqual(int(tree.get("total") or 0), 1)


class SpaceLocateTests(unittest.TestCase):
    def test_only_bound_session_opens(self):
        from app.space.dsh_locate import bound_dsh_session_id, locate_dsh_session

        self.assertEqual(
            bound_dsh_session_id(
                catalog_id="review:cr-abc",
                dsh_path="session-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ),
            "session-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        )
        self.assertEqual(bound_dsh_session_id(catalog_id="pcb8d:8D-1", dsh_path=""), "")
        loc = locate_dsh_session(catalog_id="pcb8d:8D-1", needle="8D-1", cached_dsh_id="")
        self.assertEqual(loc.get("dsh_session_id"), "")
        self.assertEqual(loc.get("detail"), "no-binding")
        loc2 = locate_dsh_session(
            catalog_id="review:cr-x",
            cached_dsh_id="session-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )
        self.assertEqual(loc2.get("dsh_session_id"), "session-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        self.assertEqual(loc2.get("detail"), "bound")


class SpaceChatDocsTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        from app.space import catalog

        self.catalog = catalog
        catalog.set_data_dir(self._tmpdir.name)

    def tearDown(self):
        self.catalog.set_data_dir(None)
        self._tmpdir.cleanup()

    def test_ingest_test_case_from_jsonl(self):
        from pathlib import Path
        from unittest import mock

        from app.space.chat_docs import (
            is_knowledge_retrieval,
            is_ops_noise,
            looks_like_chat_document,
            sync_chat_docs_from_dsh,
        )

        short = "好的，我帮你写。"
        self.assertFalse(looks_like_chat_document(short))
        # 知识库/文档检索问答不进库（含「源自《…》」引用）
        kb_ans = (
            "一、FMEA 标准答案（源自《双面沉金板FMEA》中 V 割深度超差条目）\n\n"
            "潜在后果包括层间短路与客户退货。\n"
            + ("说明补充。\n" * 40)
        )
        self.assertTrue(is_knowledge_retrieval(kb_ans))
        self.assertFalse(looks_like_chat_document(kb_ans))
        kb_faq = (
            "一、五大检验关卡合格率（核心，权重 100%）\n\n"
            "二、P0 最着急：直接卡出货/客诉\n\n"
            "三、过程能力与抽样方案\n"
            + ("指标说明。\n" * 30)
        )
        self.assertTrue(is_knowledge_retrieval(kb_faq))
        self.assertFalse(looks_like_chat_document(kb_faq))
        self.assertTrue(is_knowledge_retrieval("二钻 / 二锣计价：先看成本内核，再看口径"))
        self.assertTrue(is_knowledge_retrieval('一、8 层板"专属"计费项'))
        self.assertTrue(is_knowledge_retrieval("一、公式\n\n加工费 = 基材 + 压合。"))
        self.assertTrue(
            is_knowledge_retrieval(
                "《PCB报价规则》第十四节「表面处理」按 **面积（元/㎡）** 计价，共四种："
            )
        )
        self.assertTrue(is_knowledge_retrieval("一、铜价折算（主口径）\n\n按当日铜价。"))
        self.assertTrue(is_knowledge_retrieval("1080 PP 片（半固化片）的价格是 **18 元/张**。"))
        # 写码/提交结论、菜单完成确认不进库
        conclusion = (
            "## 本轮结论\n\n写码已完成并同步到本机。\n\n"
            "## 做了什么\n\n- 改了菜单\n\n"
            "## 改动方案\n\n改 frontend catalog。\n\n"
            + ("细节。\n" * 40)
        )
        self.assertTrue(is_ops_noise(conclusion))
        self.assertFalse(looks_like_chat_document(conclusion))
        self.assertFalse(looks_like_chat_document("## 提交完成 ✅\n\n分支已推送。\n" + ("x\n" * 80)))
        self.assertFalse(
            looks_like_chat_document(
                "已完成「报表中心 → 质量管理」的彻底移除，并验证前端构建通过。\n"
                + ("核对路径。\n" * 40)
            )
        )
        self.assertFalse(
            looks_like_chat_document(
                "写码车道当前未开启（`code_dev.disabled`），无法生成写码工具卡。\n"
                + ("说明。\n" * 30)
            )
        )
        self.assertFalse(
            looks_like_chat_document(
                "已从「报表中心」彻底删除「设备停机报表」。\n" + ("落地核对。\n" * 40)
            )
        )
        # 「」引用菜单路径 ≠ 创作；须《》或创作词
        self.assertFalse(
            looks_like_chat_document("已在「报表中心」新增设备点检报表。\n" + ("说明。\n" * 40))
        )
        # 创作 AIGC 可进库
        story = (
            "《小红帽》\n\n"
            "奶奶，你的耳朵好大。好听到你的心跳。\n"
            "奶奶，你的眼睛好大。好看清你眼里的恐惧。\n"
            "奶奶，你的嘴巴好大——狼一口吞下她。\n"
            "腹中，真正的奶奶睁开比狼更大的眼。\n"
            "次日小红帽又来敲门。温柔的声音说：快进来呀。\n"
            "可昨天，是她亲手把奶奶埋进了后院。\n"
        )
        self.assertTrue(looks_like_chat_document(story))

        body = (
            "# 登录模块测试用例\n\n"
            "## TC-01 正确密码\n\n"
            "1. 打开登录页\n2. 输入账号密码\n3. 点击登录\n"
            "期望：进入首页。\n\n" + ("步骤补充说明。\n" * 50)
        )
        self.assertTrue(looks_like_chat_document(body))

        sid = "session-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        root = Path(self._tmpdir.name) / "dsh-sessions"
        sess_dir = root / "ws" / sid
        sess_dir.mkdir(parents=True)
        lines = [
            json.dumps({"type": "session/title", "data": {"title": "写一个测试用例"}}, ensure_ascii=False),
            json.dumps(
                {
                    "type": "assistant/message",
                    "data": {
                        "message": {
                            "id": "msg-test-001",
                            "role": "assistant",
                            "content": [{"type": "text", "text": body}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "type": "assistant/message",
                    "data": {
                        "message": {
                            "id": "msg-conclusion",
                            "role": "assistant",
                            "content": [{"type": "text", "text": conclusion}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "type": "assistant/message",
                    "data": {
                        "message": {
                            "id": "msg-story",
                            "role": "assistant",
                            "content": [{"type": "text", "text": story}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "type": "assistant/message",
                    "data": {
                        "message": {
                            "id": "msg-short",
                            "role": "assistant",
                            "content": [{"type": "text", "text": short}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
        ]
        (sess_dir / "session.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

        with mock.patch("app.space.chat_docs._sessions_root", return_value=root):
            out = sync_chat_docs_from_dsh(user_id="u_hebo")
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(out.get("ingested") or 0, 2)
        art = self.catalog.get_artifact("chat-msg-test-001")
        self.assertIsNotNone(art)
        self.assertEqual(art.get("kind"), "chat_document")
        self.assertEqual(art.get("session_id"), sid)
        sess = self.catalog.get_session(sid)
        self.assertEqual(sess.get("dsh_path"), sid)
        self.assertIn("登录模块测试用例", art.get("title") or "")
        self.assertIsNone(self.catalog.get_artifact("chat-msg-conclusion"))
        story_art = self.catalog.get_artifact("chat-msg-story")
        self.assertIsNotNone(story_art)
        self.assertIn("小红帽", story_art.get("title") or "")


class SpaceLibraryPagingTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        from app.space import catalog

        self.catalog = catalog
        catalog.set_data_dir(self._tmpdir.name)

    def tearDown(self):
        self.catalog.set_data_dir(None)
        self._tmpdir.cleanup()

    def test_purge_empty_keeps_sessions_with_docs(self):
        self.catalog.upsert_session(
            session_id="empty-1",
            user_id="u_hebo",
            title="空会话",
            body_text="",
        )
        self.catalog.upsert_session(
            session_id="with-doc",
            user_id="u_hebo",
            title="有文档",
            body_text="",
        )
        rel, n = self.catalog.write_report_file(
            user_id="u_hebo",
            artifact_id="doc-1",
            body="# hello\n",
        )
        self.catalog.upsert_artifact(
            artifact_id="doc-1",
            user_id="u_hebo",
            kind="chat_document",
            title="测试文档",
            relpath=rel,
            bytes_n=n,
            session_id="with-doc",
        )
        n_purged = self.catalog.purge_empty_sessions(user_id="u_hebo")
        self.assertGreaterEqual(n_purged, 1)
        self.assertIsNone(self.catalog.get_session("empty-1"))
        self.assertIsNotNone(self.catalog.get_session("with-doc"))
        packed = self.catalog.list_library(user_id="u_hebo", page=1, page_size=10)
        ids = [s.get("id") for s in packed.get("sessions") or []]
        self.assertIn("with-doc", ids)
        self.assertNotIn("empty-1", ids)

    def test_list_library_pagination(self):
        for i in range(12):
            sid = f"s-{i:02d}"
            self.catalog.upsert_session(
                session_id=sid,
                user_id="u_hebo",
                title=f"会话 {i}",
                body_text="",
                at=1_700_000_000 + i,
            )
            rel, n = self.catalog.write_report_file(
                user_id="u_hebo",
                artifact_id=f"a-{i:02d}",
                body="# x\n",
            )
            self.catalog.upsert_artifact(
                artifact_id=f"a-{i:02d}",
                user_id="u_hebo",
                kind="chat_document",
                title=f"文档 {i}",
                relpath=rel,
                bytes_n=n,
                session_id=sid,
            )
        p1 = self.catalog.list_library(user_id="u_hebo", page=1, page_size=10)
        p2 = self.catalog.list_library(user_id="u_hebo", page=2, page_size=10)
        self.assertEqual(p1.get("total"), 12)
        self.assertEqual(len(p1.get("sessions") or []), 10)
        self.assertEqual(len(p2.get("sessions") or []), 2)

    def test_list_library_sorts_by_latest_doc_time(self):
        """资料库会话应按最新文档时间倒序（新的在前），不单看 sessions.updated_at。"""
        # 会话 A：会话行很新，但文档很旧 → 应排后
        self.catalog.upsert_session(
            session_id="sess-old-docs",
            user_id="u_hebo",
            title="旧文档会话",
            body_text="",
            at=2_000_000_900,
        )
        rel_a, n_a = self.catalog.write_report_file(
            user_id="u_hebo", artifact_id="doc-old", body="# old\n"
        )
        self.catalog.upsert_artifact(
            artifact_id="doc-old",
            user_id="u_hebo",
            kind="chat_document",
            title="旧文档",
            relpath=rel_a,
            bytes_n=n_a,
            session_id="sess-old-docs",
            at=2_000_000_100,
        )
        # 会话 B：会话行较旧，文档最新 → 应排前
        self.catalog.upsert_session(
            session_id="sess-new-docs",
            user_id="u_hebo",
            title="新文档会话",
            body_text="",
            at=2_000_000_200,
        )
        rel_b, n_b = self.catalog.write_report_file(
            user_id="u_hebo", artifact_id="doc-new", body="# new\n"
        )
        self.catalog.upsert_artifact(
            artifact_id="doc-new",
            user_id="u_hebo",
            kind="chat_document",
            title="新文档",
            relpath=rel_b,
            bytes_n=n_b,
            session_id="sess-new-docs",
            at=2_000_000_800,
        )
        packed = self.catalog.list_library(user_id="u_hebo", page=1, page_size=10)
        ids = [s.get("id") for s in packed.get("sessions") or []]
        self.assertEqual(ids[:2], ["sess-new-docs", "sess-old-docs"])


if __name__ == "__main__":
    unittest.main()


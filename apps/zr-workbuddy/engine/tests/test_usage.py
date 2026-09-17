"""用量账本：解析与 JSONL 汇总（不调真实 LLM / Cursor）。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class UsageParseTests(unittest.TestCase):
    def test_openai_provider(self):
        from app.usage.parse import from_openai_usage

        t = from_openai_usage(
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )
        self.assertIsNotNone(t)
        self.assertEqual(t["quality"], "provider")
        self.assertEqual(t["total_tokens"], 15)
        self.assertEqual(t["prompt_tokens"], 10)

    def test_openai_empty_is_none(self):
        from app.usage.parse import from_openai_usage

        self.assertIsNone(from_openai_usage({}))
        self.assertIsNone(from_openai_usage(None))

    def test_sdk_usage(self):
        from app.usage.parse import from_sdk_usage

        class _U:
            input_tokens = 3
            output_tokens = 7

        t = from_sdk_usage(_U())
        self.assertEqual(t["quality"], "sdk")
        self.assertEqual(t["total_tokens"], 10)

    def test_sdk_camel_case_dict(self):
        from app.usage.parse import from_sdk_usage

        t = from_sdk_usage(
            {
                "inputTokens": 104588,
                "outputTokens": 2173,
                "cacheReadTokens": 73056,
                "cacheWriteTokens": 0,
                "totalTokens": 179817,
            }
        )
        self.assertEqual(t["quality"], "sdk")
        self.assertEqual(t["prompt_tokens"], 104588)
        self.assertEqual(t["cache_read_tokens"], 73056)
        self.assertEqual(t["total_tokens"], 179817)

    def test_cursor_exclusive_cache_parts(self):
        from app.usage.store import _event_parts

        p = _event_parts(
            {
                "prompt_tokens": 104588,
                "completion_tokens": 2173,
                "cache_read_tokens": 73056,
                "total_tokens": 179817,
            }
        )
        self.assertEqual(p["cache_hit"], 73056)
        self.assertEqual(p["cache_miss"], 104588)
        self.assertEqual(p["output"], 2173)
        self.assertEqual(p["tokens"], 179817)

    def test_dsh_exclusive_when_cache_gt_input(self):
        from app.usage.store import _event_parts

        p = _event_parts(
            {
                "prompt_tokens": 303,
                "completion_tokens": 383,
                "cache_read_tokens": 13824,
                "reasoning_tokens": 137,
                "total_tokens": 14647,
            }
        )
        self.assertEqual(p["cache_hit"], 13824)
        self.assertEqual(p["cache_miss"], 303)
        self.assertEqual(p["output"], 383)  # 不含 reasoning（官网口径）
        self.assertEqual(p["tokens"], 14510)  # 303+13824+383

    def test_missing_tokens(self):
        from app.usage.parse import missing_tokens

        m = missing_tokens()
        self.assertEqual(m["quality"], "missing")
        self.assertEqual(m["total_tokens"], 0)


class UsageStoreTests(unittest.TestCase):
    def test_default_dir_is_engine_data_usage(self):
        from app.usage import store

        self.assertTrue(store._DEFAULT_DIR.replace("\\", "/").endswith("engine/data/usage"))
        self.assertFalse(store._DEFAULT_DIR.replace("\\", "/").endswith("app/data/usage"))

    def test_append_and_summarize(self):
        from app.usage import store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                store.append_event(
                    source="llm",
                    lane="chat",
                    provider="deepseek",
                    model="deepseek-chat",
                    tokens={
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "total_tokens": 120,
                        "quality": "provider",
                    },
                )
                store.append_event(
                    source="cursor",
                    lane="code_dev_write",
                    provider="cursor",
                    model="composer-2.5",
                    tokens=None,
                    ok=True,
                )
                s = store.summarize(days=7)
                self.assertTrue(s.get("ok"))
                self.assertEqual(s["llm"]["calls"], 1)
                self.assertEqual(s["llm"]["tokens"], 120)
                self.assertEqual(s["llm"]["cache_miss"], 100)
                self.assertEqual(s["llm"]["output"], 20)
                self.assertEqual(s["cursor"]["calls"], 1)
                self.assertEqual(s["cursor"]["missing_calls"], 1)
                self.assertIn("llm_tokens", s["today"])
                self.assertIn("cursor_tokens", s["today"])
                self.assertIn("llm_calls", s["daily"][-1])
                self.assertIn("cursor_calls", s["daily"][-1])
                self.assertTrue(s["llm"]["models"])
                self.assertEqual(s["llm"]["models"][0]["model"], "deepseek-chat")
                lanes = {row["lane"] for row in s["by_lane"]}
                self.assertIn("chat", lanes)
                self.assertIn("code_dev_write", lanes)
                ev = store.list_events(limit=10)
                self.assertEqual(ev["count"], 2)
                self.assertEqual(ev["total"], 2)
                self.assertEqual(ev["page"], 1)
                self.assertEqual(ev["page_size"], 10)
                sources = {e["source"] for e in ev["events"]}
                self.assertEqual(sources, {"llm", "cursor"})
        finally:
            store.set_data_dir(prev)

    def test_list_events_newest_first_paginated(self):
        from app.usage import store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                for i, day in enumerate(("2026-09-01", "2026-09-10", "2026-09-14")):
                    store.append_event(
                        source="llm",
                        lane="dsh_chat",
                        provider="deepseek",
                        model="deepseek-v4-flash",
                        tokens={
                            "prompt_tokens": i + 1,
                            "completion_tokens": 1,
                            "cache_read_tokens": 0,
                            "cache_write_tokens": 0,
                            "reasoning_tokens": 0,
                            "total_tokens": i + 2,
                            "quality": "sdk",
                        },
                        ts=day + "T12:00:00+08:00",
                    )
                p1 = store.list_events(source="llm", page=1, page_size=2)
                self.assertEqual(p1["total"], 3)
                self.assertEqual(p1["count"], 2)
                self.assertTrue(p1["events"][0]["ts"].startswith("2026-09-14"))
                self.assertEqual(p1["events"][0]["label"], "DSH 聊天")
                self.assertEqual(p1["events"][0]["quality"], "session")
                p2 = store.list_events(source="llm", page=2, page_size=2)
                self.assertEqual(p2["count"], 1)
                self.assertTrue(p2["events"][0]["ts"].startswith("2026-09-01"))
        finally:
            store.set_data_dir(prev)

    def test_summarize_on_focus_day(self):
        from unittest import mock

        from app.usage import store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                for day in ("2026-09-01", "2026-09-10", "2026-09-14"):
                    store.append_event(
                        source="llm",
                        lane="dsh_chat",
                        provider="deepseek",
                        model="deepseek-v4-flash",
                        tokens={
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "cache_read_tokens": 0,
                            "cache_write_tokens": 0,
                            "reasoning_tokens": 0,
                            "total_tokens": 2,
                            "quality": "sdk",
                        },
                        ts=day + "T12:00:00+08:00",
                    )
                with mock.patch("app.usage.ingest_cursor.ingest_dsh_cursor_jobs"), mock.patch(
                    "app.usage.ingest_dsh_llm.ingest_dsh_sessions"
                ):
                    focused = store.summarize(days=7, on="2026-09-10")
                self.assertEqual(focused["on"], "2026-09-10")
                self.assertEqual(focused["to"], "2026-09-10")
                self.assertEqual(focused["from"], "2026-09-04")
                self.assertEqual(focused["today"]["llm"]["calls"], 1)
                self.assertEqual(focused["llm"]["calls"], 1)
                hours = focused.get("hourly") or []
                self.assertEqual(len(hours), 24)
                self.assertEqual(hours[12]["hour"], 12)
                self.assertEqual(hours[12]["llm_calls"], 1)
                self.assertEqual(hours[12]["llm_tokens"], 2)
                self.assertEqual(hours[11]["llm_calls"], 0)
                by_date = {row["date"]: row for row in (focused.get("monthly") or [])}
                self.assertEqual(focused.get("month"), "2026-09")
                self.assertEqual(by_date["2026-09-01"]["llm_calls"], 1)
                self.assertEqual(by_date["2026-09-10"]["llm_calls"], 1)
                self.assertTrue((focused.get("monthly") or [])[0]["date"] == "2026-09-01")
                day_ev = store.list_events(source="llm", on="2026-09-10")
                self.assertEqual(day_ev["total"], 1)
                self.assertTrue(day_ev["events"][0]["ts"].startswith("2026-09-10"))
        finally:
            store.set_data_dir(prev)


class UsageApiTests(unittest.TestCase):
    def test_summary_endpoint_ok(self):
        from fastapi.testclient import TestClient

        from app.auth import paths as auth_paths
        from app.auth.users import ensure_seed_users
        from app.main import app
        from app.usage import store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                auth_paths.set_data_dir(os.path.join(td, "auth"))
                ensure_seed_users()
                client = TestClient(app)
                login = client.post(
                    "/api/auth/login",
                    json={"username": "hebo", "password": "hebo123"},
                )
                self.assertEqual(login.status_code, 200)
                token = login.json()["token"]
                headers = {"Authorization": "Bearer " + token}
                store.append_event(
                    source="llm",
                    lane="pcb",
                    provider="deepseek",
                    model="deepseek-chat",
                    tokens={
                        "prompt_tokens": 8,
                        "completion_tokens": 2,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 0,
                        "total_tokens": 10,
                        "quality": "provider",
                    },
                )
                r = client.get("/api/usage/summary?days=7", headers=headers)
                self.assertEqual(r.status_code, 200)
                d = r.json()
                self.assertTrue(d.get("ok"))
                self.assertEqual(d.get("user_id"), "u_hebo")
                self.assertEqual(d["llm"]["tokens"], 10)
                r2 = client.get("/api/usage/daily?days=7", headers=headers)
                self.assertEqual(r2.status_code, 200)
                self.assertIn("daily", r2.json())
                r3 = client.get("/api/usage/events?limit=5", headers=headers)
                self.assertEqual(r3.status_code, 200)
                self.assertGreaterEqual(r3.json().get("count") or 0, 1)
                r4 = client.get("/api/usage/events?source=llm&page=1&page_size=10", headers=headers)
                self.assertEqual(r4.status_code, 200)
                body = r4.json()
                self.assertEqual(body.get("page"), 1)
                self.assertEqual(body.get("page_size"), 10)
                self.assertIn("total", body)
                r5 = client.get("/api/usage/summary?days=7&on=2099-01-01", headers=headers)
                self.assertEqual(r5.status_code, 200)
                self.assertEqual(r5.json().get("on"), r5.json().get("to"))
                # 未登录不可看用量
                client.post("/api/auth/logout", headers=headers)
                denied = client.get("/api/usage/summary?days=1")
                self.assertEqual(denied.status_code, 401)
                # admin 看不到 hebo 的账
                admin = client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "admin123"},
                )
                ah = {"Authorization": "Bearer " + admin.json()["token"]}
                other = client.get("/api/usage/summary?days=7", headers=ah)
                self.assertEqual(other.status_code, 200)
                self.assertEqual(other.json().get("user_id"), "u_admin")
                self.assertEqual(other.json()["llm"]["tokens"], 0)
        finally:
            store.set_data_dir(prev)
            auth_paths.set_data_dir(None)


class IngestCursorTests(unittest.TestCase):
    def test_slug_strips_dot_segments(self):
        from app.usage.ingest_cursor import _slug_sandbox

        self.assertEqual(
            _slug_sandbox("/Users/hebo/.zhongruan/cursor-coding/sandboxes/ccj-1"),
            "Users-hebo-zhongruan-cursor-coding-sandboxes-ccj-1",
        )

    def test_ingest_job_from_sqlite(self):
        import json
        import sqlite3
        from pathlib import Path
        from unittest import mock

        from app.usage import ingest_cursor, store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                root = os.path.join(td, "cc")
                jobs = os.path.join(root, "jobs")
                sb = os.path.join(root, "sandboxes", "ccj-test")
                dbdir = os.path.join(sb, ".cursor-sdk-store", "h")
                os.makedirs(jobs)
                os.makedirs(dbdir)
                db = os.path.join(dbdir, "index.db")
                conn = sqlite3.connect(db)
                conn.execute(
                    "CREATE TABLE runs (run_id TEXT, agent_id TEXT, status TEXT, "
                    "model TEXT, usage_json TEXT, started_at TEXT, finished_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
                    (
                        "run-1",
                        "agent-1",
                        "FINISHED",
                        "composer-2.5",
                        json.dumps(
                            {
                                "inputTokens": 100,
                                "outputTokens": 20,
                                "cacheReadTokens": 40,
                                "totalTokens": 160,
                            }
                        ),
                        "2026-09-14T03:07:55Z",
                        "2026-09-14T03:08:30Z",
                    ),
                )
                conn.commit()
                conn.close()
                job_path = os.path.join(jobs, "ccj-test.json")
                with open(job_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": "ccj-test",
                            "status": "succeeded",
                            "agent_id": "agent-1",
                            "run_id": "run-1",
                            "sandbox_path": sb,
                            "updated_at": "2026-09-14T03:08:31Z",
                        },
                        f,
                    )
                fake_projects = Path(td) / "cursor-projects"
                fake_projects.mkdir()
                with (
                    mock.patch.object(ingest_cursor, "_dsh_cursor_roots", return_value=[Path(root)]),
                    mock.patch.object(ingest_cursor, "_cursor_projects_root", return_value=fake_projects),
                ):
                    n = ingest_cursor.ingest_dsh_cursor_jobs(force=True)
                    self.assertEqual(n, 1)
                    s = store.summarize(days=7)
                    self.assertEqual(s["cursor"]["calls"], 1)
                    self.assertEqual(s["cursor"]["tokens"], 160)
                    n2 = ingest_cursor.ingest_dsh_cursor_jobs(force=True)
                    self.assertEqual(n2, 0)
        finally:
            store.set_data_dir(prev)

    def test_upgrade_missing_when_sqlite_appears(self):
        import json
        import sqlite3
        from pathlib import Path
        from unittest import mock

        from app.usage import ingest_cursor, store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                root = os.path.join(td, "cc")
                jobs = os.path.join(root, "jobs")
                sb = os.path.join(root, "sandboxes", "ccj-up")
                os.makedirs(jobs)
                os.makedirs(sb)
                job_path = os.path.join(jobs, "ccj-up.json")
                with open(job_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": "ccj-up",
                            "status": "succeeded",
                            "agent_id": "agent-1",
                            "run_id": "run-1",
                            "sandbox_path": sb,
                            "updated_at": "2026-09-14T03:08:31Z",
                        },
                        f,
                    )
                fake_projects = Path(td) / "cursor-projects"
                fake_projects.mkdir()
                with (
                    mock.patch.object(ingest_cursor, "_dsh_cursor_roots", return_value=[Path(root)]),
                    mock.patch.object(ingest_cursor, "_cursor_projects_root", return_value=fake_projects),
                ):
                    n = ingest_cursor.ingest_dsh_cursor_jobs(force=True)
                    self.assertEqual(n, 1)
                    s = store.summarize(days=7)
                    self.assertEqual(s["cursor"]["tokens"], 0)
                    self.assertEqual(s["cursor"]["missing_calls"], 1)
                    dbdir = os.path.join(sb, ".cursor-sdk-store", "h")
                    os.makedirs(dbdir)
                    db = os.path.join(dbdir, "index.db")
                    conn = sqlite3.connect(db)
                    conn.execute(
                        "CREATE TABLE runs (run_id TEXT, agent_id TEXT, status TEXT, "
                        "model TEXT, usage_json TEXT, started_at TEXT, finished_at TEXT)"
                    )
                    conn.execute(
                        "INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
                        (
                            "run-1",
                            "agent-1",
                            "FINISHED",
                            "composer-2.5",
                            json.dumps(
                                {
                                    "inputTokens": 100,
                                    "outputTokens": 20,
                                    "cacheReadTokens": 40,
                                    "totalTokens": 160,
                                }
                            ),
                            "2026-09-14T03:07:55Z",
                            "2026-09-14T03:08:30Z",
                        ),
                    )
                    conn.commit()
                    conn.close()
                    n2 = ingest_cursor.ingest_dsh_cursor_jobs(force=True)
                    self.assertEqual(n2, 1)
                    s2 = store.summarize(days=7)
                    self.assertEqual(s2["cursor"]["calls"], 1)
                    self.assertEqual(s2["cursor"]["tokens"], 160)
                    self.assertEqual(s2["cursor"]["missing_calls"], 0)
        finally:
            store.set_data_dir(prev)


class IngestDshLlmTests(unittest.TestCase):
    def test_ingest_session_usage_chunks(self):
        import json
        from pathlib import Path
        from unittest import mock

        from app.usage import ingest_dsh_llm, store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                sid = "session-aaaabbbb-cccc-dddd-eeee-ffffffffffff"
                sdir = os.path.join(td, "sessions", "--ws--", sid)
                os.makedirs(sdir)
                lines = [
                    {"type": "session", "id": sid, "createdAt": 1789355182512},
                    {
                        "type": "request/header",
                        "time": 1789355219174,
                        "data": {
                            "header": {
                                "config": {
                                    "provider": "deepseek-official",
                                    "model": "deepseek-v4-flash",
                                }
                            }
                        },
                    },
                    {
                        "type": "assistant/chunk",
                        "time": 1789355222101,
                        "data": {
                            "turn": 1,
                            "step": 1,
                            "chunk": {
                                "type": "usage",
                                "usage": {
                                    "inputTokens": 303,
                                    "outputTokens": 383,
                                    "cacheReadTokens": 13824,
                                    "reasoningTokens": 137,
                                },
                            },
                        },
                    },
                ]
                with open(os.path.join(sdir, "session.jsonl"), "w", encoding="utf-8") as f:
                    for row in lines:
                        f.write(json.dumps(row, separators=(",", ":")) + "\n")
                with mock.patch.object(ingest_dsh_llm, "_sessions_root", return_value=Path(td) / "sessions"):
                    n = ingest_dsh_llm.ingest_dsh_sessions(force=True)
                    self.assertEqual(n, 1)
                    s = store.summarize(days=7)
                    self.assertEqual(s["llm"]["calls"], 1)
                    self.assertEqual(s["llm"]["cache_hit"], 13824)
                    self.assertEqual(s["llm"]["cache_miss"], 303)
                    self.assertEqual(s["llm"]["output"], 383)  # 不含 reasoning
                    self.assertEqual(s["llm"]["tokens"], 14510)  # 303+13824+383
                    n2 = ingest_dsh_llm.ingest_dsh_sessions(force=True)
                    self.assertEqual(n2, 0)
                    ev = store.list_events(source="llm", page=1, page_size=10)
                    self.assertEqual(ev["events"][0]["quality"], "session")
                    self.assertEqual(ev["events"][0]["label"], "DSH 聊天")
        finally:
            store.set_data_dir(prev)

    def test_session_ingest_skips_after_before_cutoff(self):
        from pathlib import Path
        from unittest import mock

        from app.usage import ingest_dsh_llm, store

        prev = store._data_dir_override
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                sid = "session-aaaabbbb-cccc-dddd-eeee-ffffffffffff"
                sdir = os.path.join(td, "sessions", "--ws--", sid)
                os.makedirs(sdir)
                lines = [
                    {"type": "session", "id": sid},
                    {
                        "type": "request/header",
                        "time": 1789355219174,
                        "data": {
                            "header": {
                                "config": {
                                    "provider": "deepseek-official",
                                    "model": "deepseek-v4-flash",
                                }
                            }
                        },
                    },
                    {
                        "type": "assistant/chunk",
                        "time": 1789355222101,
                        "data": {
                            "turn": 1,
                            "step": 1,
                            "chunk": {
                                "type": "usage",
                                "usage": {"inputTokens": 10, "outputTokens": 2},
                            },
                        },
                    },
                ]
                with open(os.path.join(sdir, "session.jsonl"), "w", encoding="utf-8") as f:
                    for row in lines:
                        f.write(json.dumps(row, separators=(",", ":")) + "\n")
                with mock.patch.object(ingest_dsh_llm, "_sessions_root", return_value=Path(td) / "sessions"):
                    n = ingest_dsh_llm.ingest_dsh_sessions(
                        force=True, before="2026-09-14T00:00:00+08:00"
                    )
                    self.assertEqual(n, 0)
                    n2 = ingest_dsh_llm.ingest_dsh_sessions(
                        force=True, before="2026-09-15T00:00:00+08:00"
                    )
                    self.assertEqual(n2, 1)
        finally:
            store.set_data_dir(prev)


class IngestPathGuardTests(unittest.TestCase):
    def test_sessions_root_rejects_outside_home(self):
        from unittest import mock
        from pathlib import Path

        from app.usage import ingest_dsh_llm

        with mock.patch.dict(os.environ, {"DSH_SESSIONS_DIR": "/tmp/workbuddy-usage-not-home"}, clear=False):
            root = ingest_dsh_llm._sessions_root()
        self.assertEqual(root, Path.home() / ".dsh" / "sessions")

    def test_cursor_env_root_rejects_outside_home(self):
        from unittest import mock
        from pathlib import Path

        from app.usage import ingest_cursor

        with mock.patch.dict(os.environ, {"CURSOR_CODING_HOME": "/tmp/workbuddy-cursor-not-home"}, clear=False):
            roots = ingest_cursor._dsh_cursor_roots()
        self.assertNotIn(Path("/tmp/workbuddy-cursor-not-home"), roots)
        self.assertIn(Path.home() / ".zhongruan" / "cursor-coding", roots)

    def test_read_runs_without_ids_does_not_sum_whole_db(self):
        import json
        import sqlite3
        from pathlib import Path
        from unittest import mock

        from app.usage import ingest_cursor, store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                root = os.path.join(td, "cc")
                jobs = os.path.join(root, "jobs")
                sb = os.path.join(root, "sandboxes", "ccj-noid")
                dbdir = os.path.join(sb, ".cursor-sdk-store", "h")
                os.makedirs(jobs)
                os.makedirs(dbdir)
                db = os.path.join(dbdir, "index.db")
                conn = sqlite3.connect(db)
                conn.execute(
                    "CREATE TABLE runs (run_id TEXT, agent_id TEXT, status TEXT, "
                    "model TEXT, usage_json TEXT, started_at TEXT, finished_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
                    (
                        "run-other",
                        "agent-other",
                        "FINISHED",
                        "composer-2.5",
                        json.dumps({"inputTokens": 999, "outputTokens": 1, "totalTokens": 1000}),
                        "2026-09-14T03:07:55Z",
                        "2026-09-14T03:08:30Z",
                    ),
                )
                conn.commit()
                conn.close()
                with open(os.path.join(jobs, "ccj-noid.json"), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": "ccj-noid",
                            "status": "succeeded",
                            "sandbox_path": sb,
                            "updated_at": "2026-09-14T03:08:31Z",
                        },
                        f,
                    )
                fake_projects = Path(td) / "cursor-projects"
                fake_projects.mkdir()
                with (
                    mock.patch.object(ingest_cursor, "_dsh_cursor_roots", return_value=[Path(root)]),
                    mock.patch.object(ingest_cursor, "_cursor_projects_root", return_value=fake_projects),
                ):
                    n = ingest_cursor.ingest_dsh_cursor_jobs(force=True)
                    self.assertEqual(n, 1)
                    s = store.summarize(days=7)
                    self.assertEqual(s["cursor"]["tokens"], 0)
                    self.assertEqual(s["cursor"]["missing_calls"], 1)
        finally:
            store.set_data_dir(prev)

    def test_sandbox_outside_allowed_roots_ignored(self):
        import json
        from pathlib import Path
        from unittest import mock

        from app.usage import ingest_cursor, store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                root = os.path.join(td, "cc")
                jobs = os.path.join(root, "jobs")
                os.makedirs(jobs)
                with open(os.path.join(jobs, "ccj-out.json"), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": "ccj-out",
                            "status": "succeeded",
                            "agent_id": "agent-1",
                            "run_id": "run-1",
                            "sandbox_path": "/etc",
                            "updated_at": "2026-09-14T03:08:31Z",
                        },
                        f,
                    )
                fake_projects = Path(td) / "cursor-projects"
                fake_projects.mkdir()
                with (
                    mock.patch.object(ingest_cursor, "_dsh_cursor_roots", return_value=[Path(root)]),
                    mock.patch.object(ingest_cursor, "_cursor_projects_root", return_value=fake_projects),
                ):
                    n = ingest_cursor.ingest_dsh_cursor_jobs(force=True)
                    self.assertEqual(n, 1)
                    s = store.summarize(days=7)
                    self.assertEqual(s["cursor"]["tokens"], 0)
        finally:
            store.set_data_dir(prev)


class UsageSideChannelTests(unittest.TestCase):
    def test_ingest_memory_audit(self):
        import sqlite3
        from pathlib import Path
        from unittest import mock

        from app.usage import ingest_dsh_side, store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                mem = Path(td) / "memory"
                mem.mkdir()
                db = mem / "memory.db"
                con = sqlite3.connect(db)
                con.execute(
                    "CREATE TABLE llm_audit_logs ("
                    "id INTEGER PRIMARY KEY, timestamp TEXT, trigger_source TEXT, "
                    "operation_type TEXT, model_id TEXT, input_tokens INT, "
                    "output_tokens INT, total_tokens INT, status TEXT, error_message TEXT, "
                    "duration_ms INT, related_memory_ids TEXT)"
                )
                con.execute(
                    "INSERT INTO llm_audit_logs VALUES "
                    "(1,'2026-09-16T11:00:00Z','autoDream','dream_consolidate',"
                    "'deepseek-official:deepseek-v4-flash',100,20,120,'success',NULL,20000,NULL)"
                )
                con.execute(
                    "INSERT INTO llm_audit_logs VALUES "
                    "(2,'2026-09-16T11:01:00Z','autoSummarize','summarize_compress',"
                    "'deepseek-official:deepseek-v4-flash',0,0,0,'success',NULL,5000,NULL)"
                )
                con.commit()
                con.close()
                with mock.patch.object(ingest_dsh_side, "_memory_db", return_value=db):
                    n = ingest_dsh_side.ingest_dsh_memory_audit(force=True)
                self.assertEqual(n, 2)
                known = store.known_job_ids()
                self.assertIn("dsh-mem-audit:1", known)
                self.assertIn("dsh-mem-audit:2", known)
                # audit 有真值的保留；零 token 的应升为 estimate
                ev = [e for e in store.iter_all_events() if e.get("job_id") == "dsh-mem-audit:2"][0]
                self.assertEqual(ev.get("quality"), "estimate")
                self.assertGreater(int(ev.get("total_tokens") or 0), 0)
                # second pass dedupes
                with mock.patch.object(ingest_dsh_side, "_memory_db", return_value=db):
                    self.assertEqual(ingest_dsh_side.ingest_dsh_memory_audit(force=True), 0)
        finally:
            store.set_data_dir(prev)

    def test_console_normalize_day(self):
        from app.usage.deepseek_console import _normalize_day, _pick_day_row

        rows = [
            {"date": "2026-09-15", "request_count": 1, "total_tokens": 10},
            {"date": "2026-09-16", "request_count": 209, "total_tokens": 1921220, "cost": 4.52},
        ]
        row = _pick_day_row(rows, "2026-09-16")
        self.assertIsNotNone(row)
        out = _normalize_day(row, "2026-09-16", cost_cny=4.52)
        self.assertTrue(out["ok"])
        self.assertEqual(out["calls"], 209)
        self.assertEqual(out["tokens"], 1921220)
        self.assertEqual(out["cost_cny"], 4.52)

    def test_llm_meter_ingest_and_dedupe(self):
        from unittest import mock
        from pathlib import Path
        from app.usage import ingest_llm_meter, store

        prev = store._data_dir_override
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                meter_dir = Path(td) / "llm-meter"
                meter_dir.mkdir()
                row = {
                    "v": 1,
                    "id": "meter_20260917120000_abc123",
                    "ts": "2026-09-17T12:00:00+08:00",
                    "source": "dsh_knowledge",
                    "provider": "deepseek-official",
                    "model": "deepseek-v4-flash",
                    "session_id": "session-x",
                    "ok": True,
                    "finish": "stop",
                    "error": "",
                    "quality": "provider",
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "cache_read_tokens": 50,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 5,
                    "total_tokens": 999,
                    "duration_ms": 100,
                }
                row_synth = {
                    **row,
                    "id": "meter_20260917120000_synth",
                    "total_tokens": 0,
                }
                (meter_dir / "events.jsonl").write_text(
                    json.dumps(row, ensure_ascii=False)
                    + "\n"
                    + json.dumps(row_synth, ensure_ascii=False)
                    + "\n",
                    encoding="utf-8",
                )
                # 误采诱饵：.lock / .tmp 不得入库
                (meter_dir / "events.jsonl.lock").write_text(
                    json.dumps({**row, "id": "meter_lock_should_skip", "total_tokens": 9999})
                    + "\n",
                    encoding="utf-8",
                )
                (meter_dir / "events.jsonl.tmp").write_text(
                    json.dumps({**row, "id": "meter_tmp_should_skip", "total_tokens": 8888})
                    + "\n",
                    encoding="utf-8",
                )
                with mock.patch.object(ingest_llm_meter, "_meter_dir", return_value=meter_dir):
                    with mock.patch.object(
                        ingest_llm_meter, "_current_user_id", create=True, return_value="u_hebo"
                    ):
                        # override 下默认跳过；force 才采
                        self.assertEqual(ingest_llm_meter.ingest_llm_meter(force=False), 0)
                        n = ingest_llm_meter.ingest_llm_meter(force=True)
                        self.assertEqual(n, 2)
                        self.assertEqual(ingest_llm_meter.ingest_llm_meter(force=True), 0)
                by_id = {
                    e.get("job_id"): e
                    for e in store.iter_all_events()
                    if str(e.get("job_id") or "").startswith("meter_20260917120000")
                }
                self.assertEqual(int(by_id["meter_20260917120000_abc123"].get("total_tokens") or 0), 999)
                self.assertEqual(int(by_id["meter_20260917120000_synth"].get("total_tokens") or 0), 170)
                # 插件若误报 total=base+reasoning，入库应纠成 base
                row_bad = {
                    **row,
                    "id": "meter_20260917120000_badtotal",
                    "total_tokens": 175,  # 100+20+50+5
                }
                (meter_dir / "events.jsonl").write_text(
                    json.dumps(row_bad, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                with mock.patch.object(ingest_llm_meter, "_meter_dir", return_value=meter_dir):
                    with mock.patch.object(
                        ingest_llm_meter, "_current_user_id", create=True, return_value="u_hebo"
                    ):
                        self.assertEqual(ingest_llm_meter.ingest_llm_meter(force=True), 1)
                bad_ev = [
                    e
                    for e in store.iter_all_events()
                    if e.get("job_id") == "meter_20260917120000_badtotal"
                ]
                self.assertEqual(int(bad_ev[0].get("total_tokens") or 0), 170)
                self.assertEqual(by_id["meter_20260917120000_abc123"].get("lane"), "dsh_knowledge")
                self.assertEqual(int(by_id["meter_20260917120000_abc123"].get("reasoning_tokens") or 0), 5)
                self.assertEqual(by_id["meter_20260917120000_abc123"].get("quality"), "provider")
                self.assertEqual(by_id["meter_20260917120000_abc123"].get("user_id"), "u_hebo")
                bad = [
                    e
                    for e in store.iter_all_events()
                    if e.get("job_id") in {"meter_lock_should_skip", "meter_tmp_should_skip"}
                ]
                self.assertEqual(bad, [])
        finally:
            store.set_data_dir(prev)

    def test_meter_active_still_ingests_pre_meter_sessions(self):
        from unittest import mock
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.usage import store

        prev = store._data_dir_override
        cutoff = datetime(2026, 9, 17, 10, 17, tzinfo=ZoneInfo("Asia/Shanghai"))
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                with mock.patch("app.usage.ingest_cursor.ingest_dsh_cursor_jobs"), mock.patch(
                    "app.usage.ingest_llm_meter.meter_active", return_value=True
                ), mock.patch("app.usage.ingest_llm_meter.ingest_llm_meter") as m_meter, mock.patch(
                    "app.usage.ingest_llm_meter.first_meter_datetime", return_value=cutoff
                ), mock.patch(
                    "app.usage.ingest_dsh_llm.ingest_dsh_sessions"
                ) as m_sess, mock.patch(
                    "app.usage.ingest_dsh_side.ingest_dsh_side_channels"
                ) as m_side, mock.patch(
                    "app.usage.report.flush_report"
                ), mock.patch(
                    "app.usage.store.supersede_pre_meter_side_lanes"
                ) as m_sup:
                    out = store.summarize(days=1, on="2026-09-17")
                    self.assertTrue(out.get("llm_meter_active"))
                    m_meter.assert_called()
                    m_sup.assert_called()
                    m_sess.assert_called()
                    self.assertEqual(m_sess.call_args.kwargs.get("before"), cutoff)
                    m_side.assert_called()
                    self.assertEqual(m_side.call_args.kwargs.get("before"), cutoff)
        finally:
            store.set_data_dir(prev)

    def test_meter_supersede_keeps_history_before_cutoff(self):
        from app.usage import store

        prev = store._data_dir_override
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                tokens_s = {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "quality": "session",
                }
                tokens_m = {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "quality": "provider",
                }
                store.append_event(
                    source="llm",
                    lane="dsh_chat",
                    provider="deepseek",
                    model="x",
                    tokens=tokens_s,
                    job_id="sess_old:t1:s1",
                    user_id="u_hebo",
                    ts="2026-09-16T12:00:00+08:00",
                    allow_active_fallback=False,
                )
                store.append_event(
                    source="llm",
                    lane="dsh_chat",
                    provider="deepseek",
                    model="x",
                    tokens=tokens_s,
                    job_id="sess_overlap:t1:s1",
                    user_id="u_hebo",
                    ts="2026-09-17T10:18:00+08:00",
                    allow_active_fallback=False,
                )
                store.append_event(
                    source="llm",
                    lane="dsh_chat",
                    provider="deepseek",
                    model="x",
                    tokens=tokens_m,
                    job_id="meter_keep_me",
                    user_id="u_hebo",
                    ts="2026-09-17T10:17:00+08:00",
                    allow_active_fallback=False,
                )
                n = store.supersede_pre_meter_side_lanes(since="2026-09-17T10:17:00+08:00")
                self.assertEqual(n, 1)
                self.assertEqual(store.supersede_pre_meter_side_lanes(), 0)
                jobs = {e.get("job_id") for e in store.iter_all_events()}
                self.assertIn("meter_keep_me", jobs)
                self.assertIn("sess_old:t1:s1", jobs)
                self.assertNotIn("sess_overlap:t1:s1", jobs)
        finally:
            store.set_data_dir(prev)

    def test_match_user_no_orphan_share(self):
        """空 user_id 不得对任意登录账号可见（防多账号串账）。"""
        from app.usage import store

        self.assertFalse(
            store._match_user({"user_id": "", "job_id": "meter_1", "lane": "dsh_chat"}, "u_a")
        )
        self.assertTrue(
            store._match_user({"user_id": "u_a", "job_id": "job1", "lane": "code_review"}, "u_a")
        )
        self.assertFalse(
            store._match_user({"user_id": "u_b", "job_id": "job1", "lane": "code_review"}, "u_a")
        )
        self.assertFalse(
            store._match_user({"user_id": "", "job_id": "eng_1", "lane": "code_review"}, "u_a")
        )

    def test_exclude_same_second_as_meter_cutoff(self):
        from app.usage import store

        cutoff = store.as_shanghai("2026-09-17T10:17:56.530+08:00")
        self.assertTrue(
            store.exclude_at_or_after_cutoff("2026-09-17T10:17:56+08:00", cutoff)
        )
        self.assertFalse(
            store.exclude_at_or_after_cutoff("2026-09-17T10:17:55+08:00", cutoff)
        )

    def test_event_ymd_uses_shanghai_calendar_day(self):
        from app.usage import store

        self.assertEqual(store._event_ymd({"ts": "2026-09-16T16:30:00+00:00"}), "2026-09-17")
        self.assertEqual(store._event_ymd({"ts": "2026-09-17T00:30:00+08:00"}), "2026-09-17")
        self.assertEqual(store._event_ymd({"ts": "2026-09-16T23:50:00+08:00"}), "2026-09-16")

    def test_bind_empty_meter_user_id(self):
        from app.usage import store

        prev = store._data_dir_override
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                store.append_event(
                    source="llm",
                    lane="dsh_chat",
                    provider="deepseek",
                    model="x",
                    tokens={
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "quality": "provider",
                    },
                    job_id="meter_orphan",
                    user_id="",
                    ts="2026-09-17T10:17:00+08:00",
                    allow_active_fallback=False,
                )
                n = store.bind_empty_meter_user_id("u_hebo")
                self.assertEqual(n, 1)
                ev = [e for e in store.iter_all_events() if e.get("job_id") == "meter_orphan"]
                self.assertEqual(ev[0].get("user_id"), "u_hebo")
                s = store.summarize(days=1, on="2026-09-17", user_id="u_hebo")
                self.assertEqual(s["today"]["llm_calls"], 1)
        finally:
            store.set_data_dir(prev)

    def test_summarize_does_not_rebind_orphans(self):
        """个人页读路径不得把空账号流水永久写给先打开的人。"""
        from unittest import mock
        from app.usage import store

        prev = store._data_dir_override
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                store.append_event(
                    source="llm",
                    lane="dsh_chat",
                    provider="deepseek",
                    model="x",
                    tokens={
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "quality": "provider",
                    },
                    job_id="meter_shared",
                    user_id="",
                    ts="2026-09-17T10:17:00+08:00",
                    allow_active_fallback=False,
                )
                with mock.patch("app.usage.ingest_cursor.ingest_dsh_cursor_jobs"), mock.patch(
                    "app.usage.ingest_llm_meter.meter_active", return_value=True
                ), mock.patch("app.usage.ingest_llm_meter.ingest_llm_meter"), mock.patch(
                    "app.usage.ingest_dsh_llm.ingest_dsh_sessions"
                ), mock.patch(
                    "app.usage.ingest_dsh_side.ingest_dsh_side_channels"
                ), mock.patch("app.usage.report.flush_report"):
                    s_a = store.summarize(days=1, on="2026-09-17", user_id="u_a")
                    s_b = store.summarize(days=1, on="2026-09-17", user_id="u_b")
                # 空账号不可见；读路径不得写归户
                self.assertEqual(s_a["today"]["llm_calls"], 0)
                self.assertEqual(s_b["today"]["llm_calls"], 0)
                ev = [e for e in store.iter_all_events() if e.get("job_id") == "meter_shared"]
                self.assertEqual(ev[0].get("user_id"), "")
        finally:
            store.set_data_dir(prev)

    def test_meter_ingest_ignores_forged_user_id(self):
        """meter JSONL 里的 user_id 可伪造，入库只认 ContextVar/active。"""
        from unittest import mock
        from pathlib import Path
        from app.usage import store, ingest_llm_meter

        prev = store._data_dir_override
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                meter_dir = Path(td) / "meter"
                meter_dir.mkdir()
                row = {
                    "id": "meter_20260917130000_forge",
                    "ts": "2026-09-17T13:00:00+08:00",
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "cache_read_tokens": 0,
                    "total_tokens": 15,
                    "ok": True,
                    "user_id": "u_attacker",
                }
                (meter_dir / "events.jsonl").write_text(
                    json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                with mock.patch.object(ingest_llm_meter, "_meter_dir", return_value=meter_dir):
                    with mock.patch.object(
                        ingest_llm_meter, "_current_user_id", create=True, return_value="u_hebo"
                    ):
                        self.assertEqual(ingest_llm_meter.ingest_llm_meter(force=True), 1)
                ev = [
                    e
                    for e in store.iter_all_events()
                    if e.get("job_id") == "meter_20260917130000_forge"
                ]
                self.assertEqual(ev[0].get("user_id"), "u_hebo")
        finally:
            store.set_data_dir(prev)

    def test_bind_empty_engine_user_id(self):
        """审码/PCB 等引擎直连空账号须归户，否则个人页漏计。"""
        from unittest import mock
        from app.usage import store

        prev = store._data_dir_override
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                store.append_event(
                    source="llm",
                    lane="code_review",
                    provider="deepseek",
                    model="x",
                    tokens={
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "cache_read_tokens": 0,
                        "total_tokens": 15,
                        "quality": "provider",
                    },
                    job_id="",
                    user_id="",
                    ts="2026-09-17T12:00:00+08:00",
                    allow_active_fallback=False,
                )
                store.append_event(
                    source="llm",
                    lane="dsh_other",
                    provider="deepseek",
                    model="x",
                    tokens={
                        "prompt_tokens": 3,
                        "completion_tokens": 1,
                        "total_tokens": 4,
                        "quality": "provider",
                    },
                    job_id="sess_side",
                    user_id="",
                    ts="2026-09-17T12:01:00+08:00",
                    allow_active_fallback=False,
                )
                n = store.bind_empty_meter_user_id("u_hebo")
                self.assertEqual(n, 2)
                by_lane = {e.get("lane"): e.get("user_id") for e in store.iter_all_events()}
                self.assertEqual(by_lane["code_review"], "u_hebo")
                self.assertEqual(by_lane["dsh_other"], "u_hebo")
                with mock.patch("app.usage.ingest_cursor.ingest_dsh_cursor_jobs"), mock.patch(
                    "app.usage.ingest_llm_meter.meter_active", return_value=False
                ), mock.patch(
                    "app.usage.ingest_llm_meter.ingest_llm_meter"
                ), mock.patch(
                    "app.usage.ingest_dsh_llm.ingest_dsh_sessions"
                ), mock.patch(
                    "app.usage.ingest_dsh_side.ingest_dsh_side_channels"
                ), mock.patch(
                    "app.usage.report.flush_report"
                ):
                    s = store.summarize(days=1, on="2026-09-17", user_id="u_hebo")
                self.assertEqual(s["today"]["llm_calls"], 2)
                self.assertEqual(s["today"]["llm_tokens"], 19)
        finally:
            store.set_data_dir(prev)


if __name__ == "__main__":
    unittest.main()

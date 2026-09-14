"""用量账本：解析与 JSONL 汇总（不调真实 LLM / Cursor）。"""

from __future__ import annotations

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
        self.assertEqual(p["output"], 520)
        self.assertEqual(p["tokens"], 14647)

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

        from app.main import app
        from app.usage import store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
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
                client = TestClient(app)
                r = client.get("/api/usage/summary?days=7")
                self.assertEqual(r.status_code, 200)
                d = r.json()
                self.assertTrue(d.get("ok"))
                self.assertEqual(d["llm"]["tokens"], 10)
                r2 = client.get("/api/usage/daily?days=7")
                self.assertEqual(r2.status_code, 200)
                self.assertIn("daily", r2.json())
                r3 = client.get("/api/usage/events?limit=5")
                self.assertEqual(r3.status_code, 200)
                self.assertGreaterEqual(r3.json().get("count") or 0, 1)
                r4 = client.get("/api/usage/events?source=llm&page=1&page_size=10")
                self.assertEqual(r4.status_code, 200)
                body = r4.json()
                self.assertEqual(body.get("page"), 1)
                self.assertEqual(body.get("page_size"), 10)
                self.assertIn("total", body)
                r5 = client.get("/api/usage/summary?days=7&on=2099-01-01")
                self.assertEqual(r5.status_code, 200)
                self.assertEqual(r5.json().get("on"), r5.json().get("to"))
        finally:
            store.set_data_dir(prev)


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
                    self.assertEqual(s["llm"]["output"], 520)
                    self.assertEqual(s["llm"]["tokens"], 14647)
                    n2 = ingest_dsh_llm.ingest_dsh_sessions(force=True)
                    self.assertEqual(n2, 0)
                    ev = store.list_events(source="llm", page=1, page_size=10)
                    self.assertEqual(ev["events"][0]["quality"], "session")
                    self.assertEqual(ev["events"][0]["label"], "DSH 聊天")
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


if __name__ == "__main__":
    unittest.main()

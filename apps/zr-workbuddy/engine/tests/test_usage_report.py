"""企业用量上报与回环汇总（不调外网）。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class UsageReportTests(unittest.TestCase):
    def test_no_user_id_not_pending(self):
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
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                        "quality": "provider",
                    },
                )
                self.assertEqual(store.pending_report_events(), [])
        finally:
            store.set_data_dir(prev)

    def test_pending_and_mark_reported(self):
        from app.auth import active as auth_active
        from app.auth import paths as auth_paths
        from app.usage import store

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                auth_paths.set_data_dir(os.path.join(td, "auth"))
                auth_active.set_active(
                    {
                        "id": "u_hebo",
                        "username": "hebo",
                        "display_name": "Hebo",
                        "role": "user",
                    },
                    exp=2_000_000_000,
                )
                evt = store.append_event(
                    source="llm",
                    lane="chat",
                    provider="deepseek",
                    model="deepseek-chat",
                    tokens={
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                        "quality": "provider",
                    },
                )
                self.assertIsNotNone(evt)
                self.assertEqual(evt.get("user_id"), "u_hebo")
                self.assertTrue(str(evt.get("machine_id") or "").startswith("mch_"))
                pending = store.pending_report_events()
                self.assertEqual(len(pending), 1)
                n = store.mark_reported([evt["id"]], when="2026-09-14T12:00:00+08:00")
                self.assertEqual(n, 1)
                self.assertEqual(store.pending_report_events(), [])
        finally:
            store.set_data_dir(prev)
            auth_paths.set_data_dir(None)
            try:
                auth_active.clear_active()
            except Exception:
                pass

    def test_flush_skips_when_disabled(self):
        from app.usage.report import flush_report

        with mock.patch("app.usage.report._usage_cfg", return_value={"report_enabled": False}):
            out = flush_report(force=True)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("detail"), "report_disabled")

    def test_flush_posts_and_marks(self):
        from app.auth import active as auth_active
        from app.auth import paths as auth_paths
        from app.usage import store
        from app.usage.report import flush_report

        class _Resp:
            status_code = 200
            content = b'{"ok":true,"accepted":[],"duplicate":[]}'

            def __init__(self, accepted):
                self._accepted = accepted
                self.content = (
                    ('{"ok":true,"accepted":' + str(accepted).replace("'", '"') + ',"duplicate":[]}').encode()
                )

            def json(self):
                import json

                return json.loads(self.content.decode())

        prev = None
        try:
            with tempfile.TemporaryDirectory() as td:
                store.set_data_dir(td)
                auth_paths.set_data_dir(os.path.join(td, "auth"))
                auth_active.set_active(
                    {
                        "id": "u_hebo",
                        "username": "hebo",
                        "display_name": "Hebo",
                        "role": "user",
                    },
                    exp=2_000_000_000,
                )
                evt = store.append_event(
                    source="llm",
                    lane="chat",
                    provider="deepseek",
                    model="m",
                    tokens={
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "quality": "provider",
                    },
                )
                eid = evt["id"]

                class _Client:
                    def __init__(self, *a, **k):
                        pass

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False

                    def post(self, url, json=None, headers=None):
                        self.last = {"url": url, "json": json, "headers": headers}
                        return _Resp([eid])

                cfg = {
                    "report_enabled": True,
                    "report_url": "http://127.0.0.1:8000/api/usage-hub/v1",
                    "report_token": "tok_test",
                }
                with mock.patch("app.usage.report._usage_cfg", return_value=cfg):
                    with mock.patch("app.usage.report.httpx.Client", _Client):
                        out = flush_report(force=True)
                self.assertEqual(out.get("accepted"), 1)
                self.assertEqual(store.pending_report_events(), [])
                # 禁止包内带 key
                self.assertNotIn("api_key", str(out))
        finally:
            store.set_data_dir(prev)
            auth_paths.set_data_dir(None)
            try:
                auth_active.clear_active()
            except Exception:
                pass

    def test_flush_rejects_non_loopback_url(self):
        from app.usage.report import flush_report

        cfg = {
            "report_enabled": True,
            "report_url": "http://example.com/api",
            "report_token": "x",
        }
        with mock.patch("app.usage.report._usage_cfg", return_value=cfg):
            with mock.patch("app.usage.report.pending_report_events", return_value=[{"id": "usg_1", "user_id": "u"}]):
                out = flush_report(force=True)
        self.assertFalse(out.get("ok"))
        self.assertIn("回环", out.get("detail") or "")


class UsageHubTests(unittest.TestCase):
    def test_ingest_idempotent_and_company_split(self):
        from app import usage_hub
        from app.auth import paths as auth_paths
        from app.auth.users import ensure_seed_users
        from app.usage import store

        prev = None
        prev_store = None
        prev_auth = None
        try:
            with tempfile.TemporaryDirectory() as td:
                hub_dir = os.path.join(td, "hub")
                local_dir = os.path.join(td, "local")
                auth_dir = os.path.join(td, "auth")
                os.makedirs(hub_dir)
                os.makedirs(local_dir)
                usage_hub.set_data_dir(hub_dir)
                store.set_data_dir(local_dir)
                auth_paths.set_data_dir(auth_dir)
                ensure_seed_users()
                body = {
                    "machine_id": "mch_t",
                    "user_id": "u_hebo",
                    "events": [
                        {
                            "id": "usg_20260914000000_aaa",
                            "ts": "2026-09-14T10:00:00+08:00",
                            "source": "llm",
                            "total_tokens": 100,
                            "quality": "provider",
                            "user_id": "u_hebo",
                        },
                        {
                            "id": "usg_20260914000001_bbb",
                            "ts": "2026-09-14T11:00:00+08:00",
                            "source": "cursor",
                            "total_tokens": 50,
                            "quality": "sdk",
                            "user_id": "u_hebo",
                        },
                        {
                            "id": "usg_20260914000002_ccc",
                            "ts": "2026-09-14T12:00:00+08:00",
                            "source": "llm",
                            "total_tokens": 30,
                            "quality": "provider",
                            "user_id": "u_admin",
                        },
                    ],
                }
                r1 = usage_hub.ingest_batch(body)
                self.assertEqual(len(r1["accepted"]), 3)
                self.assertEqual(r1.get("rejected") or [], [])
                # 未知账号拒绝
                bad = usage_hub.ingest_batch(
                    {
                        "machine_id": "mch_t",
                        "events": [
                            {
                                "id": "usg_20260914000003_bad",
                                "ts": "2026-09-14T13:00:00+08:00",
                                "source": "llm",
                                "total_tokens": 9,
                                "user_id": "u_ghost",
                            }
                        ],
                    }
                )
                self.assertEqual(bad.get("accepted") or [], [])
                self.assertEqual((bad.get("rejected") or [])[0]["reason"], "unknown_user_id")
                # 超额拒绝
                huge = usage_hub.ingest_batch(
                    {
                        "events": [
                            {
                                "id": "usg_20260914000004_huge",
                                "ts": "2026-09-14T14:00:00+08:00",
                                "source": "llm",
                                "total_tokens": 9_999_999,
                                "user_id": "u_hebo",
                            }
                        ],
                    }
                )
                self.assertEqual((huge.get("rejected") or [])[0]["reason"], "tokens_too_large")
                r2 = usage_hub.ingest_batch(body)
                self.assertEqual(len(r2["duplicate"]), 3)
                self.assertEqual(r2["accepted"], [])
                co = usage_hub.company_summary(from_date="2026-09-01", to_date="2026-09-14")
                self.assertEqual(co["llm"]["tokens"], 130)
                self.assertEqual(co["cursor"]["tokens"], 50)
                self.assertEqual(co["people"], 2)
                pe = usage_hub.people_summary(
                    from_date="2026-09-01", to_date="2026-09-14", grain="day"
                )
                by = {(r["user_id"], r["period"]): r for r in pe["rows"]}
                self.assertEqual(by[("u_hebo", "2026-09-14")]["llm_tokens"], 100)
                self.assertEqual(by[("u_hebo", "2026-09-14")]["cursor_tokens"], 50)
                self.assertEqual(by[("u_admin", "2026-09-14")]["llm_tokens"], 30)
        finally:
            usage_hub.set_data_dir(prev)
            store.set_data_dir(prev_store)
            auth_paths.set_data_dir(prev_auth)

    def test_company_merges_local_ledger_without_double_count(self):
        from app import usage_hub
        from app.auth import paths as auth_paths
        from app.auth.users import ensure_seed_users
        from app.usage import store

        prev_hub = None
        prev_store = None
        prev_auth = None
        try:
            with tempfile.TemporaryDirectory() as td:
                hub_dir = os.path.join(td, "hub")
                local_dir = os.path.join(td, "local")
                auth_dir = os.path.join(td, "auth")
                os.makedirs(hub_dir)
                os.makedirs(local_dir)
                usage_hub.set_data_dir(hub_dir)
                store.set_data_dir(local_dir)
                auth_paths.set_data_dir(auth_dir)
                ensure_seed_users()
                eid = "usg_20260914000000_loc"
                with open(store.events_path(), "w", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "id": eid,
                                "ts": "2026-09-14T10:00:00+08:00",
                                "source": "llm",
                                "total_tokens": 77,
                                "user_id": "u_hebo",
                                "quality": "provider",
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                co = usage_hub.company_summary(from_date="2026-09-01", to_date="2026-09-14")
                self.assertEqual(co["llm"]["tokens"], 77)
                # 同 id 再 ingest 到 hub 不得双计
                usage_hub.ingest_batch(
                    {
                        "machine_id": "m1",
                        "user_id": "u_hebo",
                        "events": [
                            {
                                "id": eid,
                                "ts": "2026-09-14T10:00:00+08:00",
                                "source": "llm",
                                "total_tokens": 77,
                                "user_id": "u_hebo",
                            }
                        ],
                    }
                )
                co2 = usage_hub.company_summary(from_date="2026-09-01", to_date="2026-09-14")
                self.assertEqual(co2["llm"]["tokens"], 77)
                pe = usage_hub.people_summary(
                    from_date="2026-09-01", to_date="2026-09-14", grain="day"
                )
                by_uid = {r["user_id"]: r for r in pe["rows"]}
                self.assertIn("u_hebo", by_uid)
                self.assertEqual(by_uid["u_hebo"]["llm_tokens"], 77)
                self.assertIn("display_name", by_uid["u_hebo"])
        finally:
            usage_hub.set_data_dir(prev_hub)
            store.set_data_dir(prev_store)
            auth_paths.set_data_dir(prev_auth)


class EnterpriseApiAdminGateTests(unittest.TestCase):
    def test_enterprise_requires_admin(self):
        from fastapi.testclient import TestClient

        from app.auth import paths as auth_paths
        from app.main import app

        with tempfile.TemporaryDirectory() as td:
            auth_paths.set_data_dir(td)
            from app.auth.users import ensure_seed_users

            ensure_seed_users()
            with TestClient(app) as client:
                hebo = client.post(
                    "/api/auth/login",
                    json={"username": "hebo", "password": "hebo123"},
                ).json()
                self.assertTrue(hebo.get("ok"))
                denied = client.get(
                    "/api/usage/enterprise/people?from=2026-09-01&to=2026-09-14&grain=day",
                    headers={"Authorization": "Bearer " + hebo["token"]},
                )
                self.assertEqual(denied.status_code, 403)

                admin = client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "admin123"},
                ).json()
                self.assertTrue(admin.get("ok"))
                ok = client.get(
                    "/api/usage/enterprise/people?from=2026-09-01&to=2026-09-14&grain=day",
                    headers={"Authorization": "Bearer " + admin["token"]},
                )
                self.assertEqual(ok.status_code, 200)
                body = ok.json()
                self.assertTrue(body.get("ok"))
                self.assertIn("rows", body)

                summary = client.get(
                    "/api/usage/enterprise/summary?days=7&on=2026-09-14",
                    headers={"Authorization": "Bearer " + admin["token"]},
                )
                self.assertEqual(summary.status_code, 200)
                sbody = summary.json()
                self.assertTrue(sbody.get("ok"))
                self.assertEqual(sbody.get("scope"), "enterprise")
                self.assertIn("today", sbody)
                self.assertIn("hourly", sbody)

                denied_sum = client.get(
                    "/api/usage/enterprise/summary?days=7",
                    headers={"Authorization": "Bearer " + hebo["token"]},
                )
                self.assertEqual(denied_sum.status_code, 403)

                # hub 读接口不得匿名 / 普通用户可读
                anon = client.get("/api/usage-hub/v1/people?from=2026-09-01&to=2026-09-14")
                self.assertEqual(anon.status_code, 401)
                hub_denied = client.get(
                    "/api/usage-hub/v1/company?from=2026-09-01&to=2026-09-14",
                    headers={"Authorization": "Bearer " + hebo["token"]},
                )
                self.assertEqual(hub_denied.status_code, 403)
                hub_ok = client.get(
                    "/api/usage-hub/v1/people?from=2026-09-01&to=2026-09-14&grain=day",
                    headers={"Authorization": "Bearer " + admin["token"]},
                )
                self.assertEqual(hub_ok.status_code, 200)
            auth_paths.set_data_dir(None)

    def test_ingest_rejects_empty_report_token(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            r = client.post("/api/usage-hub/v1/ingest", json={"events": []})
            self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()

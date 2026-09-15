"""本机账号：种子用户、JWT、active 会话、用量 user_id。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class AuthModuleTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        from app.auth import paths as auth_paths
        from app.usage import store as usage_store

        self._auth_paths = auth_paths
        self._usage_store = usage_store
        auth_paths.set_data_dir(self._tmpdir.name)
        usage_store.set_data_dir(os.path.join(self._tmpdir.name, "usage"))

    def tearDown(self):
        self._auth_paths.set_data_dir(None)
        self._usage_store.set_data_dir(None)
        self._tmpdir.cleanup()

    def test_seed_and_login_password(self):
        from app.auth.users import ensure_seed_users, public_user, verify_password

        ensure_seed_users()
        ensure_seed_users()  # idempotent
        u = verify_password("hebo", "hebo123")
        self.assertIsNotNone(u)
        self.assertEqual(u["id"], "u_hebo")
        self.assertEqual(public_user(u)["role"], "user")
        self.assertIsNone(verify_password("hebo", "wrong"))
        admin = verify_password("admin", "admin123")
        self.assertEqual(admin["role"], "admin")

    def test_jwt_roundtrip(self):
        from app.auth.tokens import issue_token, verify_token

        tok, exp = issue_token(user_id="u_hebo", username="hebo", role="user", ttl_sec=3600)
        self.assertGreater(exp, 0)
        claims = verify_token(tok)
        self.assertEqual(claims["id"], "u_hebo")
        self.assertEqual(claims["username"], "hebo")
        self.assertIsNone(verify_token(tok[:-2] + "xx"))

    def test_login_me_logout_api(self):
        from fastapi.testclient import TestClient

        from app.auth.users import ensure_seed_users
        from app.main import app

        ensure_seed_users()
        with TestClient(app) as client:
            bad = client.post("/api/auth/login", json={"username": "hebo", "password": "x"})
            self.assertEqual(bad.status_code, 401)
            ok = client.post("/api/auth/login", json={"username": "hebo", "password": "hebo123"})
            self.assertEqual(ok.status_code, 200)
            body = ok.json()
            self.assertTrue(body.get("ok"))
            self.assertTrue(body.get("token"))
            me = client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer " + body["token"]},
            )
            self.assertTrue(me.json().get("authenticated"))
            self.assertEqual(me.json()["user"]["username"], "hebo")
            out = client.post("/api/auth/logout")
            self.assertTrue(out.json().get("ok"))
            # 登出后用量须登录
            usage = client.get("/api/usage/summary?days=1")
            self.assertEqual(usage.status_code, 401)
            docs = client.get("/openapi.json")
            self.assertEqual(docs.status_code, 200)

    def test_backfill_and_filter_by_user(self):
        from app.usage.store import append_event, backfill_orphan_user_id, summarize

        append_event(
            source="llm",
            lane="chat",
            provider="t",
            model="m",
            tokens={
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
                "quality": "provider",
            },
        )
        # 无登录时 user_id 为空
        n = backfill_orphan_user_id(default_user_id="u_hebo")
        self.assertGreaterEqual(n, 1)
        self.assertEqual(backfill_orphan_user_id(default_user_id="u_hebo"), 0)  # idempotent
        hebo = summarize(days=7, user_id="u_hebo")
        admin = summarize(days=7, user_id="u_admin")
        self.assertEqual(hebo["llm"]["tokens"], 2)
        self.assertEqual(admin["llm"]["tokens"], 0)

    def test_active_and_append_user_id(self):
        from app.auth.active import clear_active, get_active_user, set_active
        from app.auth.users import ensure_seed_users, public_user, verify_password
        from app.usage.store import append_event

        ensure_seed_users()
        u = public_user(verify_password("hebo", "hebo123"))
        set_active(u, exp=2_000_000_000)
        self.assertEqual(get_active_user()["id"], "u_hebo")
        evt = append_event(
            source="llm",
            lane="chat",
            provider="test",
            model="m",
            tokens={
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "quality": "provider",
            },
        )
        self.assertIsNotNone(evt)
        self.assertEqual(evt["user_id"], "u_hebo")
        clear_active()
        evt2 = append_event(
            source="llm",
            lane="chat",
            provider="test",
            model="m",
            tokens={
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
                "quality": "provider",
            },
        )
        self.assertEqual(evt2.get("user_id") or "", "")

    def test_usage_requires_bearer_not_active_only(self):
        """active.json 不得单独打开用量 HTTP（防跨账号读）。"""
        from fastapi.testclient import TestClient

        from app.auth.active import set_active
        from app.auth.users import ensure_seed_users, public_user, verify_password
        from app.main import app

        ensure_seed_users()
        u = public_user(verify_password("hebo", "hebo123"))
        set_active(u, exp=2_000_000_000)
        with TestClient(app) as client:
            denied = client.get("/api/usage/summary?days=1")
            self.assertEqual(denied.status_code, 401)
            login = client.post(
                "/api/auth/login",
                json={"username": "hebo", "password": "hebo123"},
            )
            ok = client.get(
                "/api/usage/summary?days=1",
                headers={"Authorization": "Bearer " + login.json()["token"]},
            )
            self.assertEqual(ok.status_code, 200)

    def test_disabled_user_jwt_rejected_and_change_password(self):
        from fastapi.testclient import TestClient

        from app.auth.users import ensure_seed_users, set_user_disabled
        from app.main import app

        ensure_seed_users()
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "hebo", "password": "hebo123"},
            )
            token = login.json()["token"]
            ch = client.post(
                "/api/auth/change-password",
                json={
                    "username": "hebo",
                    "old_password": "hebo123",
                    "new_password": "hebo12345",
                },
            )
            self.assertEqual(ch.status_code, 200)
            self.assertFalse(ch.json()["user"].get("must_change_password"))
            bad = client.post(
                "/api/auth/login",
                json={"username": "hebo", "password": "hebo123"},
            )
            self.assertEqual(bad.status_code, 401)
            self.assertTrue(set_user_disabled("u_hebo", True))
            denied = client.get(
                "/api/usage/summary?days=1",
                headers={"Authorization": "Bearer " + token},
            )
            self.assertEqual(denied.status_code, 401)

if __name__ == "__main__":
    unittest.main()

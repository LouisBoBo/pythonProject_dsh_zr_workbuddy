"""P0 HITL nonce / path_ticket / Origin 守卫单测。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)

from fastapi.testclient import TestClient

from app.hitl import (
    ACTION_DEV,
    ACTION_PATH,
    consume,
    gate_review_path,
    issue,
    issue_surface_ok,
    local_origin_ok,
    mutating_path_guarded,
    reset_store_for_tests,
)
from app.main import app

_UI_HEADERS = {
    "Origin": "http://127.0.0.1:3080",
    "X-WorkBuddy-Hitl": "ui",
}


class HitlTokenTests(unittest.TestCase):
    def setUp(self):
        reset_store_for_tests()

    def test_issue_consume_once(self):
        from app.hitl.tokens import normalize_payload_hash

        with tempfile.TemporaryDirectory() as td:
            ws = str(Path(td).resolve())
            ph = normalize_payload_hash("一次性 nonce 消耗测试需求摘要")
            issued = issue(action=ACTION_DEV, workspace=ws, payload_hash=ph)
            self.assertTrue(issued.get("ok"), issued)
            nonce = issued["nonce"]
            ok = consume(nonce=nonce, action=ACTION_DEV, workspace=ws, payload_hash=ph)
            self.assertTrue(ok.get("ok"), ok)
            again = consume(nonce=nonce, action=ACTION_DEV, workspace=ws, payload_hash=ph)
            self.assertFalse(again.get("ok"))
            self.assertEqual(again.get("code"), "hitl_nonce_invalid")

    def test_issue_requires_payload_hash(self):
        with tempfile.TemporaryDirectory() as td:
            ws = str(Path(td).resolve())
            bare = issue(action=ACTION_DEV, workspace=ws)
            self.assertFalse(bare.get("ok"))
            bad = issue(action=ACTION_DEV, workspace=ws, payload_hash="not-hex")
            self.assertFalse(bad.get("ok"))

    def test_payload_hash_mismatch(self):
        from app.hitl.tokens import normalize_payload_hash

        with tempfile.TemporaryDirectory() as td:
            ws = str(Path(td).resolve())
            req = "报表中心菜单删除设备管理子项"
            issued = issue(
                action=ACTION_DEV,
                workspace=ws,
                payload_hash=normalize_payload_hash(req),
            )
            self.assertTrue(issued.get("ok"), issued)
            bad = consume(
                nonce=issued["nonce"],
                action=ACTION_DEV,
                workspace=ws,
                payload_hash=normalize_payload_hash(req + "-篡改"),
            )
            self.assertFalse(bad.get("ok"))
            self.assertEqual(bad.get("code"), "hitl_payload_mismatch")

    def test_payload_hash_ok(self):
        from app.hitl.tokens import normalize_payload_hash

        with tempfile.TemporaryDirectory() as td:
            ws = str(Path(td).resolve())
            req = "报表中心菜单删除设备管理子项"
            ph = normalize_payload_hash(req)
            issued = issue(action=ACTION_DEV, workspace=ws, payload_hash=ph)
            ok = consume(
                nonce=issued["nonce"],
                action=ACTION_DEV,
                workspace=ws,
                payload_hash=ph,
            )
            self.assertTrue(ok.get("ok"), ok)

    def test_workspace_mismatch(self):
        from app.hitl.tokens import normalize_payload_hash

        with tempfile.TemporaryDirectory() as td:
            ws = str(Path(td).resolve())
            ph = normalize_payload_hash("workspace 绑定测试")
            issued = issue(action=ACTION_DEV, workspace=ws, payload_hash=ph)
            bad = consume(
                nonce=issued["nonce"],
                action=ACTION_DEV,
                workspace=ws + "-other",
                payload_hash=ph,
            )
            self.assertFalse(bad.get("ok"))
            self.assertEqual(bad.get("code"), "hitl_bind_mismatch")

    def test_missing_nonce(self):
        out = consume(nonce="", action=ACTION_DEV, workspace="/tmp")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("code"), "hitl_nonce_missing")

    def test_path_ticket_gate(self):
        with tempfile.TemporaryDirectory() as td:
            p = str(Path(td).resolve())
            issued = issue(action=ACTION_PATH, path=p)
            self.assertTrue(issued.get("ok"))
            gate = gate_review_path(local_path=p, path_ticket=issued["nonce"])
            self.assertTrue(gate.get("ok"), gate)
            bare = gate_review_path(local_path=p, path_ticket="")
            self.assertFalse(bare.get("ok"))
            self.assertEqual(bare.get("code"), "path_ticket_missing")
            allow = gate_review_path(
                local_path=p,
                path_ticket="",
                allow_agent_absolute_path=True,
            )
            self.assertTrue(allow.get("ok"))


class HitlOriginTests(unittest.TestCase):
    def test_mutating_paths(self):
        self.assertTrue(mutating_path_guarded("/api/hitl/issue", "POST"))
        self.assertTrue(mutating_path_guarded("/api/code-dev/confirm", "POST"))
        self.assertTrue(mutating_path_guarded("/api/code-review/run/stream", "POST"))
        self.assertTrue(mutating_path_guarded("/api/config", "PUT"))
        self.assertTrue(mutating_path_guarded("/api/pick-folder", "POST"))
        self.assertFalse(mutating_path_guarded("/api/runtime", "GET"))
        self.assertFalse(mutating_path_guarded("/api/code-dev/confirm", "GET"))

    def test_local_origin(self):
        self.assertIsNone(local_origin_ok(None, None))
        self.assertIsNone(local_origin_ok("http://127.0.0.1:3080", None))
        self.assertIsNone(local_origin_ok("http://localhost:8000", None))
        self.assertIsNotNone(local_origin_ok("http://evil.example", None))

    def test_issue_surface(self):
        self.assertIsNotNone(issue_surface_ok(origin=None, referer=None, ui_header=None))
        self.assertIsNotNone(
            issue_surface_ok(origin="http://127.0.0.1:3080", referer=None, ui_header=None)
        )
        self.assertIsNone(
            issue_surface_ok(
                origin="http://127.0.0.1:3080",
                referer=None,
                ui_header="ui",
            )
        )
        self.assertIsNotNone(
            issue_surface_ok(
                origin="http://evil.example",
                referer=None,
                ui_header="ui",
            )
        )


class HitlHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        reset_store_for_tests()

    def test_issue_requires_ui_surface(self):
        with tempfile.TemporaryDirectory() as td:
            ws = str(Path(td).resolve())
            bare = self.client.post(
                "/api/hitl/issue",
                json={"action": "code-dev.confirm", "workspace": ws},
            )
            self.assertEqual(bare.status_code, 403)
            self.assertEqual(bare.json().get("code"), "hitl_issue_forbidden")

            r = self.client.post(
                "/api/hitl/issue",
                json={
                    "action": "code-dev.confirm",
                    "workspace": ws,
                    "requirement": "报表中心菜单删除设备管理子项并验收",
                },
                headers=_UI_HEADERS,
            )
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json().get("ok"))
            self.assertTrue(r.json().get("nonce", "").startswith("htl_"))

            missing_req = self.client.post(
                "/api/hitl/issue",
                json={"action": "code-dev.confirm", "workspace": ws},
                headers=_UI_HEADERS,
            )
            self.assertEqual(missing_req.status_code, 400)
            self.assertEqual(missing_req.json().get("code"), "hitl_requirement_missing")

            no_nonce = self.client.post(
                "/api/code-dev/confirm",
                json={"workspace": ws, "requirement": "x" * 40},
            )
            self.assertEqual(no_nonce.status_code, 400)

    def test_issue_rejects_path_action(self):
        r = self.client.post(
            "/api/hitl/issue",
            json={"action": "code-review.path", "path": "/tmp"},
            headers=_UI_HEADERS,
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json().get("code"), "hitl_action_not_http")

    def test_reject_evil_origin(self):
        r = self.client.post(
            "/api/hitl/issue",
            json={"action": "code-dev.confirm", "workspace": "/tmp"},
            headers={"Origin": "http://evil.example", "X-WorkBuddy-Hitl": "ui"},
        )
        self.assertEqual(r.status_code, 403)
        # 可能先被中间件 origin_rejected，或签发面 hitl_issue_forbidden
        self.assertIn(r.json().get("code"), {"origin_rejected", "hitl_issue_forbidden"})

    def test_code_dev_start_disabled(self):
        import asyncio

        from app.cli_ops import run_async

        out = asyncio.run(run_async("code-dev-start", ["/tmp", "hello"]))
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("code"), "hitl_start_disabled")


if __name__ == "__main__":
    unittest.main()

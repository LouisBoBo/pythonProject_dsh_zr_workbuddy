"""P1 企业安全：审计 / SSE 脱敏 / stream_token / write_scope 开关（默认不破现网）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class SecurityAuditTests(unittest.TestCase):
    def test_append_never_raises(self):
        from app.security_audit import append_audit, audit_path

        with tempfile.TemporaryDirectory() as td:
            with mock.patch("app.security_audit._data_root", return_value=Path(td)):
                append_audit("unit.test", actor="test", detail="ok")
                append_audit("unit.test", actor="test", huge="x" * 10000)
                path = audit_path()
                self.assertTrue(path.is_file())
                lines = path.read_text(encoding="utf-8").strip().splitlines()
                self.assertGreaterEqual(len(lines), 2)
                row = json.loads(lines[0])
                self.assertEqual(row.get("event"), "unit.test")


class PublicRedactTests(unittest.TestCase):
    def test_redacts_sk_in_job_and_sse(self):
        from app.code_dev.public_redact import redact_job_public, redact_sse_payload

        secret = "sk-" + ("a" * 24)
        job = {
            "id": "ldj-x",
            "live_text": f"key={secret}",
            "requirement": f"use {secret}",
            "messages": [{"role": "user", "content": f"api_key={secret}"}],
            "brief": {"summary": f"tok={secret}"},
            "stream_token": "secret-stream-tok",
            "events": [{"type": "status", "text": f"api_key={secret}"}],
        }
        pub = redact_job_public(job)
        self.assertNotIn(secret, pub["live_text"])
        self.assertIn("sk-••••", pub["live_text"])
        self.assertNotIn(secret, pub["events"][0]["text"])
        self.assertNotIn(secret, pub["requirement"])
        self.assertNotIn(secret, pub["messages"][0]["content"])
        self.assertNotIn(secret, pub["brief"]["summary"])
        self.assertNotIn("stream_token", pub)
        # 落盘原件未改
        self.assertIn(secret, job["live_text"])
        self.assertEqual(job.get("stream_token"), "secret-stream-tok")

        ev = redact_sse_payload({"type": "token", "text": secret, "job": job})
        self.assertNotIn(secret, ev["text"])
        self.assertNotIn(secret, ev["job"]["live_text"])
        self.assertNotIn("stream_token", ev["job"])


class GetJobTokenPolicyTests(unittest.TestCase):
    def test_get_job_omits_token_when_required(self):
        from app.code_dev import ops as code_dev_ops

        fake = {
            "id": "ldj-t",
            "status": "running",
            "stream_token": "tok-should-hide",
            "live_text": "ok",
            "progress": "1",
            "error": "",
        }
        with mock.patch.object(code_dev_ops.job_store, "get_job", return_value=fake), mock.patch(
            "app.code_dev.config.get_config"
        ) as gc:
            gc.return_value = mock.Mock(require_job_stream_token=True)
            out = code_dev_ops.get_job("ldj-t")
            self.assertTrue(out.get("ok"))
            self.assertNotIn("stream_token", out)
            self.assertNotIn("stream_token", out.get("job") or {})

            gc.return_value = mock.Mock(require_job_stream_token=False)
            out2 = code_dev_ops.get_job("ldj-t")
            self.assertEqual(out2.get("stream_token"), "tok-should-hide")
            self.assertNotIn("stream_token", out2.get("job") or {})

    def test_get_job_reply_uses_redacted_error(self):
        from app.code_dev import ops as code_dev_ops

        secret = "sk-" + ("b" * 24)
        fake = {
            "id": "ldj-e",
            "status": "failed",
            "stream_token": "t",
            "error": f"boom {secret}",
            "progress": "",
        }
        with mock.patch.object(code_dev_ops.job_store, "get_job", return_value=fake), mock.patch(
            "app.code_dev.config.get_config"
        ) as gc:
            gc.return_value = mock.Mock(require_job_stream_token=False)
            out = code_dev_ops.get_job("ldj-e")
            self.assertNotIn(secret, str(out.get("reply") or ""))
            self.assertNotIn(secret, str(out.get("detail") or ""))


class StreamTokenGateTests(unittest.TestCase):
    def test_default_allows_missing_token(self):
        from app.code_dev.ops import check_job_stream_token

        job = {"stream_token": "tok-abc"}
        with mock.patch("app.code_dev.config.get_config") as gc:
            gc.return_value = mock.Mock(require_job_stream_token=False)
            self.assertTrue(check_job_stream_token(job, "").get("ok"))
            self.assertTrue(check_job_stream_token(job, "tok-abc").get("ok"))
            bad = check_job_stream_token(job, "wrong")
            self.assertFalse(bad.get("ok"))
            self.assertEqual(bad.get("code"), "job_stream_token_invalid")

    def test_required_needs_token(self):
        from app.code_dev.ops import check_job_stream_token

        job = {"stream_token": "tok-abc"}
        with mock.patch("app.code_dev.config.get_config") as gc:
            gc.return_value = mock.Mock(require_job_stream_token=True)
            miss = check_job_stream_token(job, "")
            self.assertFalse(miss.get("ok"))
            self.assertEqual(miss.get("code"), "job_stream_token_missing")
            self.assertTrue(check_job_stream_token(job, "tok-abc").get("ok"))
            # 旧任务无 token：强制模式仍放行
            self.assertTrue(check_job_stream_token({}, "").get("ok"))


class WriteScopeGateTests(unittest.TestCase):
    def test_default_allows_empty_scope_path(self):
        from app.code_dev.config import CodeDevConfig

        cfg = CodeDevConfig(require_explicit_write_scope=False)
        self.assertFalse(cfg.require_explicit_write_scope)

    def test_confirm_rejects_empty_when_required(self):
        from app.code_dev import chat_bridge

        with mock.patch("app.code_dev.chat_bridge.get_config") as gc, mock.patch(
            "app.code_dev.chat_bridge.validate_requirement_for_start"
        ) as val, mock.patch("app.code_dev.chat_bridge.infer_target_from_text") as infer, mock.patch(
            "app.code_dev.chat_bridge.write_scope_from_hints", return_value=[]
        ), mock.patch("app.code_dev.chat_bridge.code_dev_start") as start:
            gc.return_value = mock.Mock(require_explicit_write_scope=True)
            val.return_value = {
                "ok": True,
                "errors": [],
                "warnings": [],
                "target_hints": {"module": "x", "confidence": "low", "expected_paths": []},
            }
            infer.return_value = {"module": "x", "confidence": "low", "expected_paths": []}
            out = chat_bridge.confirm_and_start(
                workspace="/tmp/ws",
                requirement="做一个无关紧要的小改动，不要指定目录，用于单测空 write_scope 门禁",
            )
            self.assertFalse(out.get("ok"))
            self.assertEqual(out.get("code"), "write_scope_required")
            start.assert_not_called()


class CreateJobTokenTests(unittest.TestCase):
    def test_create_job_mints_stream_token(self):
        from app.code_dev import jobs as job_store

        with tempfile.TemporaryDirectory() as td:
            job = job_store.create_job(
                Path(td),
                user_id=None,
                username=None,
                thread_id="",
                workspace="/tmp/ws",
                message="hello",
            )
            self.assertTrue(str(job.get("stream_token") or "").strip())


if __name__ == "__main__":
    unittest.main()

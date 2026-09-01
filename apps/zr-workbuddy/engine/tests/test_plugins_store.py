"""plugins.json 原子写与 flock。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock


class PluginsStoreTests(unittest.TestCase):
    def test_enable_disable_roundtrip(self):
        from app import plugins_store

        with tempfile.TemporaryDirectory() as td:
            feat = os.path.join(td, "features")
            eng = os.path.join(td, "engine")
            data = os.path.join(eng, "data")
            os.makedirs(os.path.join(feat, "demo"))
            with open(os.path.join(feat, "demo", "index.js"), "w", encoding="utf-8") as f:
                f.write("//")
            os.makedirs(data)
            state = os.path.join(data, "plugins.json")
            with mock.patch.object(plugins_store, "_FEATURES_DIR", feat), mock.patch.object(
                plugins_store, "_STATE_PATH", state
            ), mock.patch.object(plugins_store, "_LOCK_PATH", state + ".lock"):
                r = plugins_store.enable("demo")
                self.assertTrue(r.get("ok"))
                self.assertIn("demo", r.get("enabled") or [])
                with open(state, encoding="utf-8") as f:
                    raw = json.loads(f.read())
                self.assertEqual(raw["enabled"], ["demo"])
                r2 = plugins_store.disable("demo")
                self.assertTrue(r2.get("ok"))
                self.assertNotIn("demo", r2.get("enabled") or [])

    def test_new_feature_dir_auto_listed(self):
        """新增 features/<id>/ 后无需改白名单，snapshot.available 自动包含。"""
        from app import plugins_store

        with tempfile.TemporaryDirectory() as td:
            feat = os.path.join(td, "features")
            data = os.path.join(td, "data")
            os.makedirs(feat)
            os.makedirs(data)
            old = os.path.join(feat, "mes-ask")
            os.makedirs(old)
            with open(os.path.join(old, "index.js"), "w", encoding="utf-8") as f:
                f.write("//\n")
            with open(os.path.join(old, "manifest.json"), "w", encoding="utf-8") as f:
                f.write('{"id":"mes-ask","name":"查数","purpose":"x"}')
            state = os.path.join(data, "plugins.json")
            with open(state, "w", encoding="utf-8") as f:
                f.write('{"enabled":["mes-ask"]}\n')
            with mock.patch.object(plugins_store, "_FEATURES_DIR", feat), mock.patch.object(
                plugins_store, "_STATE_PATH", state
            ), mock.patch.object(plugins_store, "_LOCK_PATH", state + ".lock"):
                snap1 = plugins_store.snapshot()
                self.assertEqual({m["id"] for m in snap1["available"]}, {"mes-ask"})
                neu = os.path.join(feat, "mes-report")
                os.makedirs(neu)
                with open(os.path.join(neu, "index.js"), "w", encoding="utf-8") as f:
                    f.write("//\n")
                with open(os.path.join(neu, "manifest.json"), "w", encoding="utf-8") as f:
                    f.write('{"id":"mes-report","name":"报表","purpose":"出报表"}')
                snap2 = plugins_store.snapshot()
                self.assertEqual({m["id"] for m in snap2["available"]}, {"mes-ask", "mes-report"})
                report = next(m for m in snap2["available"] if m["id"] == "mes-report")
                self.assertEqual(report.get("kind"), "feature")
                self.assertEqual(report.get("name"), "报表")
                self.assertNotIn("mes-report", snap2["enabled"])
                plugins_store.enable("mes-report")
                self.assertIn("mes-report", plugins_store.snapshot()["enabled"])


if __name__ == "__main__":
    unittest.main()

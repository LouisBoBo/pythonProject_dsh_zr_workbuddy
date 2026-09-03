"""code_deploy：按插件单元映射单测（不 SSH）。"""
from __future__ import annotations

import os
import sys
import unittest

_ENG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)


class CodeDeployUnitTests(unittest.TestCase):
    def test_map_only_changed_features(self):
        from app.code_deploy.units import map_paths_to_units

        paths = [
            "apps/zr-workbuddy/features/code-commit/index.js",
            "apps/zr-workbuddy/features/code-dev/manifest.json",
            "docs/功能实现/P0-2.md",
        ]
        units = map_paths_to_units(paths)
        ids = [u.id for u in units]
        self.assertEqual(ids, ["feature:code-commit", "feature:code-dev"])
        self.assertTrue(all(u.action == "sync_feature" for u in units))

    def test_engine_and_bridge_ranked_last(self):
        from app.code_deploy.units import map_paths_to_units

        paths = [
            "apps/zr-workbuddy/plugins/mes-bridge/lib/client.js",
            "apps/zr-workbuddy/features/mes-ask/index.js",
            "apps/zr-workbuddy/engine/app/main.py",
        ]
        ids = [u.id for u in map_paths_to_units(paths)]
        self.assertEqual(ids, ["feature:mes-ask", "engine", "bridge"])

    def test_filter_units_by_ids(self):
        from app.code_deploy.units import filter_units_by_ids, map_paths_to_units

        units = map_paths_to_units(
            [
                "apps/zr-workbuddy/features/code-commit/index.js",
                "apps/zr-workbuddy/features/code-dev/index.js",
                "apps/zr-workbuddy/engine/app/cli_ops.py",
            ]
        )
        picked = filter_units_by_ids(units, ["feature:code-commit", "feature:code-dev"])
        self.assertEqual([u.id for u in picked], ["feature:code-commit", "feature:code-dev"])

    def test_intent(self):
        from app.code_deploy.intent import is_code_deploy_question

        self.assertTrue(is_code_deploy_question("部署到预发"))
        self.assertTrue(is_code_deploy_question("发布到 staging"))
        self.assertTrue(is_code_deploy_question("部署上线"))
        self.assertTrue(is_code_deploy_question("增量部署"))
        self.assertTrue(is_code_deploy_question("帮我部署上线"))
        self.assertFalse(is_code_deploy_question("提交代码"))
        self.assertFalse(is_code_deploy_question("部署工单进度"))

    def test_list_catalog_units(self):
        from pathlib import Path

        from app.code_deploy.units import list_catalog_units

        root = Path(_ENG).resolve().parents[2]  # repo root
        units = list_catalog_units(root)
        ids = [u.id for u in units]
        self.assertIn("feature:code-deploy", ids)
        self.assertIn("engine", ids)
        self.assertIn("bridge", ids)
        self.assertIn("scripts", ids)

    def test_normalize_mode_first_full(self):
        from app.code_deploy.ops import _normalize_mode

        self.assertEqual(_normalize_mode("auto", first_deploy=True), "full")
        self.assertEqual(_normalize_mode("auto", first_deploy=False), "incremental")
        self.assertEqual(_normalize_mode("full", first_deploy=False), "full")

    def test_policy_first_forces_full(self):
        from app.code_deploy.policy import decide_deploy_mode
        from app.code_deploy.units import build_unit

        d = decide_deploy_mode(
            last_sha="",
            base_resolved=False,
            paths=[],
            units=[],
        )
        self.assertTrue(d.force_full)
        self.assertEqual(d.mode, "full")
        self.assertFalse(d.allow_mode_override)

    def test_policy_feature_only_incremental(self):
        from app.code_deploy.policy import decide_deploy_mode
        from app.code_deploy.units import build_unit

        units = [build_unit("feature:code-dev"), build_unit("feature:code-commit")]
        d = decide_deploy_mode(
            last_sha="abc123",
            base_resolved=True,
            paths=[
                "apps/zr-workbuddy/features/code-dev/index.js",
                "apps/zr-workbuddy/features/code-commit/index.js",
            ],
            units=units,
        )
        self.assertEqual(d.mode, "incremental")
        self.assertFalse(d.force_full)

    def test_policy_scripts_force_full(self):
        from app.code_deploy.policy import decide_deploy_mode
        from app.code_deploy.units import build_unit

        units = [build_unit("scripts"), build_unit("engine")]
        d = decide_deploy_mode(
            last_sha="abc123",
            base_resolved=True,
            paths=["scripts/engine.sh", "apps/zr-workbuddy/engine/app/main.py"],
            units=units,
        )
        self.assertTrue(d.force_full)
        self.assertEqual(d.mode, "full")

    def test_policy_override_blocked_when_forced(self):
        from app.code_deploy.policy import apply_user_mode_override, decide_deploy_mode

        d = decide_deploy_mode(last_sha="", base_resolved=False, paths=[], units=[])
        out = apply_user_mode_override(d, "incremental")
        self.assertEqual(out.mode, "full")
        self.assertTrue(out.force_full)

    def test_safe_local_path_blocks_escape(self):
        from pathlib import Path

        from app.code_deploy.ssh_sync import _safe_local_path

        root = Path(_ENG).resolve().parents[2]
        self.assertIsNotNone(_safe_local_path(root, "apps/zr-workbuddy/engine/app"))
        self.assertIsNone(_safe_local_path(root, "/etc/passwd"))
        self.assertIsNone(_safe_local_path(root, "../README.md"))

    def test_health_blocks_loopback(self):
        from app.code_deploy.ssh_sync import probe_health

        self.assertFalse(probe_health("http://127.0.0.1:9/").get("ok"))
        self.assertFalse(probe_health("http://localhost/").get("ok"))


if __name__ == "__main__":
    unittest.main()

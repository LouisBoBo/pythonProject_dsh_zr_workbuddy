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

        d = decide_deploy_mode(
            last_sha="",
            base_resolved=False,
            paths=[],
            units=[],
        )
        self.assertTrue(d.force_full)
        self.assertEqual(d.mode, "full")
        self.assertFalse(d.allow_upgrade_to_full)
        self.assertFalse(d.recommend_full)

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
        self.assertTrue(d.allow_upgrade_to_full)

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

    def test_policy_binary_no_soft_recommend(self):
        """变更面较大也不再出现「建议全量」中间态，仍为增量（可升级）。"""
        from app.code_deploy.policy import decide_deploy_mode
        from app.code_deploy.units import build_unit

        units = [
            build_unit("feature:a"),
            build_unit("feature:b"),
            build_unit("feature:c"),
            build_unit("engine"),
        ]
        # 4 个单元 < 强制阈值 6 → 增量
        d = decide_deploy_mode(
            last_sha="abc123",
            base_resolved=True,
            paths=["apps/zr-workbuddy/features/a/index.js"],
            units=units,
        )
        self.assertEqual(d.mode, "incremental")
        self.assertFalse(d.force_full)
        self.assertFalse(d.recommend_full)

    def test_policy_override_blocked_when_forced(self):
        from app.code_deploy.policy import apply_user_mode_override, decide_deploy_mode

        d = decide_deploy_mode(last_sha="", base_resolved=False, paths=[], units=[])
        out = apply_user_mode_override(d, "incremental")
        self.assertEqual(out.mode, "full")
        self.assertTrue(out.force_full)

    def test_policy_requirements_not_force_full(self):
        """依赖变更走 engine 单元，不应锁死全仓全量。"""
        from app.code_deploy.policy import decide_deploy_mode
        from app.code_deploy.units import build_unit

        units = [build_unit("engine")]
        d = decide_deploy_mode(
            last_sha="abc123",
            base_resolved=True,
            paths=["apps/zr-workbuddy/engine/requirements.txt"],
            units=units,
            dirty_paths=["apps/zr-workbuddy/engine/requirements.txt"],
        )
        self.assertFalse(d.force_full)
        self.assertEqual(d.mode, "incremental")

    def test_engine_config_example_maps_incremental(self):
        """config.example.yaml 归 engine 单元，不再因未映射强制全量。"""
        from app.code_deploy.policy import decide_deploy_mode
        from app.code_deploy.units import build_unit, map_paths_to_units, path_to_unit_id

        rel = "apps/zr-workbuddy/engine/config/config.example.yaml"
        self.assertEqual(path_to_unit_id(rel), "engine")
        self.assertIsNone(
            path_to_unit_id("apps/zr-workbuddy/engine/config/config.yaml")
        )
        units = map_paths_to_units([rel])
        self.assertEqual([u.id for u in units], ["engine"])
        d = decide_deploy_mode(
            last_sha="abc123",
            base_resolved=True,
            paths=[rel],
            units=units,
        )
        self.assertFalse(d.force_full)
        self.assertEqual(d.mode, "incremental")
        eng = build_unit("engine")
        assert eng is not None
        self.assertIn("apps/zr-workbuddy/engine/config", eng.local_rels)

    def test_policy_engine_bridge_incremental(self):
        from app.code_deploy.policy import decide_deploy_mode
        from app.code_deploy.units import build_unit

        units = [build_unit("engine"), build_unit("bridge")]
        d = decide_deploy_mode(
            last_sha="abc123",
            base_resolved=True,
            paths=[
                "apps/zr-workbuddy/engine/app/main.py",
                "apps/zr-workbuddy/plugins/mes-bridge/lib/client.js",
            ],
            units=units,
        )
        self.assertFalse(d.force_full)
        self.assertEqual(d.mode, "incremental")

    def test_execution_plan_matches_mode(self):
        from app.code_deploy.policy import resolve_confirm_mode, resolve_execution_plan

        full = [{"id": "engine"}, {"id": "bridge"}, {"id": "scripts"}]
        incr = [{"id": "engine"}]
        p_full = resolve_execution_plan(
            mode="full", force_full=True, units_full=full, units_incremental=incr
        )
        self.assertEqual(p_full["mode"], "full")
        self.assertEqual(p_full["unit_ids"], ["engine", "bridge", "scripts"])
        self.assertTrue(p_full["locked"])

        p_incr = resolve_execution_plan(
            mode="incremental", force_full=False, units_full=full, units_incremental=incr
        )
        self.assertEqual(p_incr["mode"], "incremental")
        self.assertEqual(p_incr["unit_ids"], ["engine"])
        self.assertFalse(p_incr["locked"])

        m, err = resolve_confirm_mode(
            job_mode="full", force_full=True, requested_mode="incremental"
        )
        self.assertEqual(m, "full")
        self.assertTrue(err)

        m2, err2 = resolve_confirm_mode(
            job_mode="incremental", force_full=False, requested_mode="full"
        )
        self.assertEqual(m2, "full")
        self.assertFalse(err2)

    def test_filter_unchanged_dirty_paths(self):
        import tempfile
        from pathlib import Path

        from app.code_deploy.diff_map import (
            file_content_fingerprint,
            filter_unchanged_dirty_paths,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "apps" / "zr-workbuddy" / "engine" / "requirements.txt"
            f.parent.mkdir(parents=True)
            f.write_text("fastapi>=0.110\n", encoding="utf-8")
            rel = "apps/zr-workbuddy/engine/requirements.txt"
            fp = file_content_fingerprint(root, rel)
            keep, skipped = filter_unchanged_dirty_paths(root, [rel], {rel: fp})
            self.assertEqual(keep, [])
            self.assertEqual(skipped, [rel])
            keep2, skipped2 = filter_unchanged_dirty_paths(root, [rel], {rel: "other"})
            self.assertEqual(keep2, [rel])
            self.assertEqual(skipped2, [])

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

    def test_remote_port_ignores_health_url(self):
        """health_url 公网反代口不得覆盖引擎 remote_engine_port。"""
        from app.code_deploy.config import CodeDeployConfig
        from app.code_deploy.ssh_sync import _resolve_remote_port

        cfg = CodeDeployConfig(
            enabled=True,
            health_url="http://175.178.238.31:8092/",
            remote_engine_port=8091,
        )
        self.assertEqual(_resolve_remote_port(cfg), 8091)
        cfg2 = CodeDeployConfig(enabled=True, health_url="", remote_engine_port=8092)
        self.assertEqual(_resolve_remote_port(cfg2), 8091)  # 8092 视为反代保留口


if __name__ == "__main__":
    unittest.main()

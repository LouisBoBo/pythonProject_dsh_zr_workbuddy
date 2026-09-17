#!/usr/bin/env python3
"""ensure_dsh_llm_meter 单测。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ensure_dsh_llm_meter import (
    METER_ID,
    METER_PKG,
    METER_VERSION,
    ensure_dsh_llm_meter,
    package_installed,
)


class EnsureLlmMeterTests(unittest.TestCase):
    def test_writes_cordis_and_need_install(self):
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td)
            (profile / "package.json").write_text(
                json.dumps({"name": "web", "dependencies": {}, "dsh": {"profile": {"bundles": []}}})
                + "\n",
                encoding="utf-8",
            )
            (profile / "cordis.patch.yml").write_text(
                "# header\n- id: webserver\n  config:\n    port: 3081\n",
                encoding="utf-8",
            )
            result = ensure_dsh_llm_meter(profile)
            self.assertFalse(result["installed"])
            self.assertTrue(result["need_install"])
            patch = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
            self.assertIn(f"id: {METER_ID}", patch)
            self.assertIn(METER_PKG, patch)
            self.assertIn("enabled: true", patch)
            self.assertIn("llm-meter/events.jsonl", patch)
            pkg = json.loads((profile / "package.json").read_text(encoding="utf-8"))
            self.assertNotIn(METER_PKG, pkg.get("dependencies") or {})

    def test_registers_when_installed(self):
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td)
            nm = profile.joinpath("node_modules", *METER_PKG.split("/"))
            nm.mkdir(parents=True)
            (nm / "package.json").write_text(
                json.dumps({"name": METER_PKG, "version": METER_VERSION}) + "\n",
                encoding="utf-8",
            )
            (profile / "package.json").write_text(
                json.dumps({"name": "web", "dependencies": {}, "dsh": {"profile": {"bundles": []}}})
                + "\n",
                encoding="utf-8",
            )
            (profile / "cordis.patch.yml").write_text("[]\n", encoding="utf-8")
            self.assertTrue(package_installed(profile))
            r1 = ensure_dsh_llm_meter(profile)
            self.assertTrue(r1["installed"])
            self.assertFalse(r1["need_install"])
            pkg = json.loads((profile / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(pkg["dependencies"].get(METER_PKG), METER_VERSION)
            self.assertIn(METER_PKG, pkg["dsh"]["profile"]["bundles"])
            r2 = ensure_dsh_llm_meter(profile)
            self.assertFalse(r2["need_install"])

    def test_idempotent_cordis(self):
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td)
            (profile / "package.json").write_text(
                json.dumps({"name": "web", "dependencies": {}}) + "\n", encoding="utf-8"
            )
            (profile / "cordis.patch.yml").write_text("[]\n", encoding="utf-8")
            ensure_dsh_llm_meter(profile)
            a = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
            ensure_dsh_llm_meter(profile)
            b = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
            self.assertEqual(a.count(f"id: {METER_ID}"), 1)
            self.assertEqual(a, b)


    def test_does_not_eat_mes_bridge_insert(self):
        """计量补丁不得误删 dsh-mes-bridge 的 insert（否则右上角账号头像整段消失）。"""
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td)
            (profile / "package.json").write_text(
                json.dumps({"name": "web", "dependencies": {}}) + "\n", encoding="utf-8"
            )
            (profile / "cordis.patch.yml").write_text(
                "# header\n"
                "- insert:\n"
                "    - id: dsh-mes-bridge\n"
                "      name: '@dsh-external/dsh-mes-bridge'\n"
                "\n"
                "# --- llm-meter (old insert form) ---\n"
                "- insert:\n"
                "    - id: llm-meter\n"
                "      name: '@zhongruan/dsh-llm-meter'\n"
                "      config:\n"
                "        enabled: false\n",
                encoding="utf-8",
            )
            ensure_dsh_llm_meter(profile)
            patch = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
            self.assertIn("id: dsh-mes-bridge", patch)
            self.assertIn("@dsh-external/dsh-mes-bridge", patch)
            self.assertEqual(patch.count("id: dsh-mes-bridge"), 1)
            self.assertEqual(patch.count(f"id: {METER_ID}"), 1)
            self.assertNotIn("- insert:\n    - id: llm-meter", patch)


if __name__ == "__main__":
    unittest.main()

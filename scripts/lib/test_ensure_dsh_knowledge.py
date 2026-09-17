#!/usr/bin/env python3
"""ensure_dsh_knowledge 单测。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ensure_dsh_knowledge import (
    KB_PKG,
    KB_VERSION,
    LEGACY_KB_PKGS,
    ensure_dsh_knowledge,
    package_installed,
)


class EnsureDshKnowledgeTest(unittest.TestCase):
    def test_fresh_profile_does_not_register_until_installed(self):
        """未装中软包时只写 cordis/allowBuilds，不往 package.json 塞 unpublished 依赖。"""
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td)
            (profile / "package.json").write_text(
                json.dumps(
                    {
                        "name": "dsh-profile-web",
                        "dependencies": {"@lemoncat7/dsh-knowledge": "2.9.6"},
                        "dsh": {"profile": {"bundles": ["@lemoncat7/dsh-knowledge"]}},
                    }
                ),
                encoding="utf-8",
            )
            (profile / "cordis.patch.yml").write_text(
                "# head\n- id: webserver\n  config:\n    host: 127.0.0.1\n    port: 3081\n",
                encoding="utf-8",
            )
            (profile / "pnpm-workspace.yaml").write_text(
                "packages:\n  - .\n\nnodeLinker: hoisted\nautoInstallPeers: false\n"
                "allowBuilds:\n  cloudflared: true\n",
                encoding="utf-8",
            )
            result = ensure_dsh_knowledge(profile)
            self.assertTrue(result["need_install"])
            self.assertEqual(result["pkg"], KB_PKG)
            ws = (profile / "pnpm-workspace.yaml").read_text(encoding="utf-8")
            self.assertIn("onnxruntime-node: true", ws)
            self.assertIn("cloudflared: true", ws)
            patch = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
            self.assertIn("extractionEnabled: false", patch)
            self.assertIn("databasePath:", patch)
            self.assertIn("connectionPath:", patch)
            self.assertIn("- id: knowledge", patch)
            pkg = json.loads((profile / "package.json").read_text(encoding="utf-8"))
            self.assertNotIn(KB_PKG, pkg["dependencies"])
            self.assertNotIn(KB_PKG, pkg["dsh"]["profile"]["bundles"])
            # 中软未装上前保留 lemoncat7，避免现场空窗
            self.assertEqual(pkg["dependencies"]["@lemoncat7/dsh-knowledge"], "2.9.6")
            self.assertIn("@lemoncat7/dsh-knowledge", pkg["dsh"]["profile"]["bundles"])

    def test_purges_legacy_when_zhongruan_installed(self):
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td)
            nm = profile.joinpath("node_modules", *KB_PKG.split("/"))
            nm.mkdir(parents=True)
            (nm / "package.json").write_text(f'{{"name":"{KB_PKG}"}}\n', encoding="utf-8")
            (profile / "package.json").write_text(
                json.dumps(
                    {
                        "dependencies": {
                            KB_PKG: KB_VERSION,
                            "@lemoncat7/dsh-knowledge": "2.9.6",
                            "dsh-knowledge-base": "0.1.4",
                        },
                        "dsh": {
                            "profile": {
                                "bundles": [
                                    KB_PKG,
                                    "@lemoncat7/dsh-knowledge",
                                    "dsh-knowledge-base",
                                ]
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (profile / "cordis.patch.yml").write_text(
                "# ---\n"
                "- id: knowledge\n"
                f"  name: '{KB_PKG}'\n"
                "  config:\n"
                "    backend: local\n"
                "    databasePath: !!js dshHomePath('knowledge/knowledge.sqlite')\n"
                "    connectionPath: !!js dshHomePath('knowledge/connection.json')\n"
                "    exposeApi: false\n"
                "    exposeWeb: true\n"
                "    extractionEnabled: false\n",
                encoding="utf-8",
            )
            (profile / "pnpm-workspace.yaml").write_text(
                "packages:\n  - .\nallowBuilds:\n  esbuild: true\n  onnxruntime-node: true\n"
                "  protobufjs: true\n  sharp: true\n  tesseract.js: false\n",
                encoding="utf-8",
            )
            r1 = ensure_dsh_knowledge(profile)
            r2 = ensure_dsh_knowledge(profile)
            self.assertFalse(r1["need_install"])
            self.assertFalse(r2["need_install"])
            self.assertTrue(package_installed(profile))
            pkg = json.loads((profile / "package.json").read_text(encoding="utf-8"))
            for legacy in LEGACY_KB_PKGS:
                self.assertNotIn(legacy, pkg["dependencies"])
                self.assertNotIn(legacy, pkg["dsh"]["profile"]["bundles"])
            self.assertIn(KB_PKG, pkg["dependencies"])
            self.assertIn(KB_PKG, pkg["dsh"]["profile"]["bundles"])
            patch = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
            self.assertIn("databasePath:", patch)
            self.assertEqual(patch.count("- id: knowledge"), 1)


if __name__ == "__main__":
    unittest.main()

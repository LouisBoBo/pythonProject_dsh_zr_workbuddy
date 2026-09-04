"""feature_install：契约校验、zip 安全、安装与隔离卸载。"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from app import feature_install


ROOT = Path(__file__).resolve().parents[3]  # repo root? engine/tests -> engine -> zr-workbuddy -> apps -> repo
# tests at apps/zr-workbuddy/engine/tests → parents[0]=tests, [1]=engine, [2]=zr-workbuddy, [3]=apps, [4]=repo
REPO = Path(__file__).resolve().parents[4]
SAMPLE = REPO / "docs" / "examples" / "sample-third-party"


class FeatureInstallTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.mkdtemp(prefix="feat-test-")
        self.features = os.path.join(self._td, "features")
        self.quarantine = os.path.join(self._td, "quarantine")
        os.makedirs(self.features, exist_ok=True)
        self._p_feat = mock.patch.object(feature_install, "features_dir", return_value=self.features)
        self._p_q = mock.patch.object(feature_install, "quarantine_dir", return_value=self.quarantine)
        self._p_tmp = mock.patch.object(
            feature_install, "install_tmp_dir", return_value=os.path.join(self._td, "tmp")
        )
        self._p_cfg = mock.patch.object(
            feature_install,
            "_cfg",
            return_value={"max_zip_bytes": 5_000_000, "max_files": 200, "allow_force": True},
        )
        self._p_feat.start()
        self._p_q.start()
        self._p_tmp.start()
        self._p_cfg.start()
        # plugins_store 读写落到临时目录
        state = os.path.join(self._td, "plugins.json")
        self._p_state = mock.patch("app.plugins_store._STATE_PATH", state)
        self._p_lock = mock.patch("app.plugins_store._LOCK_PATH", state + ".lock")
        self._p_fdir = mock.patch("app.plugins_store._FEATURES_DIR", self.features)
        self._p_state.start()
        self._p_lock.start()
        self._p_fdir.start()

    def tearDown(self):
        for p in (
            self._p_feat,
            self._p_q,
            self._p_tmp,
            self._p_cfg,
            self._p_state,
            self._p_lock,
            self._p_fdir,
        ):
            p.stop()
        shutil.rmtree(self._td, ignore_errors=True)

    def _write_feature(self, fid: str, index: str, manifest: dict | None = None) -> str:
        d = os.path.join(self.features if False else self._td, fid)
        # write into a staging dir outside features for install_from_dir source
        d = os.path.join(self._td, "src", fid)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.js"), "w", encoding="utf-8") as f:
            f.write(index)
        man = manifest or {
            "id": fid,
            "name": fid,
            "purpose": "test",
            "version": "0.0.1",
        }
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False)
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
            f.write("# test\n")
        return d

    _GOOD_JS = """
export const name = "demo-feat";
export const inject = ["tools"];
export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) return;
}
"""

    def test_sample_validates(self):
        self.assertTrue(SAMPLE.is_dir(), f"missing sample at {SAMPLE}")
        rep = feature_install.validate_feature_dir(str(SAMPLE))
        self.assertTrue(rep["ok"], rep.get("errors"))
        self.assertEqual(rep["id"], "sample-third-party")

    def test_reject_npm_import(self):
        src = self._write_feature(
            "bad-npm",
            'import x from "lodash";\nexport const name = "bad-npm";\n'
            'export const inject = ["tools"];\nexport function apply(ctx) {}\n',
        )
        # fix id in js name mismatch - use matching
        src = self._write_feature(
            "bad-npm",
            'import x from "lodash";\nexport const name = "bad-npm";\n'
            'export const inject = ["tools"];\nexport function apply(ctx) {}\n',
            {"id": "bad-npm", "name": "x", "purpose": "y"},
        )
        rep = feature_install.validate_feature_dir(src)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("lodash" in e for e in rep["errors"]))

    def test_install_and_force(self):
        src = self._write_feature(
            "demo-feat",
            self._GOOD_JS,
            {"id": "demo-feat", "name": "Demo", "purpose": "demo", "version": "1.0.0"},
        )
        out = feature_install.install_from_dir(src, force=False, enable=True)
        self.assertTrue(out["ok"], out)
        self.assertTrue(os.path.isfile(os.path.join(self.features, "demo-feat", "index.js")))
        out2 = feature_install.install_from_dir(src, force=False, enable=True)
        self.assertFalse(out2["ok"])
        out3 = feature_install.install_from_dir(src, force=True, enable=True)
        self.assertTrue(out3["ok"], out3)

    def test_zip_slip_rejected(self):
        zpath = os.path.join(self._td, "evil.zip")
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("../escape.js", "export const name='x';")
        dest = os.path.join(self._td, "unz")
        os.makedirs(dest, exist_ok=True)
        errs = feature_install.safe_extract_zip(
            zpath, dest, max_bytes=1_000_000, max_files=50
        )
        self.assertTrue(errs)

    def test_zip_install(self):
        src = self._write_feature(
            "zip-feat",
            self._GOOD_JS.replace("demo-feat", "zip-feat"),
            {"id": "zip-feat", "name": "Z", "purpose": "z"},
        )
        zpath = os.path.join(self._td, "ok.zip")
        with zipfile.ZipFile(zpath, "w") as zf:
            for name in ("index.js", "manifest.json", "README.md"):
                zf.write(os.path.join(src, name), arcname=f"zip-feat/{name}")
        out = feature_install.install_from_zip(zpath, force=False, enable=True)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["id"], "zip-feat")

    def test_uninstall_purge(self):
        src = self._write_feature(
            "gone-feat",
            self._GOOD_JS.replace("demo-feat", "gone-feat"),
            {"id": "gone-feat", "name": "G", "purpose": "g"},
        )
        self.assertTrue(feature_install.install_from_dir(src, enable=True)["ok"])
        out = feature_install.uninstall_feature("gone-feat", purge=True)
        self.assertTrue(out["ok"], out)
        self.assertTrue(out.get("purged"))
        self.assertFalse(os.path.isdir(os.path.join(self.features, "gone-feat")))
        self.assertTrue(os.path.isdir(out["quarantine"]))

    def test_id_dir_mismatch(self):
        d = os.path.join(self._td, "src", "wrong-dir")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.js"), "w", encoding="utf-8") as f:
            f.write(self._GOOD_JS.replace("demo-feat", "other-id"))
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "other-id", "name": "o", "purpose": "o"}, f)
        rep = feature_install.validate_feature_dir(d)
        self.assertFalse(rep["ok"])


if __name__ == "__main__":
    unittest.main()

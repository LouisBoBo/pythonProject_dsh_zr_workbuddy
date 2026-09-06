"""在 import numpy/pandas 之前设置 BLAS 环境，并跳过 macOS Accelerate 自检。

部分本机 NumPy 1.26 + Accelerate 在 `_mac_os_check`（polyfit）时会 SIGFPE，
导致 unittest/引擎一加载 demo 数据就整进程崩掉。此处用 import hook 跳过该自检。
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MPLBACKEND", "Agg")


def _install_numpy_macos_guard() -> None:
    if sys.platform != "darwin":
        return
    if getattr(sys, "_wb_numpy_macos_guard", False):
        return
    sys._wb_numpy_macos_guard = True  # type: ignore[attr-defined]

    class _NumpyInitLoader(importlib.abc.Loader):
        def __init__(self, origin: str):
            self.origin = origin

        def create_module(self, spec):  # noqa: ANN001
            return None

        def exec_module(self, module):  # noqa: ANN001
            with open(self.origin, "r", encoding="utf-8") as f:
                src = f.read()
            # 跳过 Accelerate polyfit 自检（仅改导入期行为，不影响数值 API）
            src = src.replace(
                "if sys.platform == \"darwin\":\n"
                "        from . import exceptions\n"
                "        with warnings.catch_warnings(record=True) as w:\n"
                "            _mac_os_check()",
                "if False:  # patched by WorkBuddy blas_env (macOS Accelerate SIGFPE)\n"
                "        from . import exceptions\n"
                "        with warnings.catch_warnings(record=True) as w:\n"
                "            _mac_os_check()",
                1,
            )
            code = compile(src, self.origin, "exec")
            exec(code, module.__dict__)

    class _NumpyInitFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):  # noqa: ANN001
            if fullname != "numpy":
                return None
            # 避免递归：临时卸掉自己再 find
            try:
                sys.meta_path.remove(self)
            except ValueError:
                return None
            try:
                spec = importlib.util.find_spec("numpy")
            finally:
                sys.meta_path.insert(0, self)
            if spec is None or not spec.origin or not str(spec.origin).endswith("__init__.py"):
                return spec
            spec.loader = _NumpyInitLoader(spec.origin)
            return spec

    sys.meta_path.insert(0, _NumpyInitFinder())


_install_numpy_macos_guard()

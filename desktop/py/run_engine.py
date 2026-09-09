"""桌面安装包内嵌引擎入口：uvicorn app.main:app。"""
from __future__ import annotations

import os
import sys


def main() -> None:
    host = os.environ.get("WORKBUDDY_ENGINE_HOST", "127.0.0.1")
    port = int(os.environ.get("WORKBUDDY_ENGINE_PORT", "18000"))
    eng = os.environ.get("WORKBUDDY_ENGINE_DIR", "").strip()
    if not eng:
        # runtime/app/desktop/py/run_engine.py → runtime/app/apps/zr-workbuddy/engine
        here = os.path.dirname(os.path.abspath(__file__))
        eng = os.path.normpath(
            os.path.join(here, "..", "..", "apps", "zr-workbuddy", "engine")
        )
    if not os.path.isdir(eng):
        raise SystemExit(f"引擎目录不存在: {eng}")
    os.chdir(eng)
    # uvicorn 加载 app.main → 需要 engine 根在 sys.path（不是 engine/app）
    if eng not in sys.path:
        sys.path.insert(0, eng)
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

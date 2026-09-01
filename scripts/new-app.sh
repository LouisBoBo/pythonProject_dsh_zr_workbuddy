#!/bin/bash
# 框架：按标准架构生成空 AI 应用（不含业务：无 MES/面板/LLM）
# 用法: scripts/new-app.sh <应用名>
set -e
APP="${1:?用法: new-app.sh <应用名>}"
if ! [[ "$APP" =~ ^[a-z][a-z0-9_-]*$ ]]; then
  echo "应用名须小写字母开头 [a-z0-9_-]"; exit 1
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPDIR="$ROOT/apps/$APP"
[ -d "$APPDIR" ] && { echo "已存在 $APPDIR"; exit 1; }

mkdir -p "$APPDIR/engine/config" "$APPDIR/engine/data" "$APPDIR/engine/app" \
  "$APPDIR/plugins/${APP}-runtime/lib" "$APPDIR/engine/tests"

cat > "$APPDIR/VERSION" <<EOF
0.1.0
EOF

cat > "$APPDIR/engine/config/runtime.yaml" <<YAML
# 本应用运行时（业务配置）
server:
  host: 127.0.0.1
  port: 8000
python: python3
YAML

cat > "$APPDIR/engine/config/config.example.yaml" <<YAML
# 业务密钥与连接配置示例（复制为 config.yaml，勿提交）
# 按你的应用自行增删字段
app:
  name: $APP
YAML

cat > "$APPDIR/engine/engine_cli.py" <<'PY'
#!/usr/bin/env python3
"""引擎 CLI：stdout 单行 JSON。与 /api/cli 同一实现（cli_ops）。"""
from __future__ import annotations
import asyncio
import json
import sys

from app.cli_ops import run_async


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    rest = args[1:]
    out = asyncio.run(run_async(cmd, rest))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
PY
chmod +x "$APPDIR/engine/engine_cli.py"

cat > "$APPDIR/engine/app/__init__.py" <<'PY'
PY

cat > "$APPDIR/engine/app/runtime_conf.py" <<'PY'
"""读取 runtime.yaml —— 委托仓库唯一实现 scripts/lib/read_runtime.py。"""
from __future__ import annotations
import importlib.util
import os
from typing import Any, Dict

_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_ENGINE_ROOT)))
_HELPER = os.path.join(_REPO_ROOT, "scripts", "lib", "read_runtime.py")


def _fallback_runtime() -> Dict[str, Any]:
    host = os.environ.get("APP_ENGINE_HOST") or "127.0.0.1"
    port_raw = os.environ.get("APP_ENGINE_PORT") or "8000"
    python = os.environ.get("APP_ENGINE_PYTHON") or "python3"
    try:
        port = int(port_raw)
    except Exception:
        port = 8000
    return {"host": str(host), "port": port, "python": str(python)}


def read_runtime() -> Dict[str, Any]:
    path = os.path.join(_ENGINE_ROOT, "config", "runtime.yaml")
    if os.path.isfile(_HELPER):
        spec = importlib.util.spec_from_file_location("dsh_read_runtime", _HELPER)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.read_runtime(path)
    return _fallback_runtime()
PY

cat > "$APPDIR/engine/app/cli_ops.py" <<'PY'
"""与 engine_cli / HTTP /api/cli 共用的命令实现。"""
from __future__ import annotations


async def run_async(cmd: str, rest: list[str]) -> dict:
    if cmd == "ask":
        q = " ".join(rest).strip()
        if not q:
            return {"ok": False, "detail": "问题为空"}
        return {"ok": True, "reply": f"收到: {q}", "chart": None, "table": None}
    if cmd == "status":
        return {"ok": True, "ready": True}
    return {"ok": False, "detail": f"未知命令: {cmd}"}
PY

cat > "$APPDIR/engine/app/main.py" <<PY
"""HTTP 入口；端口见 config/runtime.yaml。插件统一调用 /api/cli。"""
from __future__ import annotations

from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .runtime_conf import read_runtime

app = FastAPI(
    title="$APP Engine",
    version="0.1.0",
    openapi_tags=[
        {"name": "状态", "description": "健康与运行时"},
        {"name": "引擎约定", "description": "与 CLI 一致的插件入口"},
    ],
)
# 本机 Origin；引擎应只绑 127.0.0.1，勿对公网暴露（无自造鉴权）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3080", "http://localhost:3080"],
    allow_origin_regex=r"http://(127\\.0\\.0\\.1|localhost):\\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status", tags=["状态"], summary="引擎状态")
def status():
    return {"ok": True, "app": "$APP"}


@app.get("/api/runtime", tags=["状态"], summary="读取运行时地址")
def runtime():
    return {"ok": True, **read_runtime()}


class CliBody(BaseModel):
    cmd: str
    args: List[str] = []


@app.post("/api/cli", tags=["引擎约定"], summary="插件统一调用入口")
async def api_cli(body: CliBody):
    from .cli_ops import run_async
    cmd = (body.cmd or "").strip()
    if not cmd:
        return {"ok": False, "detail": "cmd 不能为空"}
    return await run_async(cmd, list(body.args or []))
PY

mkdir -p "$APPDIR/features"
echo '{"enabled":[]}' > "$APPDIR/engine/data/plugins.json"

cat > "$APPDIR/engine/requirements.txt" <<'TXT'
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
pyyaml>=6.0
TXT

cat > "$APPDIR/engine/tests/test_smoke.py" <<'PY'
"""冒烟：应用可导入。"""
import unittest

class Smoke(unittest.TestCase):
    def test_import_app(self):
        from app.main import app
        self.assertIsNotNone(app)

if __name__ == "__main__":
    unittest.main()
PY

# runtime 库（非 Cordis 插件）— HTTP 优先模板
cat > "$APPDIR/plugins/${APP}-runtime/package.json" <<JSON
{
  "name": "@dsh-external/${APP}-runtime",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "lib/index.js",
  "exports": { ".": "./lib/index.js" },
  "description": "应用引擎调用辅助（业务库，非 Cordis 插件）",
  "dshApp": { "cordisPlugin": false },
  "license": "MIT"
}
JSON

cat > "$APPDIR/plugins/${APP}-runtime/lib/index.js" <<'JS'
/**
 * 模板：统一走 HTTP /api/cli；地址解析唯一入口 scripts/lib/read_runtime.py。
 */
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ENGINE_DIR = path.join(__dirname, "..", "..", "..", "engine");
const REPO_ROOT = path.join(ENGINE_DIR, "..", "..", "..");
const READ_RUNTIME = path.join(REPO_ROOT, "scripts", "lib", "read_runtime.py");
const RUNTIME_PATH = path.join(ENGINE_DIR, "config", "runtime.yaml");

function loadRuntime() {
  const defaults = { host: "127.0.0.1", port: 8000, python: "python3" };
  try {
    if (fs.existsSync(READ_RUNTIME)) {
      const out = execFileSync("python3", [READ_RUNTIME, RUNTIME_PATH], {
        encoding: "utf8",
        timeout: 5000,
      });
      const j = JSON.parse(out.trim());
      return {
        host: j.host || defaults.host,
        port: Number(j.port || defaults.port),
        python: j.python || defaults.python,
      };
    }
  } catch {
    /* fallback */
  }
  return {
    host: process.env.APP_ENGINE_HOST || defaults.host,
    port: Number(process.env.APP_ENGINE_PORT || defaults.port),
    python: process.env.APP_ENGINE_PYTHON || defaults.python,
  };
}

const RT = loadRuntime();
export const ENGINE_HOST = RT.host;
export const ENGINE_PORT = RT.port;
export const PYTHON = RT.python;
export const TIMEOUT_MS = 60000;

function httpJson(method, urlPath, body, timeoutMs = TIMEOUT_MS) {
  return new Promise((resolve) => {
    const payload = body == null ? null : Buffer.from(JSON.stringify(body), "utf8");
    const req = http.request(
      {
        host: ENGINE_HOST,
        port: ENGINE_PORT,
        path: urlPath,
        method,
        timeout: timeoutMs,
        headers: {
          Accept: "application/json",
          ...(payload
            ? { "Content-Type": "application/json", "Content-Length": payload.length }
            : {}),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
          } catch {
            resolve({ ok: false, detail: "引擎响应非 JSON" });
          }
        });
      },
    );
    req.on("error", (err) => resolve({ ok: false, detail: String(err.message || err).slice(0, 400) }));
    req.on("timeout", () => {
      req.destroy();
      resolve({ ok: false, detail: "超时" });
    });
    if (payload) req.write(payload);
    req.end();
  });
}

function probeEngine() {
  return new Promise((resolve) => {
    const req = http.get(
      { host: ENGINE_HOST, port: ENGINE_PORT, path: "/api/runtime", timeout: 1500 },
      (res) => {
        res.resume();
        resolve(res.statusCode >= 200 && res.statusCode < 500);
      },
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

export async function ensureEngineHttp() {
  if (await probeEngine()) return true;
  const appName = path.basename(path.dirname(ENGINE_DIR));
  const sh = path.join(REPO_ROOT, "scripts", "engine.sh");
  if (!fs.existsSync(sh)) return false;
  try {
    execFileSync("bash", [sh, appName, "ensure"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
      timeout: 45000,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch {
    /* probe below */
  }
  return probeEngine();
}

export async function runEngine(args, timeoutMs = TIMEOUT_MS) {
  const list = Array.isArray(args) ? args : [];
  const cmd = String(list[0] || "").trim();
  if (!cmd) return { ok: false, detail: "命令为空" };
  if (!(await ensureEngineHttp())) {
    return { ok: false, detail: `引擎未就绪（${ENGINE_HOST}:${ENGINE_PORT}）` };
  }
  return httpJson("POST", "/api/cli", { cmd, args: list.slice(1).map(String) }, timeoutMs);
}

export function resultRender(_a, v) {
  const lines = [];
  if (v && v.reply) lines.push(String(v.reply));
  if (v && v.detail) lines.push(String(v.detail));
  return [{ type: "text", text: lines.join("\n\n") || JSON.stringify(v) }];
}
JS

cat > "$APPDIR/plugins/README.md" <<MD
# $APP plugins

常驻 Cordis 包（若需要热插拔 Agent 工具，仿 \`zr-workbuddy/plugins/mes-bridge\`：
唯一 bridge + \`features/\` + \`engine/data/plugins.json\`，用 Cordis \`ctx.plugin\` / fiber.dispose，勿往 profile 再堆正式包）。

引擎库：\`${APP}-runtime\`（非 Cordis）。业务能力放 \`../features/\`。
MD

cat > "$APPDIR/README.md" <<MD
# $APP

版本见 \`VERSION\`。

\`\`\`bash
scripts/engine.sh $APP ensure
scripts/plugin.sh --app $APP new demo "示例功能"
# 热插拔需自备 bridge（参考 zr-workbuddy）；仅有 features 目录不够
scripts/test.sh $APP
\`\`\`

- 端口：\`engine/config/runtime.yaml\`（\`/api/runtime\` 走 read_runtime）
- 密钥：复制 \`config.example.yaml\` → \`config.yaml\`（勿提交）
- CLI 与 \`/api/cli\` 共用 \`engine/app/cli_ops.py\`
MD

echo "✅ 已生成空应用 apps/$APP（含 /api/cli、runtime 库、features/、冒烟测试）"
echo "加功能: scripts/plugin.sh --app $APP new <id> \"说明\""
echo "引擎: scripts/engine.sh $APP ensure"
echo "热插拔: 需仿 zr-workbuddy 增加 bridge（见 plugins/README.md）"

/**
 * 应用级引擎调用辅助（业务层，非框架）。
 * 统一走 HTTP /api/cli；地址解析唯一入口：scripts/lib/read_runtime.py
 */
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
/** plugins/<app>-runtime/lib → apps/<app>/engine */
export const ENGINE_DIR = path.join(__dirname, "..", "..", "..", "engine");
export const ENGINE_CLI = path.join(ENGINE_DIR, "engine_cli.py");
/** apps/<app>/engine → 仓库根 */
const REPO_ROOT = path.join(ENGINE_DIR, "..", "..", "..");
const READ_RUNTIME = path.join(REPO_ROOT, "scripts", "lib", "read_runtime.py");
const RUNTIME_PATH = path.join(ENGINE_DIR, "config", "runtime.yaml");
const CHARTS_DIR = path.join(ENGINE_DIR, "data", "charts");

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
    /* fallback below */
  }
  // 与 scripts/lib/read_runtime.py / runtime_conf 环境变量约定一致
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
          const raw = Buffer.concat(chunks).toString("utf8");
          try {
            resolve(JSON.parse(raw));
          } catch {
            resolve({
              ok: false,
              detail: `引擎响应非 JSON（HTTP ${res.statusCode}）: ${raw.slice(0, 200)}`,
            });
          }
        });
      },
    );
    req.on("error", (err) =>
      resolve({ ok: false, detail: String(err.message || err).slice(0, 400) }),
    );
    req.on("timeout", () => {
      req.destroy();
      resolve({ ok: false, detail: "引擎 HTTP 请求超时" });
    });
    if (payload) req.write(payload);
    req.end();
  });
}

function probeEngine(port = ENGINE_PORT, host = ENGINE_HOST) {
  return new Promise((resolve) => {
    const req = http.get(
      { host, port, path: "/api/runtime", timeout: 1500 },
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

/** apps/<name>/engine → 应用名；启停只走 scripts/engine.sh，禁止在此直接 spawn uvicorn（防竞态孤儿进程） */
const APP_NAME = path.basename(path.dirname(ENGINE_DIR));
const ENGINE_SH = path.join(REPO_ROOT, "scripts", "engine.sh");

/** 确保引擎 HTTP 就绪（与 engine.sh ensure 同一路径） */
export async function ensureEngineHttp() {
  if (await probeEngine()) return true;
  if (!fs.existsSync(ENGINE_SH)) {
    return false;
  }
  try {
    execFileSync("bash", [ENGINE_SH, APP_NAME, "ensure"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
      timeout: 45000,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch {
    /* 下面再 probe */
  }
  return probeEngine();
}

/**
 * 统一引擎调用：args[0]=cmd，其余为参数。
 * 例：runEngine(["ask", "今日再制品工单"])
 */
export async function runEngine(args, timeoutMs = TIMEOUT_MS) {
  const list = Array.isArray(args) ? args : [];
  const cmd = String(list[0] || "").trim();
  if (!cmd) return { ok: false, detail: "命令为空" };
  const rest = list.slice(1).map(String);

  const up = await ensureEngineHttp();
  if (!up) {
    return { ok: false, detail: `引擎 HTTP 未就绪（${ENGINE_HOST}:${ENGINE_PORT}）` };
  }
  return httpJson("POST", "/api/cli", { cmd, args: rest }, timeoutMs);
}

export function parseDataUri(uri) {
  if (typeof uri !== "string" || !uri.startsWith("data:")) return null;
  const m = /^data:(image\/(?:png|jpeg|jpg|webp|gif));base64,(.+)$/i.exec(uri.replace(/\s/g, ""));
  if (!m) return null;
  let mediaType = m[1].toLowerCase();
  if (mediaType === "image/jpg") mediaType = "image/jpeg";
  try {
    const buf = Buffer.from(m[2], "base64");
    if (!buf.length) return null;
    return { mediaType, data: new Uint8Array(buf), buffer: buf };
  } catch {
    return null;
  }
}

function persistChartFile(parsed) {
  try {
    fs.mkdirSync(CHARTS_DIR, { recursive: true });
    const name = `chart-${Date.now()}.png`;
    const full = path.join(CHARTS_DIR, name);
    fs.writeFileSync(full, parsed.buffer);
    // Agent 侧只回相对路径，避免把本机绝对路径泄漏进会话
    return path.join("data", "charts", name);
  } catch {
    return null;
  }
}

export async function attachChart(ctx, result) {
  const parsed = parseDataUri(result && result.chart);
  if (!parsed) return result;

  const filePath = persistChartFile(parsed);
  let next = { ...result };
  if (filePath) {
    next.chart_file = filePath;
    const note = next.note ? `${next.note} ` : "";
    next.note = `${note}（图表已保存）`.trim();
  }

  // 必须用 ctx.get：Cordis 对未 inject 的服务用 ctx.xxx 会直接抛错，不是 undefined
  const store = ctx && typeof ctx.get === "function" ? ctx.get("attachments") : null;
  if (store && typeof store.saveImage === "function") {
    try {
      const ref = await store.saveImage({
        data: parsed.data,
        mediaType: parsed.mediaType,
        name: "chart.png",
      });
      next = { ...next, chart_attachment: ref };
    } catch {
      /* fall through to inline */
    }
  }

  // 无 attachment 时保留 data URI，供 resultRender 内联
  if (!next.chart_attachment) {
    next.chart_inline = result.chart;
  }
  return next;
}

export function resultRender(_a, v) {
  const stripMarks = (s) =>
    String(s || "")
      .replace(/<<<\s*思考\s*>>>/g, "")
      .replace(/<<<\s*回答\s*>>>/g, "")
      .replace(/<<<[^>]*$/g, "");
  const lines = [];
  if (v && typeof v.thinking === "string" && v.thinking) {
    lines.push("【思考过程】\n" + stripMarks(v.thinking));
  }
  if (v && typeof v.reply === "string" && v.reply) lines.push(stripMarks(v.reply));
  if (v && typeof v.note === "string" && v.note) lines.push("> " + v.note);
  if (v && typeof v.detail === "string" && v.detail) lines.push(v.detail);
  if (v && Array.isArray(v.table) && v.table.length) {
    lines.push(
      v.table
        .map((r) => `- ${r.label ?? ""}: ${r.value ?? ""}${r.extra ? `（${r.extra}）` : ""}`)
        .join("\n"),
    );
  }
  const blocks = [{ type: "text", text: lines.join("\n\n") || JSON.stringify(v) }];
  if (v && v.chart_attachment && typeof v.chart_attachment === "object") {
    blocks.push({ type: "image", attachment: v.chart_attachment });
  } else if (v && typeof v.chart_inline === "string" && v.chart_inline.startsWith("data:")) {
    blocks.push({ type: "image", url: v.chart_inline });
  } else if (v && typeof v.chart === "string" && v.chart.startsWith("data:")) {
    blocks.push({ type: "image", url: v.chart });
  }
  return blocks;
}

/**
 * mes-bridge —— 唯一常驻 Cordis 包（热插拔宿主）。
 *
 * Cordis 规范：ctx.plugin → Fiber；dispose 卸工具；inject 声明硬依赖。
 * 本应用约定：engine/data/plugins.json 为启停真相源；features/ 热插拔，面板壳常驻。
 */
import { pathToFileURL } from "node:url";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { defineTool } from "@deepseek-ai/dsh-tools";
import * as runtime from "@dsh-external/mes-runtime";

export const name = "dsh-mes-bridge";
export const inject = ["tools"];

const __dirname = path.dirname(fileURLToPath(import.meta.url));
/** plugins/mes-bridge/lib → apps/zr-workbuddy */
const APP_ROOT = path.join(__dirname, "..", "..", "..");
const ENGINE_DIR = path.join(APP_ROOT, "engine");
const FEATURES_DIR = path.join(APP_ROOT, "features");
const STATE_PATH = path.join(ENGINE_DIR, "data", "plugins.json");
const POLL_MS = 1200;

function listFeatureIds() {
  if (!fs.existsSync(FEATURES_DIR)) return [];
  return fs
    .readdirSync(FEATURES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && fs.existsSync(path.join(FEATURES_DIR, d.name, "index.js")))
    .map((d) => d.name)
    .sort();
}

function readManifest(id) {
  const p = path.join(FEATURES_DIR, id, "manifest.json");
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return { id, name: id, purpose: "" };
  }
}

function featureMtime(id) {
  try {
    return fs.statSync(path.join(FEATURES_DIR, id, "index.js")).mtimeMs;
  } catch {
    return 0;
  }
}

/** 读可无锁（写方 atomic replace）；启停变更一律走 Python plugins_store（flock）。 */
function readEnabled() {
  try {
    const data = JSON.parse(fs.readFileSync(STATE_PATH, "utf8"));
    if (Array.isArray(data.enabled)) return data.enabled.map(String);
  } catch {
    /* default: all */
  }
  return listFeatureIds();
}

function pluginsStore(op, idOrJson) {
  const args = ["-m", "app.plugins_store", op];
  if (idOrJson != null && idOrJson !== "") args.push(String(idOrJson));
  const out = execFileSync("python3", args, {
    cwd: ENGINE_DIR,
    encoding: "utf8",
    timeout: 8000,
  });
  return JSON.parse(String(out).trim() || "{}");
}

export function apply(ctx) {
  const mesEngine = {
    ...runtime,
    defineTool,
  };
  ctx.provide("mesEngine", mesEngine);

  runtime
    .ensureEngineHttp()
    .then((ok) => {
      console.log(
        ok
          ? "[mes-bridge] 引擎 HTTP 就绪"
          : "[mes-bridge] 引擎未就绪，可 scripts/engine.sh zr-workbuddy ensure",
      );
    })
    .catch(() => {});

  /** @type {Map<string, { dispose: () => Promise<void> }>} */
  const fibers = new Map();
  /** @type {Map<string, number>} id → 加载时 index.js mtimeMs */
  const loadedMtime = new Map();
  /** @type {Map<string, string>} id → 最近一次加载失败原因 */
  const loadErrors = new Map();
  let syncing = false;
  let syncDirty = false;
  let lastKey = "";

  async function unload(id) {
    const f = fibers.get(id);
    if (!f) {
      loadErrors.delete(id);
      loadedMtime.delete(id);
      return;
    }
    try {
      await f.dispose();
    } catch (e) {
      console.warn("[mes-bridge] dispose 失败", id, e);
    }
    fibers.delete(id);
    loadedMtime.delete(id);
    loadErrors.delete(id);
    console.log("[mes-bridge] 已停用 feature:", id);
  }

  async function load(id) {
    const file = path.join(FEATURES_DIR, id, "index.js");
    if (!fs.existsSync(file)) {
      const msg = "feature 目录或 index.js 不存在";
      loadErrors.set(id, msg);
      console.warn("[mes-bridge]", id, msg);
      return false;
    }
    try {
      // ?t= 强制新加载；旧 ESM 模块对象可能仍留在内存（可接受的小泄漏）
      const url = pathToFileURL(file).href + "?t=" + Date.now();
      const mod = await import(url);
      const fiberLike = ctx.plugin(mod);
      const fiber = typeof fiberLike?.then === "function" ? await fiberLike : fiberLike;
      if (!fiber || typeof fiber.dispose !== "function") {
        const msg = "未返回可 dispose 的 fiber";
        loadErrors.set(id, msg);
        console.warn("[mes-bridge]", id, msg);
        return false;
      }
      fibers.set(id, fiber);
      loadedMtime.set(id, featureMtime(id));
      loadErrors.delete(id);
      console.log("[mes-bridge] 已启用 feature:", id);
      return true;
    } catch (e) {
      const msg = String(e && e.message ? e.message : e).slice(0, 300);
      loadErrors.set(id, msg);
      console.warn("[mes-bridge] 加载失败（不影响同轮其它 feature）:", id, msg);
      return false;
    }
  }

  async function sync() {
    if (syncing) {
      syncDirty = true;
      return;
    }
    syncing = true;
    try {
      do {
        syncDirty = false;
        const available = new Set(listFeatureIds());
        const target = readEnabled().filter((id) => available.has(id));
        const key = [...target].sort().join(",") + "|" + [...loadErrors.keys()].sort().join(",");

        for (const id of [...fibers.keys()]) {
          if (!target.includes(id)) {
            try {
              await unload(id);
            } catch (e) {
              console.warn("[mes-bridge] unload 异常", id, e);
            }
          }
        }
        for (const id of target) {
          const mt = featureMtime(id);
          if (fibers.has(id)) {
            // 已加载但源文件变更 → Cordis dispose 后重新 ctx.plugin（热重载）
            if (mt && loadedMtime.get(id) === mt) continue;
            try {
              await unload(id);
            } catch (e) {
              console.warn("[mes-bridge] 重载前 unload 异常", id, e);
            }
          }
          try {
            await load(id);
          } catch (e) {
            const msg = String(e && e.message ? e.message : e).slice(0, 300);
            loadErrors.set(id, msg);
            console.warn("[mes-bridge] sync 单项异常:", id, msg);
          }
        }
        for (const id of [...loadErrors.keys()]) {
          if (!target.includes(id)) loadErrors.delete(id);
        }
        if (key !== lastKey) {
          lastKey = key;
          const failed = [...loadErrors.keys()];
          console.log(
            "[mes-bridge] features 同步 →",
            target.join(", ") || "(无)",
            failed.length ? `; 失败: ${failed.join(", ")}` : "",
          );
        }
      } while (syncDirty);
    } catch (e) {
      console.warn("[mes-bridge] sync 外层失败:", e);
    } finally {
      syncing = false;
      if (syncDirty) {
        syncDirty = false;
        sync().catch(() => {});
      }
    }
  }

  function featureStatus(fid) {
    const enabled = readEnabled().includes(fid);
    const loaded = fibers.has(fid);
    const err = loadErrors.get(fid);
    let live = "idle";
    if (loaded) live = "loaded";
    else if (err) live = "error";
    return {
      id: fid,
      enabled,
      loaded,
      live,
      error: err || null,
      ...(readManifest(fid) || {}),
    };
  }

  ctx.tools.register(
    defineTool({
      name: "mes_plugin",
      description:
        "MES 功能热插拔：action=list|enable|disable|reload；id 为 feature 目录名（如 mes-ask）。" +
        "启停写 engine/data/plugins.json（真相源），无需重启 DSH。" +
        "改 feature 源码后可用 reload，或等 bridge 按 mtime 自动重载。",
      parameters: {
        action: { type: "string", required: true, description: "list | enable | disable | reload" },
        id: { type: "string", description: "feature id（enable/disable/reload 时必填）" },
      },
      output: {
        schema: { type: "object", additionalProperties: true },
        render: runtime.resultRender,
      },
      timeoutMs: 20000,
      async execute(args) {
        const action = String(args.action || "").trim();
        const id = String(args.id || "").trim();
        if (action === "list") {
          const rows = listFeatureIds().map(featureStatus);
          return {
            ok: true,
            reply: rows
              .map((r) => {
                const on = r.enabled ? "enabled" : "disabled";
                const err = r.error ? ` ERR=${r.error}` : "";
                return `- ${r.id}: ${on}/${r.live}${err} — ${r.purpose || r.name || ""}`;
              })
              .join("\n"),
            available: listFeatureIds(),
            enabled: readEnabled(),
            loaded: [...fibers.keys()],
            errors: Object.fromEntries(loadErrors),
            features: rows,
          };
        }
        if (action === "reload") {
          if (!id) return { ok: false, detail: "需要 id" };
          if (!listFeatureIds().includes(id)) return { ok: false, detail: `未知 feature: ${id}` };
          if (!readEnabled().includes(id)) {
            return { ok: false, detail: `${id} 未启用；请先 enable` };
          }
          await unload(id);
          await load(id);
          const st = featureStatus(id);
          return {
            ok: !st.error,
            detail: st.error ? `重载失败: ${st.error}` : `已重载 ${id}`,
            feature: st,
          };
        }
        if (action === "enable" || action === "disable") {
          if (!id) return { ok: false, detail: "需要 id" };
          const avail = new Set(listFeatureIds());
          if (action === "enable" && !avail.has(id)) {
            return { ok: false, detail: `未知 feature: ${id}` };
          }
          // 单一写路径：plugins_store（flock），不二次 runEngine 改同一文件
          let written;
          try {
            written = pluginsStore(action, id);
          } catch (e) {
            return { ok: false, detail: `写入 plugins.json 失败: ${String(e.message || e).slice(0, 200)}` };
          }
          if (written && written.ok === false) {
            return written;
          }
          await sync();
          const st = featureStatus(id);
          return {
            ok: !st.error,
            detail: st.error
              ? `已写入启停，但加载失败: ${st.error}`
              : action === "enable"
                ? `已启用 ${id}`
                : `已停用 ${id}`,
            enabled: readEnabled(),
            feature: st,
          };
        }
        return { ok: false, detail: "action 须为 list|enable|disable|reload" };
      },
    }),
  );

  const timer = setInterval(() => {
    sync().catch(() => {});
  }, POLL_MS);
  if (typeof timer.unref === "function") timer.unref();

  const watchers = [];
  try {
    fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });
    watchers.push(
      fs.watch(path.dirname(STATE_PATH), { persistent: false }, (_e, filename) => {
        if (!filename || String(filename).includes("plugins.json")) sync().catch(() => {});
      }),
    );
  } catch {
    /* poll only */
  }
  try {
    if (fs.existsSync(FEATURES_DIR)) {
      watchers.push(
        fs.watch(FEATURES_DIR, { persistent: false }, () => {
          sync().catch(() => {});
        }),
      );
    }
  } catch {
    /* poll mtime */
  }

  ctx.effect(() => () => {
    clearInterval(timer);
    for (const w of watchers) {
      try {
        w.close();
      } catch {
        /* ignore */
      }
    }
    return Promise.all([...fibers.keys()].map((id) => unload(id)));
  });

  sync().catch(() => {});
}

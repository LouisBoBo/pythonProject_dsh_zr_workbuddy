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

const WORKBUDDY_CODE_DEV_PROMPT = [
  "## ZR-WorkBuddy 写码路由（强制）",
  "当用户要改代码、改页面、改菜单、挪菜单、加功能、做报表页、Cursor 写码、删除菜单子项时：",
  "1. **本轮第一个工具调用必须是 `mes_code_dev_begin`，且 message=用户原话（原样，禁止留空）**。",
  "2. **禁止**用 `run_code` / code-mode（会触发 scheduler.prepare 报错 → 本轮运行失败），以及 Bash / Grep / Glob / Read / Write / StrReplace 去扫或改用户工程来「完成写码」。",
  "3. **禁止**先长思考、先查 Vite/日志/HMR；改菜单类诉求同样走 begin → 主聊天工具卡。",
  "4. 工具卡内完成：选目录 → 梳理需求 → 确认后才由 Cursor Local 改盘；未确认禁止 `mes_code_dev_start`。",
  "5. `mes_code_dev_begin` 返回后**禁止**再复述「已为您打开写码工具卡…请在卡片中…」——卡已在主聊天展示，回复留空或仅一句「请在上方工具卡确认」。",
  "6. **禁止**在同一轮里再调其它工具（尤其 `run_code`）；begin 成功即停，等用户在卡片操作。",
  "7. 写码不会自动 git commit；提交用 `mes_code_commit_begin`。",
  "示例：「看板管理菜单删除设备看板子项」→ 立刻 `mes_code_dev_begin`，message 填该句原文。",
  "",
  "## ZR-WorkBuddy 一体部署路由（强制）",
  "当用户要部署到预发/上线、自动化部署、发布到服务器时：",
  "1. **本轮只调用一次 `mes_code_deploy_begin`**，参数全部留空即可（默认 staging）。",
  "2. **禁止**传 env=production/prod；**禁止**再调 prepare/confirm；**禁止**失败后换参数重试出第二张卡。",
  "3. **禁止**自己 SSH/rsync；出卡后只说一句「请点确认部署」，不要复述原因/单元列表。",
  "示例：「部署上线」→ 立刻 `mes_code_deploy_begin()`。",
].join("\n");

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

  // 写入系统提示：不依赖工作区是否加载 .dsh/skills（用户工程目录常无本仓 Skill）
  try {
    const sp = ctx.get && ctx.get("systemPrompt");
    if (sp && typeof sp.section === "function") {
      sp.section({
        name: "workbuddy:code-dev-route",
        order: 35,
        text: WORKBUDDY_CODE_DEV_PROMPT,
      });
      console.log("[mes-bridge] 已注册 systemPrompt：workbuddy:code-dev-route");
    } else {
      console.warn("[mes-bridge] 无 systemPrompt 服务：写码路由硬约束未注入");
    }
  } catch (e) {
    console.warn("[mes-bridge] systemPrompt 注入失败", e);
  }

  // 启动时断言 TOOL_RUNTIME_SCHEDULER 可解析：profile 若另装了 dsh-tools，
  // agent-loop 会在任意工具（含 mes_code_dev_begin）上炸
  // Cannot read properties of undefined (reading 'prepare')。
  import("@deepseek-ai/dsh-tools")
    .then((toolsMod) => {
      const sym =
        toolsMod.TOOL_RUNTIME_SCHEDULER ||
        (toolsMod.default && toolsMod.default.TOOL_RUNTIME_SCHEDULER);
      const sched = sym && ctx.tools ? ctx.tools[sym] : null;
      if (!sched || typeof sched.prepare !== "function") {
        console.error(
          "[mes-bridge] FATAL: ctx.tools 缺少同源 TOOL_RUNTIME_SCHEDULER.prepare。" +
            "多为 ~/.dsh/profiles/web/node_modules/@deepseek-ai/dsh-tools 与宿主双实例。" +
            "请执行: scripts/check-vendor.sh --fix && scripts/plugin.sh --app zr-workbuddy install bridge --restart",
        );
      } else {
        console.log("[mes-bridge] TOOL_RUNTIME_SCHEDULER.prepare 可用");
      }
    })
    .catch((e) => {
      console.warn(
        "[mes-bridge] scheduler 健康检查跳过:",
        e && e.message ? e.message : e,
      );
    });

  // 次要防线：拒绝 run_code（真正的 prepare 崩在 agent-loop Symbol，须靠 check-vendor 对齐）
  try {
    if (ctx.tools && typeof ctx.tools.guard === "function") {
      ctx.tools.guard((exec) => {
        const name = String((exec && exec.name) || "");
        if (name === "run_code") {
          return (
            "禁止使用 run_code。改菜单/写码请只调用 mes_code_dev_begin，在工具卡内确认后开工。"
          );
        }
        return undefined;
      });
      console.log("[mes-bridge] 已注册 tools.guard：拒绝 run_code");
    }
  } catch (e) {
    console.warn("[mes-bridge] tools.guard 注册失败", e);
  }

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
      // 必须收成普通对象再交给 Cordis：部分运行时对 Module Namespace 的
      // `typeof apply === "function"` 检测会失败（报 received object）。
      const plugin = {
        name: mod.name,
        inject: mod.inject,
        apply: mod.apply,
      };
      if (mod.Config) plugin.Config = mod.Config;
      if (typeof plugin.apply !== "function") {
        throw new Error('feature 未导出 apply 函数（收到 ' + typeof plugin.apply + '）');
      }
      const fiberLike = ctx.plugin(plugin);
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

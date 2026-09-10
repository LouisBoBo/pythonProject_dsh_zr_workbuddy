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

const WORKBUDDY_ROUTE_TABLE = [
  "## ZR-WorkBuddy 意图分流（强制 · 先看这张表）",
  "| 用户意图 | 本轮第一个工具 | 禁止误用 |",
  "| --- | --- | --- |",
  "| 改代码 / 改页面 / 改菜单 / 删菜单子项 / 加功能 | `mes_code_dev_begin` | 不是审码、不是 Bash/git |",
  "| 代码审核 / 审码 / code review / 看看改动 | `mes_code_review_begin` | 不是 `mes_code_dev_begin`、不是 git diff |",
  "| 提交代码 / git commit / push 本批 | `mes_code_commit_begin` | 不是 `mes_code_review_run`、不是 Bash git |",
  "| 部署 / 上线 / 预发 / 发布服务器 | `mes_code_deploy_begin` | 不是 SSH/rsync 自部署 |",
  "| MES 查产量良率工单 | `mes_ask` | 不是写码 |",
  "| PCB 工艺问答 | `mes_pcb` | 不是 MES 查数 |",
].join("\n");

const WORKBUDDY_CODE_DEV_PROMPT = [
  "## ZR-WorkBuddy 写码路由（强制）",
  "当用户要改代码、改页面、改菜单、挪菜单、加功能、做报表页、Cursor 写码、删除菜单子项时（**不是**审码/提交/部署）：",
  "1. **本轮第一个工具调用必须是 `mes_code_dev_begin`，且 message=用户原话（原样，禁止留空）**。",
  "2. **禁止**用 `run_code` / code-mode（会触发 scheduler.prepare 报错 → 本轮运行失败），以及 Bash / Grep / Glob / Read / Write / StrReplace 去扫或改用户工程来「完成写码」。",
  "3. **禁止**先长思考、先查 Vite/日志/HMR；改菜单类诉求同样走 begin → 主聊天工具卡。",
  "4. 工具卡内完成：选目录 → 梳理需求 → 确认后才由 Cursor Local 改盘；未确认禁止开工（确认只走 UI → /api/code-dev/confirm）。",
  "5. `mes_code_dev_begin` 返回后**禁止**再输出任何用户可见文字（含「请在卡片中确认」「请在上方工具卡确认」）——卡已在主聊天展示，回复必须留空。",
  "6. **禁止**在同一轮里再调其它工具（尤其 `run_code` / Write / StrReplace / Bash 改盘）；begin 成功即停，等用户在卡片操作。",
  "7. 写码不会自动 git commit；提交用 `mes_code_commit_begin`；部署用 `mes_code_deploy_begin`。",
  "示例：「看板管理菜单删除设备看板子项」→ 立刻 `mes_code_dev_begin`，message 填该句原文。",
].join("\n");

const WORKBUDDY_CODE_REVIEW_PROMPT = [
  "## ZR-WorkBuddy 审码路由（强制）",
  "当用户说「审核代码 / 审码 / code review / 代码审核 / 看看改动有没有问题 / 帮我 review」时：",
  "1. **本轮第一个工具调用必须是 `mes_code_review_begin`**（不是 `mes_code_dev_begin`，不是 Bash / Grep / Read / git）。",
  "2. **禁止**用 Bash 执行 `git diff` / `git status` / `git log` / `git show` / `grep` / `rg` 扫仓代审；审码走引擎 `code-review` 车道 + 主聊天工具卡。",
  "3. **禁止**用 `mes_code_dev_begin` 处理纯审码诉求（不写码、不改菜单、不删文件）。",
  "4. 工具卡内：选目录 → 勾选文件 → 点「开始审核」；确认前禁止 `mes_code_review_run`。",
  "5. `mes_code_review_begin` 返回后回复留空或仅一句「请在上方审码工具卡操作」，禁止复述 diff 结论。",
  "6. 提交前门禁 findings 走 `mes_code_commit_begin`，**不要**用 `mes_code_review_run` 代替提交门禁。",
  "示例：「代码审核」→ 立刻 `mes_code_review_begin()`，不要先 ls / git status。",
].join("\n");

const WORKBUDDY_CODE_COMMIT_PROMPT = [
  "## ZR-WorkBuddy 提交路由（强制）",
  "当用户说「提交代码 / 帮我 commit / push / 提交本批 / 提交门禁」时：",
  "1. **本轮第一个工具调用必须是 `mes_code_commit_begin`**（不是 Bash git、不是 `mes_code_review_run`）。",
  "2. **禁止** Bash 执行 `git add` / `git commit` / `git push`；提交须经工具卡门禁 → 人确认。",
  "3. **禁止**用全量审码 `mes_code_review_run` 代替提交门禁 findings 列表。",
  "4. 工具卡内：选目录 → 勾选文件 → 跑门禁 → 确认后才 commit/push。",
  "5. `mes_code_commit_begin` 返回后回复留空，禁止口头代用户确认。",
  "示例：「提交代码」→ 立刻 `mes_code_commit_begin()`。",
].join("\n");

const WORKBUDDY_CODE_DEPLOY_PROMPT = [
  "## ZR-WorkBuddy 一体部署路由（强制）",
  "当用户要部署到预发/上线、自动化部署、发布到服务器时：",
  "1. **本轮只调用一次 `mes_code_deploy_begin`**，参数全部留空即可（默认 staging）。",
  "2. **禁止**传 env=production/prod；**禁止**再调 prepare/confirm；**禁止**失败后换参数重试出第二张卡。",
  "3. **禁止** Bash SSH/rsync/scp 自部署；出卡后回复留空，等用户点确认部署。",
  "示例：「部署上线」→ 立刻 `mes_code_deploy_begin()`。",
].join("\n");

/** 磁盘写入类工具：禁止绕过 code-dev 沙箱+HITL 直接改用户工程 */
const DISK_WRITE_TOOLS = new Set([
  "Write",
  "write",
  "StrReplace",
  "str_replace",
  "Edit",
  "edit",
  "Delete",
  "delete",
  "ApplyPatch",
  "apply_patch",
  "MultiEdit",
  "multi_edit",
  "NotebookEdit",
  "notebook_edit",
]);

function bashLooksLikeDiskWrite(raw) {
  const s = String(raw || "");
  if (!s.trim()) return false;
  if (/(^|[\s;|&])(rm|mv|cp|install|tee|truncate|chmod|chown|ln)\b/i.test(s)) return true;
  if (/(^|[\s;|&])sed\s+(-[^\s]*i|--in-place)/i.test(s)) return true;
  if (/(^|[\s;|&])perl\s+(-[^\s]*i)/i.test(s)) return true;
  if (/(^|[^=])>{1,2}\s*\S/.test(s) && !/>&\s*\d/.test(s)) return true;
  if (/\b(git\s+(add|commit|push|checkout|reset|clean|rebase|merge)|npm\s+install|pnpm\s+i|yarn\s+add)\b/i.test(s))
    return true;
  return false;
}

/** Bash 读盘代审：禁止 git diff/status 等绕过 mes_code_review_begin */
function bashLooksLikeManualCodeReview(raw) {
  const s = String(raw || "");
  if (!s.trim()) return false;
  if (/\bgit\s+(diff|status|log|show|blame)\b/i.test(s)) return true;
  if (/\b(rg|grep|find)\b[\s\S]{0,120}\.(vue|tsx?|jsx?|py|go|java)\b/i.test(s)) return true;
  if (/\bls\b[\s\S]{0,80}(src|router|menu|views)/i.test(s)) return true;
  return false;
}

/** Bash 自部署：禁止 ssh/rsync 绕过 mes_code_deploy_begin */
function bashLooksLikeManualDeploy(raw) {
  const s = String(raw || "");
  if (!s.trim()) return false;
  if (/\b(ssh|rsync|scp|sftp)\b/i.test(s)) return true;
  if (/\bansible-playbook\b/i.test(s)) return true;
  return false;
}

function toolExecPayload(exec) {
  if (!exec || typeof exec !== "object") return "";
  const parts = [];
  for (const k of ["args", "arguments", "input", "params", "command", "cmd", "code", "script"]) {
    const v = exec[k];
    if (v == null) continue;
    if (typeof v === "string") parts.push(v);
    else {
      try {
        parts.push(JSON.stringify(v));
      } catch {
        parts.push(String(v));
      }
    }
  }
  return parts.join("\n");
}


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

function resolveBridgePython() {
  const cands = [
    runtime.PYTHON,
    process.env.APP_ENGINE_PYTHON,
    "/usr/local/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
    "/opt/homebrew/bin/python3",
    "python3",
  ].filter(Boolean);
  const seen = new Set();
  for (const c of cands) {
    const bin = String(c);
    if (seen.has(bin)) continue;
    seen.add(bin);
    try {
      execFileSync(bin, ["-c", "import sys; assert sys.version_info[:2] >= (3, 10)"], {
        encoding: "utf8",
        timeout: 4000,
      });
      return bin;
    } catch (e) {
      /* try next */
    }
  }
  throw new Error(
    "找不到可用的 Python 3.10+（plugins_store）。请安装 Python 3.10+，或在 runtime.yaml / APP_ENGINE_PYTHON 指定解释器。",
  );
}

function pluginsStore(op, idOrJson) {
  const args = ["-m", "app.plugins_store", op];
  if (idOrJson != null && idOrJson !== "") args.push(String(idOrJson));
  let bin;
  try {
    bin = resolveBridgePython();
  } catch (e) {
    throw new Error(String(e && e.message ? e.message : e));
  }
  try {
    const out = execFileSync(bin, args, {
      cwd: ENGINE_DIR,
      encoding: "utf8",
      timeout: 8000,
    });
    return JSON.parse(String(out).trim() || "{}");
  } catch (e) {
    const detail = String((e && (e.stderr || e.message)) || e).slice(0, 400);
    throw new Error("plugins_store 调用失败（python=" + bin + "）：" + detail);
  }
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
        name: "workbuddy:route-table",
        order: 34,
        text: WORKBUDDY_ROUTE_TABLE,
      });
      sp.section({
        name: "workbuddy:code-dev-route",
        order: 35,
        text: WORKBUDDY_CODE_DEV_PROMPT,
      });
      sp.section({
        name: "workbuddy:code-review-route",
        order: 36,
        text: WORKBUDDY_CODE_REVIEW_PROMPT,
      });
      sp.section({
        name: "workbuddy:code-commit-route",
        order: 37,
        text: WORKBUDDY_CODE_COMMIT_PROMPT,
      });
      sp.section({
        name: "workbuddy:code-deploy-route",
        order: 38,
        text: WORKBUDDY_CODE_DEPLOY_PROMPT,
      });
      console.log(
        "[mes-bridge] 已注册 systemPrompt：route-table + code-dev/review/commit/deploy",
      );
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

  // 硬防线：拒绝绕过 code-dev 的磁盘写入（run_code / Write / StrReplace / 危险 Bash）
  try {
    if (ctx.tools && typeof ctx.tools.guard === "function") {
      ctx.tools.guard((exec) => {
        const name = String((exec && exec.name) || "");
        const lower = name.toLowerCase();
        if (name === "run_code" || lower === "run_code") {
          return (
            "禁止使用 run_code。写码→mes_code_dev_begin；审码→mes_code_review_begin；" +
            "提交→mes_code_commit_begin；部署→mes_code_deploy_begin。"
          );
        }
        if (DISK_WRITE_TOOLS.has(name) || DISK_WRITE_TOOLS.has(lower)) {
          return (
            "禁止直接 " +
            name +
            " 改用户工程。写码/删菜单必须走 mes_code_dev_begin → 确认卡 → Cursor 沙箱。"
          );
        }
        if (lower === "bash" || lower === "shell" || lower === "run_terminal_cmd" || lower === "terminal") {
          const payload = toolExecPayload(exec);
          if (bashLooksLikeDiskWrite(payload)) {
            return (
              "禁止用 " +
              name +
              " 改盘（rm/mv/cp/重定向/git 写等）。请走 mes_code_dev_begin 工具卡。"
            );
          }
          if (bashLooksLikeManualCodeReview(payload)) {
            return (
              "禁止用 " +
              name +
              " 扫仓/git diff 代审。用户要审码请只调 mes_code_review_begin，在审码工具卡内选目录并开始审核。"
            );
          }
          if (bashLooksLikeManualDeploy(payload)) {
            return (
              "禁止用 " +
              name +
              " 自部署（ssh/rsync/scp）。用户要部署请只调 mes_code_deploy_begin，在部署确认卡内点确认。"
            );
          }
        }
        return undefined;
      });
      console.log("[mes-bridge] 已注册 tools.guard：拒绝 run_code / 写盘工具 / 危险 Bash");
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
  let featureReloadCount = 0;

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
      featureReloadCount += 1;
      if (featureReloadCount === 40 || featureReloadCount === 80) {
        console.warn(
          "[mes-bridge] feature 热重载已累计 " +
            featureReloadCount +
            " 次（ESM 模块对象可能残留）。开发态建议适时重启 DSH 回收内存。",
        );
      }
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

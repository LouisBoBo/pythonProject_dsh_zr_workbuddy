/**
 * 热插拔 feature：code-deploy（一体部署）
 * 无 import npm；算数在 engine/app/code_deploy。
 *
 * 主聊天 HITL：begin/prepare 返回 code_deploy_ui + presentationMeta，
 * 由 mes-bridge tool.call.toolview 展示确认卡（全量/增量 → 人确认 → SSH）。
 */
export const name = "code-deploy";
export const inject = ["tools"];

const OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: true,
  properties: {
    ok: { type: "boolean" },
    reply: { type: "string" },
    detail: { oneOf: [{ type: "string" }, { type: "null" }] },
    job_id: { oneOf: [{ type: "string" }, { type: "null" }] },
    can_deploy: { oneOf: [{ type: "boolean" }, { type: "null" }] },
    units: {
      oneOf: [
        { type: "array", items: { type: "object", additionalProperties: true } },
        { type: "null" },
      ],
    },
  },
};

function eng(ctx) {
  return ctx.get("mesEngine");
}

function timeoutOf(e) {
  return Math.max(e.TIMEOUT_MS || 60000, 180000);
}

function cdpSlimUi(ui) {
  if (!ui || typeof ui !== "object") return null;
  if (ui.kind === "success") {
    return {
      kind: "success",
      title: ui.title || "部署完成",
      entry_url: ui.entry_url || ui.access_url || ui.health_url || "",
      remote: ui.remote || "",
      env: ui.env || "",
      units: Array.isArray(ui.units) ? ui.units.slice(0, 20) : [],
      actions: Array.isArray(ui.actions) ? ui.actions.slice(0, 8) : [],
    };
  }
  const forceFull = !!(ui.force_full || ui.locked_mode === "full");
  const mode = forceFull ? "full" : ui.mode === "full" ? "full" : "incremental";
  const rawList =
    mode === "full"
      ? ui.units_full || ui.units || ui.unit_labels || []
      : ui.units_incremental || ui.units || ui.unit_labels || [];
  let ids = [];
  if (Array.isArray(ui.unit_ids) && ui.unit_ids.length) {
    ids = ui.unit_ids.map(String).filter(Boolean);
  } else if (ui.execution && Array.isArray(ui.execution.unit_ids)) {
    ids = ui.execution.unit_ids.map(String).filter(Boolean);
  } else {
    ids = (rawList || [])
      .map((x) => (typeof x === "string" ? x : (x && x.id) || ""))
      .filter(Boolean);
  }
  const labelById = {};
  const kindById = {};
  for (const x of ui.unit_labels || rawList || []) {
    if (!x || typeof x !== "object" || !x.id) continue;
    labelById[String(x.id)] = String(x.label || x.id);
    kindById[String(x.id)] = String(x.kind || "");
  }
  const units = ids.slice(0, 24).map((id) => ({
    id,
    label: labelById[id] || id,
    kind: kindById[id] || "",
  }));
  const sha = String(ui.head_sha || "").trim();
  const ws = String(ui.workspace || "").trim();
  const wsShort = ws ? ws.replace(/\/+$/, "").split("/").pop() : "";
  const reasons = Array.isArray(ui.reasons)
    ? ui.reasons
    : ui.policy && Array.isArray(ui.policy.reasons)
      ? ui.policy.reasons
      : [];
  const reason =
    String(ui.reason || "").trim() ||
    reasons
      .map((x) => String(x || "").trim())
      .filter(Boolean)
      .slice(0, 2)
      .join("；")
      .slice(0, 220);
  return {
    kind: "confirm",
    job_id: ui.job_id || "",
    mode,
    force_full: forceFull,
    first_deploy: !!ui.first_deploy,
    env: ui.env || "",
    ssh_host: ui.ssh_host || "",
    ssh_app_path: ui.ssh_app_path || "",
    entry_url: ui.entry_url || ui.access_url || ui.health_url || "",
    workspace: wsShort || ws,
    base_ref: String(ui.base_ref || "").slice(0, 48),
    head_ref: String(ui.head_ref || "HEAD").slice(0, 48),
    head_sha_short: sha ? sha.slice(0, 10) : "",
    unit_ids: ids,
    units,
    unit_count: ids.length || Number(ui.unit_count) || 0,
    can_deploy: ui.can_deploy !== false && ids.length > 0,
    reason,
    note: String(ui.note || "").slice(0, 120),
    summary: forceFull ? "全量" : mode === "full" ? "全量" : "增量",
  };
}

function cdpQuietRender(_args, value) {
  // 不把长 reply/detail 再渲成一块文字，避免和确认卡叠成「一堆框」
  if (value && value.code_deploy_ui) return [{ type: "text", text: "" }];
  if (value && value.deploy_success) {
    const u = value.deploy_success.entry_url || value.reply || "部署完成";
    return [{ type: "text", text: String(u) }];
  }
  const msg = (value && (value.reply || value.detail)) || "";
  return [{ type: "text", text: String(msg).slice(0, 200) }];
}

function cdpPresentationMeta(_args, value) {
  if (value && value.code_deploy_ui) {
    const slim = cdpSlimUi(value.code_deploy_ui);
    if (!slim) return { wb: { t: "cdp-none" } };
    return { wb: { t: "cdp-" + slim.kind, ui: slim } };
  }
  if (value && value.deploy_success) {
    const slim = cdpSlimUi(Object.assign({ kind: "success" }, value.deploy_success));
    return { wb: { t: "cdp-success", ui: slim || { kind: "success" } } };
  }
  return { wb: { t: "cdp-none" } };
}

export function apply(ctx) {
  const e = eng(ctx);
  if (!e) {
    console.error("[code-deploy] mesEngine 未提供：请启用 mes-bridge");
    return;
  }
  const t = timeoutOf(e);

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_deploy_begin",
      description:
        "【一体部署唯一入口】用户说部署/上线/预发时：本轮只调用本工具一次，参数全可空。" +
        "禁止传 env=production/prod；禁止再调 mes_code_deploy_prepare；出卡后禁止长回复或重试。" +
        "人点确认卡才会同步（WorkBuddy 仓按单元增量；普通项目同步整个仓库）。",
      parameters: {
        workspace: {
          type: "string",
          description: "可空；空=配置 default_workspace",
        },
        env: {
          type: "string",
          description: "可空；默认 staging。禁止 production",
        },
        mode: {
          type: "string",
          description: "可空；默认 auto",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: cdpQuietRender,
        presentationMeta: cdpPresentationMeta,
      },
      timeoutMs: Math.max(t, 120000),
      async execute(args) {
        const parts = ["code-deploy-prepare"];
        const ws = String((args && args.workspace) || "").trim();
        if (ws) parts.push(ws);
        let env = String((args && args.env) || "").trim().toLowerCase();
        if (env === "prod" || env === "production" || env === "生产") env = "";
        if (env) parts.push("--env", env);
        const mode = String((args && args.mode) || "").trim();
        if (mode) parts.push("--mode", mode);
        const pick = await e.runEngine(parts);
        if (!pick || !pick.ok) {
          return {
            ok: false,
            reply: (pick && (pick.reply || pick.detail)) || "部署准备失败",
            detail: (pick && pick.detail) || "",
            code_deploy_ui: null,
          };
        }
        // 不把 units_full / 长 reply 塞进工具结果正文（Cordis 会再渲一块）
        return {
          ok: true,
          job_id: pick.job_id,
          can_deploy: pick.can_deploy,
          reply: "",
          detail: null,
          code_deploy_ui: pick.code_deploy_ui,
          source: "code_deploy",
        };
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_deploy_status",
      description:
        "ZR-WorkBuddy：查看一体部署车道是否就绪（开关、SSH、浏览器入口）。" +
        "示例：「部署功能开了吗」。",
      parameters: {},
      output: { schema: OUTPUT_SCHEMA, render: e.resultRender },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute() {
        return await e.runEngine(["code-deploy-status"]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_deploy_prepare",
      description:
        "【勿主动调用】内部/排障用；用户部署请只用 mes_code_deploy_begin。",
      parameters: {
        workspace: { type: "string", description: "本机 Git 仓库根，可空=配置默认" },
        env: { type: "string", description: "环境名，默认 staging" },
        base_ref: { type: "string", description: "对比基线，空=上次成功部署 SHA" },
        mode: {
          type: "string",
          description: "auto|full|incremental；auto=无上次部署则全量",
        },
        unit_ids: {
          type: "array",
          items: { type: "string" },
          description: "强制指定单元，如 feature:code-commit、engine",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: cdpQuietRender,
        presentationMeta: cdpPresentationMeta,
      },
      timeoutMs: Math.max(e.TIMEOUT_MS || 60000, 120000),
      async execute(args) {
        const parts = ["code-deploy-prepare"];
        const ws = String(args.workspace || "").trim();
        if (ws) parts.push(ws);
        let env = String(args.env || "").trim().toLowerCase();
        if (env === "prod" || env === "production" || env === "生产") env = "";
        if (env) parts.push("--env", env);
        const base = String(args.base_ref || "").trim();
        if (base) parts.push("--base", base);
        const mode = String(args.mode || "").trim();
        if (mode) parts.push("--mode", mode);
        const ids = Array.isArray(args.unit_ids) ? args.unit_ids : [];
        for (const id of ids) {
          const s = String(id || "").trim();
          if (s) parts.push("--unit", s);
        }
        const pick = await e.runEngine(parts);
        if (!pick || !pick.ok) {
          return {
            ok: false,
            reply: (pick && (pick.reply || pick.detail)) || "部署准备失败",
            code_deploy_ui: null,
          };
        }
        return {
          ok: true,
          job_id: pick.job_id,
          can_deploy: pick.can_deploy,
          reply: "",
          detail: null,
          code_deploy_ui: pick.code_deploy_ui,
          source: "code_deploy",
        };
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_deploy_confirm",
      description:
        "ZR-WorkBuddy【一体部署确认】：人确认后 SSH/rsync，并收尾拉起引擎+聊天壳。" +
        "须带确认卡签发的 HITL nonce；禁止仅凭 confirmed=true。通常由工具卡调用，勿代替用户点确认。",
      parameters: {
        job_id: { type: "string", required: true, description: "prepare 返回的 job_id" },
        nonce: { type: "string", required: true, description: "确认卡签发的 HITL nonce" },
        decision: { type: "string", description: "approve|reject" },
        mode: { type: "string", description: "full|incremental" },
        unit_ids: {
          type: "array",
          items: { type: "string" },
          description: "确认时勾选的单元 id；全量可不传",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: cdpPresentationMeta,
      },
      timeoutMs: Math.max(e.TIMEOUT_MS || 60000, 300000),
      async execute(args) {
        const nonce = String(args.nonce || "").trim();
        if (!nonce) {
          return { ok: false, detail: "缺少 HITL nonce", reply: "请在部署确认卡操作" };
        }
        const jobId = String(args.job_id || "").trim();
        if (!jobId) return { ok: false, detail: "job_id 不能为空" };
        const parts = ["code-deploy-confirm", jobId, "nonce=" + nonce];
        const decision = String(args.decision || "approve").trim();
        parts.push("--decision", decision);
        const mode = String(args.mode || "").trim();
        if (mode) parts.push("--mode", mode);
        const ids = Array.isArray(args.unit_ids) ? args.unit_ids : [];
        for (const id of ids) {
          const s = String(id || "").trim();
          if (s) parts.push("--unit", s);
        }
        return await e.runEngine(parts);
      },
    }),
  );
}

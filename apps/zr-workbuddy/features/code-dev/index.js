/**
 * 热插拔 feature：code-dev（本机 Cursor Local 写码）
 * 无 import npm；算数在 engine/app/code_dev。
 *
 * 主聊天 HITL：begin 返回 code_dev_ui + presentationMeta，
 * 由 mes-bridge tool.call.toolview 在主对话工具卡内选目录/填需求/确认开工。
 * 禁止依赖浮层面板 / ask_user_question；确认前绝不 start Job。
 */
export const name = "code-dev";
export const inject = ["tools"];

const OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: true,
  properties: {
    ok: { type: "boolean" },
    reply: { type: "string" },
    detail: { oneOf: [{ type: "string" }, { type: "null" }] },
    job_id: { oneOf: [{ type: "string" }, { type: "null" }] },
    job: { oneOf: [{ type: "object", additionalProperties: true }, { type: "null" }] },
  },
};

function eng(ctx) {
  return ctx.get("mesEngine");
}

function timeoutOf(e) {
  return Math.max(e.TIMEOUT_MS || 60000, 120000);
}

function cdPresentationMeta(_args, value) {
  if (value && value.code_dev_ui) {
    const kind = value.code_dev_ui.kind || "pick";
    return { wb: { t: "cd-" + kind, ui: value.code_dev_ui } };
  }
  if (value && value.job_id) {
    return { wb: { t: "cd-job", job_id: value.job_id } };
  }
  return { wb: { t: "cd-none" } };
}

function cdCardOnlyRender(args, value, fallback) {
  if (!value || value.ok === false || !value.code_dev_ui) {
    return fallback(args, value);
  }
  return [{ type: "text", text: "" }];
}

export function apply(ctx) {
  const e = eng(ctx);
  if (!e) {
    console.error("[code-dev] mesEngine 未提供：请启用 mes-bridge");
    return;
  }
  const t = timeoutOf(e);

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_dev_begin",
      description:
        "【写码主入口】用户说「写码 / 改代码 / 改页面 / 改菜单 / 挪菜单 / 加功能 / 开发页面 / Cursor 写码」" +
        "（含「物料出库写到仓库管理菜单」这类改菜单诉求）时必须只调本工具，且应作为本轮第一个工具调用。" +
        "**必须把用户原话原样传入 message**（勿留空），可选 workspace；返回主聊天工具卡（选目录→梳理需求→确认）。" +
        "工具卡顶部已有中文引导（选目录、填诉求、确认后开工），本工具成功返回后必须立刻结束本轮：" +
        "禁止再输出任何用户可见文字（含中英文「已打开写码工具卡/development tool card」、步骤复述、操作指引）。",
      parameters: {
        workspace: {
          type: "string",
          description: "可选：本机工程绝对路径",
        },
        message: {
          type: "string",
          required: true,
          description: "必填：用户本轮原话/写码诉求（原样传入，工具卡会自动填入「原始写码诉求」）",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: (a, v) => cdCardOnlyRender(a, v, e.resultRender),
        presentationMeta: cdPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const workspace = String((args && args.workspace) || "").trim();
        const message = String((args && args.message) || "").trim();
        const cmd = ["code-dev-pick"];
        if (workspace) cmd.push("workspace=" + workspace);
        if (message) cmd.push("requirement=" + message);
        const pick = await e.runEngine(cmd);
        if (!pick || !pick.ok) return pick;
        const ui = pick.code_dev_ui || null;
        if (ui) {
          if (workspace) ui.workspace = workspace;
          if (message) {
            ui.requirement = message;
            ui.original_goal = message;
          }
        }
        return {
          ok: true,
          reply: "",
          detail: null,
          workspace: (ui && ui.workspace) || workspace || pick.workspace || "",
          code_dev_ui: ui,
          suggestions: pick.suggestions || [],
          source: "code_dev",
        };
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_dev_status",
      description:
        "【排障】写码车道状态。用户说「写码」时禁止调用；请用 mes_code_dev_begin。",
      parameters: {},
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: cdPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute() {
        return await e.runEngine(["code-dev-status"]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_dev_check",
      description:
        "【排障】校验工程路径。用户说「写码」时禁止调用；请用 mes_code_dev_begin。",
      parameters: {
        workspace: {
          type: "string",
          required: true,
          description: "本机工程绝对路径",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: cdPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await e.runEngine(["code-dev-check", workspace]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_dev_start",
      description:
        "仅当用户已在工具卡确认并拿到 HITL nonce 时使用。日常请用 mes_code_dev_begin；禁止仅凭 confirmed=true 开工。",
      parameters: {
        workspace: {
          type: "string",
          required: true,
          description: "本机工程绝对路径",
        },
        message: {
          type: "string",
          required: true,
          description: "已确认的改码需求摘要",
        },
        nonce: {
          type: "string",
          required: true,
          description: "确认卡签发的一次性 HITL nonce（须来自 UI，不可伪造）",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: cdPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const nonce = String(args.nonce || "").trim();
        if (!nonce) {
          return {
            ok: false,
            detail: "缺少 HITL nonce：请让用户在写码确认卡点击确认",
            reply: "请先完成写码确认卡，再启动。",
          };
        }
        const workspace = String(args.workspace || "").trim();
        const message = String(args.message || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        if (!message) return { ok: false, detail: "message 不能为空" };
        return await e.runEngine(
          ["code-dev-confirm", workspace, message, "nonce=" + nonce],
          t,
        );
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_dev_job",
      description: "查询本机写码任务状态。示例：「查一下任务 ldj-xxxx」。",
      parameters: {
        job_id: { type: "string", required: true, description: "任务 id" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: cdPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await e.runEngine(["code-dev-job", job_id]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_dev_cancel",
      description: "取消进行中的本机写码任务。",
      parameters: {
        job_id: { type: "string", required: true, description: "任务 id" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: cdPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await e.runEngine(["code-dev-cancel", job_id]);
      },
    }),
  );
}

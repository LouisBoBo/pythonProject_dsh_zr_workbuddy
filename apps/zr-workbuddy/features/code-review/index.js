/**
 * 热插拔 feature：code-review（本机目录直读审码）
 * 无 import npm；算数在 engine/app/code_review。
 *
 * 主聊天 HITL：begin 无路径时返回 code_review_ui + presentationMeta，
 * 由 mes-bridge 客户端 tool.call.toolview 在 DSH 主对话工具卡内渲染「选目录+勾选文件」。
 * 禁止依赖浮层面板 / ask_user_question 答题壳。
 */
export const name = "code-review";
export const inject = ["tools"];

const OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: true,
  properties: {
    ok: { type: "boolean" },
    reply: { type: "string" },
    detail: { oneOf: [{ type: "string" }, { type: "null" }] },
    report_id: { oneOf: [{ type: "string" }, { type: "null" }] },
    findings: {
      oneOf: [
        { type: "array", items: { type: "object", additionalProperties: true } },
        { type: "null" },
      ],
    },
    files_reviewed: {
      oneOf: [{ type: "array", items: { type: "string" } }, { type: "null" }],
    },
  },
};

function eng(ctx) {
  return ctx.get("mesEngine");
}

function timeoutOf(e) {
  return Math.max(e.TIMEOUT_MS || 60000, 300000);
}

function crPresentationMeta(_args, value) {
  if (value && value.code_review_ui) {
    return { wb: { t: "cr-pick", ui: value.code_review_ui } };
  }
  if (value && value.report_id) {
    return { wb: { t: "cr-done", report_id: value.report_id } };
  }
  return { wb: { t: "cr-none" } };
}

export function apply(ctx) {
  const e = eng(ctx);
  if (!e) {
    console.error("[code-review] mesEngine 未提供：请启用 mes-bridge");
    return;
  }
  const t = timeoutOf(e);

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_review_begin",
      description:
        "【审码主入口】用户说「审核代码 / 审码 / code review」时必须只调本工具。" +
        "未给绝对路径时：返回选目录确认（主聊天工具卡内可选目录并勾选文件），不要再问用户、不要用 ask_user_question、不要 Bash 扫盘。" +
        "若用户已给绝对路径，直接开审（默认抽样）；有 files 则按指定文件审。",
      parameters: {
        local_path: {
          type: "string",
          description: "可选：本机工程绝对路径；省略则弹出主聊天选目录/文件卡",
        },
        scope: { type: "string", description: "可选相对子路径" },
        focus: { type: "string", description: "可选审查重点" },
        files: {
          type: "string",
          description: "可选：逗号分隔相对路径；省略则默认抽样",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: crPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const local_path = String((args && args.local_path) || "").trim();
        const scope = String((args && args.scope) || "").trim();
        const focus = String((args && args.focus) || "").trim();

        // 企业硬门禁：begin 一律出选目录卡，禁止 Agent 带路径直跑
        const pickCmd = ["code-review-pick"];
        if (local_path) pickCmd.push("workspace=" + local_path);
        if (scope) pickCmd.push("scope=" + scope);
        if (focus) pickCmd.push("focus=" + focus);
        const pick = await e.runEngine(pickCmd);
        if (!pick || !pick.ok) return pick;
        const ui = pick.code_review_ui || null;
        return {
          ok: true,
          reply:
            "请在**上方工具卡**中选择本机工程目录，再勾选要审的文件，然后点「开始审核」。" +
            "（不要在聊天里再发路径直跑；须经工具卡签发 path_ticket。）",
          detail: "await_toolview_pick",
          suggestions: pick.suggestions || [],
          workspace: pick.workspace || local_path || "",
          scope: scope || (pick.scope || ""),
          focus: focus || (pick.focus || ""),
          code_review_ui: ui,
          source: "code_review",
        };
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_review_status",
      description:
        "【排障】审码车道状态。用户说「审核代码」时禁止调用；请用 mes_code_review_begin。",
      parameters: {},
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: crPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute() {
        return await e.runEngine(["code-review-status"]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_review_check",
      description:
        "【排障】校验路径。用户说「审核代码」时禁止调用；请用 mes_code_review_begin。",
      parameters: {
        local_path: { type: "string", required: true, description: "本机路径" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: crPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const local_path = String(args.local_path || "").trim();
        if (!local_path) return { ok: false, detail: "local_path 不能为空" };
        return await e.runEngine(["code-review-check", local_path]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_review_list",
      description:
        "【排障】列可审文件。日常选文件请在主聊天工具卡中勾选。",
      parameters: {
        local_path: { type: "string", required: true, description: "工程路径" },
        scope: { type: "string", description: "可选子路径" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: crPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const local_path = String(args.local_path || "").trim();
        if (!local_path) return { ok: false, detail: "local_path 不能为空" };
        const scope = String(args.scope || "").trim();
        const cmd = scope
          ? ["code-review-list", local_path, "scope=" + scope]
          : ["code-review-list", local_path];
        return await e.runEngine(cmd);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_review_run",
      description:
        "仅当已有列文件签发的 path_ticket 时使用。用户只说「审核代码」时请用 mes_code_review_begin。",
      parameters: {
        local_path: { type: "string", required: true, description: "工程路径" },
        path_ticket: {
          type: "string",
          required: true,
          description: "list/check 返回的 path_ticket",
        },
        scope: { type: "string", description: "子路径" },
        files: { type: "string", description: "逗号分隔相对路径" },
        focus: { type: "string", description: "审查重点" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: crPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const local_path = String(args.local_path || "").trim();
        const path_ticket = String(args.path_ticket || "").trim();
        if (!local_path) return { ok: false, detail: "local_path 不能为空" };
        if (!path_ticket) {
          return {
            ok: false,
            detail: "缺少 path_ticket：请先在工具卡列文件或走 mes_code_review_begin",
          };
        }
        const cmd = ["code-review-run", local_path, "path_ticket=" + path_ticket];
        const scope = String(args.scope || "").trim();
        const focus = String(args.focus || "").trim();
        const files = String(args.files || "").trim();
        if (scope) cmd.push("scope=" + scope);
        if (focus) cmd.push("focus=" + focus);
        if (files) cmd.push("files=" + files);
        return await e.runEngine(cmd, t);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_review_report",
      description: "按 report_id 查已保存审码报告。",
      parameters: {
        report_id: { type: "string", required: true, description: "如 cr-…" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: crPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const report_id = String(args.report_id || "").trim();
        if (!report_id) return { ok: false, detail: "report_id 不能为空" };
        return await e.runEngine(["code-review-report", report_id]);
      },
    }),
  );
}

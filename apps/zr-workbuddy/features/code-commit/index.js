/**
 * 热插拔 feature：code-commit（人触发提交）
 * 无 import npm；算数在 engine/app/code_commit。
 *
 * 主聊天 HITL：begin 无路径时返回 code_commit_ui + presentationMeta，
 * 由 mes-bridge tool.call.toolview 在主对话工具卡内：选目录 → 勾选文件 → 门禁 → 确认 commit/push。
 * 禁止依赖浮层面板 / ask_user_question 答题壳。
 */
export const name = "code-commit";
export const inject = ["tools"];

const OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: true,
  properties: {
    ok: { type: "boolean" },
    reply: { type: "string" },
    detail: { oneOf: [{ type: "string" }, { type: "null" }] },
    job_id: { oneOf: [{ type: "string" }, { type: "null" }] },
    can_commit: { oneOf: [{ type: "boolean" }, { type: "null" }] },
    findings: {
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

function ccPresentationMeta(_args, value) {
  if (value && value.code_commit_ui) {
    const kind = value.code_commit_ui.kind || "pick";
    return { wb: { t: "cc-" + kind, ui: value.code_commit_ui } };
  }
  if (value && value.job_id && value.can_commit) {
    return { wb: { t: "cc-gate-ok", job_id: value.job_id } };
  }
  return { wb: { t: "cc-none" } };
}

export function apply(ctx) {
  const e = eng(ctx);
  if (!e) {
    console.error("[code-commit] mesEngine 未提供：请启用 mes-bridge");
    return;
  }
  const t = timeoutOf(e);

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_begin",
      description:
        "【提交主入口】用户说「提交代码 / 帮我提交 / 提交门禁」时必须只调本工具。" +
        "未给绝对路径时：返回选目录确认（主聊天工具卡内可选目录、勾选文件、门禁与确认推送），" +
        "不要再问用户、不要用 ask_user_question、不要 Bash 扫盘。" +
        "若用户已给绝对路径，可直接跑门禁（仍建议让用户在卡里确认）。",
      parameters: {
        workspace: {
          type: "string",
          description: "可选：本机 Git 工程绝对路径；省略则弹出主聊天选目录/文件卡",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const workspace = String((args && args.workspace) || "").trim();
        if (!workspace) {
          const pick = await e.runEngine(["code-commit-pick"]);
          if (!pick || !pick.ok) return pick;
          const ui = pick.code_commit_ui || null;
          return {
            ok: true,
            reply:
              "请在**上方工具卡**中选择本机 Git 工程目录，勾选要提交的文件，" +
              "跑门禁通过后再确认才会 commit/push（可推远程）。",
            detail: "await_toolview_pick",
            suggestions: pick.suggestions || [],
            workspace: pick.workspace || "",
            code_commit_ui: ui,
            source: "code_commit",
          };
        }
        // 已有路径：仍返回带预填的 pick 卡，由工具卡完成选文件/门禁/确认（避免答题壳）
        const pick = await e.runEngine([
          "code-commit-pick",
          "workspace=" + workspace,
        ]);
        if (!pick || !pick.ok) return pick;
        const ui = pick.code_commit_ui || null;
        if (ui && workspace) ui.workspace = workspace;
        return {
          ok: true,
          reply:
            "已带入目录 `" +
            workspace +
            "`。请在上方工具卡勾选文件并完成门禁与确认。",
          detail: "await_toolview_pick",
          workspace,
          code_commit_ui: ui,
          source: "code_commit",
        };
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_start",
      description:
        "仅当已有明确 workspace 且只需门禁时使用。日常请用 mes_code_commit_begin。",
      parameters: {
        workspace: {
          type: "string",
          required: true,
          description: "本机 Git 工程绝对路径",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await e.runEngine(["code-commit-start", workspace], t);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_status",
      description:
        "【排障】提交车道状态。用户说「提交代码」时禁止调用；请用 mes_code_commit_begin。",
      parameters: {},
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute() {
        return await e.runEngine(["code-commit-status"]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_check",
      description:
        "【排障】校验 Git 路径。用户说「提交代码」时禁止调用；请用 mes_code_commit_begin。",
      parameters: {
        workspace: {
          type: "string",
          required: true,
          description: "本机 Git 工程绝对路径",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await e.runEngine(["code-commit-check", workspace]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_prepare",
      description: "【排障】只列待提交文件。日常选文件请在主聊天工具卡勾选。",
      parameters: {
        workspace: {
          type: "string",
          required: true,
          description: "本机 Git 工程绝对路径",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await e.runEngine(["code-commit-prepare", workspace]);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_prepare_fix",
      description: "门禁阻断后：生成写码修复数据。用户说「修复这些问题」时用。",
      parameters: {
        workspace: { type: "string", description: "可选工程路径" },
        job_id: { type: "string", description: "可选门禁任务 id" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const cmd = ["code-commit-prepare-fix"];
        const ws = String(args.workspace || "").trim();
        const jid = String(args.job_id || "").trim();
        if (ws) cmd.push("workspace=" + ws);
        if (jid) cmd.push("job_id=" + jid);
        return await e.runEngine(cmd);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_confirm",
      description:
        "备用：仅工具卡未能确认、且已持有 UI 签发的 HITL nonce 时使用。日常勿单独调用；禁止仅凭 confirmed=true。",
      parameters: {
        job_id: { type: "string", required: true, description: "门禁任务 id" },
        message: { type: "string", required: true, description: "中文提交说明" },
        push: { type: "boolean", description: "是否 push" },
        decision: { type: "string", description: "approve 或 reject" },
        nonce: {
          type: "string",
          required: true,
          description: "确认卡签发的 HITL nonce",
        },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const nonce = String(args.nonce || "").trim();
        if (!nonce) {
          return { ok: false, detail: "缺少 HITL nonce：请在提交确认卡操作" };
        }
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        const message = String(args.message || "").trim();
        const decision = String(args.decision || "approve").trim() || "approve";
        const cmd = [
          "code-commit-confirm",
          job_id,
          "message=" + message,
          "decision=" + decision,
          "nonce=" + nonce,
        ];
        if (args.push === true || args.push === false) {
          cmd.push("push=" + (args.push ? "true" : "false"));
        }
        return await e.runEngine(cmd, t);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_push_retry",
      description: "本地已 commit、仅 push 失败时重试推送。",
      parameters: {
        job_id: { type: "string", required: true, description: "任务 id" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: t,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await e.runEngine(["code-commit-push-retry", job_id], t);
      },
    }),
  );

  ctx.tools.register(
    e.defineTool({
      name: "mes_code_commit_job",
      description: "按 job_id 查询提交门禁任务状态。",
      parameters: {
        job_id: { type: "string", required: true, description: "任务 id" },
      },
      output: {
        schema: OUTPUT_SCHEMA,
        render: e.resultRender,
        presentationMeta: ccPresentationMeta,
      },
      timeoutMs: e.TIMEOUT_MS || 60000,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await e.runEngine(["code-commit-job", job_id]);
      },
    }),
  );
}

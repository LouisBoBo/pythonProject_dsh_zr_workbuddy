/**
 * 热插拔 feature：code-commit（人触发提交 P0-2）
 * 无 import npm；算数在 engine/app/code_commit。
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
    findings: { oneOf: [{ type: "array", items: { type: "object", additionalProperties: true } }, { type: "null" }] },
  },
};

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[code-commit] mesEngine 未提供：请启用 mes-bridge");
    return;
  }

  const timeoutMs = Math.max(eng.TIMEOUT_MS || 60000, 180000);

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_status",
      description:
        "ZR-WorkBuddy：查看人触发提交车道是否就绪（开关、默认推送、工作分支）。" +
        "示例：「提交功能开了吗」「code commit 状态」。",
      parameters: {},
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute() {
        return await eng.runEngine(["code-commit-status"]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_check",
      description:
        "ZR-WorkBuddy：校验本机绝对路径是否为可提交的 Git 工程目录。" +
        "示例：「检查 /Users/me/proj 能不能提交」。",
      parameters: {
        workspace: {
          type: "string",
          required: true,
          description: "本机 Git 工程绝对路径",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await eng.runEngine(["code-commit-check", workspace]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_prepare",
      description:
        "ZR-WorkBuddy：列出待提交业务源码（Git dirty 优先），不跑门禁、不 commit。" +
        "示例：「准备提交 /Users/me/proj」。",
      parameters: {
        workspace: { type: "string", required: true, description: "本机 Git 工程绝对路径" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await eng.runEngine(["code-commit-prepare", workspace]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_start",
      description:
        "ZR-WorkBuddy：启动提交门禁（列出文件 + P0/P1 批审）。通过后仍须人确认才会 commit。" +
        "不要用本工具代替确认提交。示例：「对 /Users/me/proj 做提交门禁」。",
      parameters: {
        workspace: { type: "string", required: true, description: "本机 Git 工程绝对路径" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await eng.runEngine(["code-commit-start", workspace], timeoutMs);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_prepare_fix",
      description:
        "ZR-WorkBuddy：根据最近一次提交门禁阻断，生成写码修复确认卡数据（不自动开工）。" +
        "用户说「修复这些问题」时优先用本能力。示例：「按门禁修复」「修复这些问题」。",
      parameters: {
        workspace: { type: "string", description: "可选：本机工程路径" },
        job_id: { type: "string", description: "可选：门禁任务 id，如 cc-…" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const cmd = ["code-commit-prepare-fix"];
        const ws = String(args.workspace || "").trim();
        const jid = String(args.job_id || "").trim();
        if (ws) cmd.push("workspace=" + ws);
        if (jid) cmd.push("job_id=" + jid);
        return await eng.runEngine(cmd);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_confirm",
      description:
        "ZR-WorkBuddy：人确认后执行 git commit（可选 push）。须已有门禁通过的 job_id；" +
        "提交说明须含中文。禁止在未获用户确认时调用。示例：用户点确认卡后。",
      parameters: {
        job_id: { type: "string", required: true, description: "门禁任务 id，如 cc-…" },
        message: { type: "string", required: true, description: "中文提交说明" },
        push: {
          type: "boolean",
          description: "是否推送远程；默认跟配置（通常 true）",
        },
        decision: {
          type: "string",
          description: "approve（默认）或 reject",
        },
        confirmed: {
          type: "boolean",
          required: true,
          description: "必须为 true，表示用户已在 UI 确认",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs,
      async execute(args) {
        if (!args.confirmed) {
          return { ok: false, detail: "须 confirmed=true（用户已确认）" };
        }
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        const message = String(args.message || "").trim();
        const decision = String(args.decision || "approve").trim() || "approve";
        const cmd = ["code-commit-confirm", job_id, "message=" + message, "decision=" + decision];
        if (args.push === true || args.push === false) {
          cmd.push("push=" + (args.push ? "true" : "false"));
        }
        return await eng.runEngine(cmd, timeoutMs);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_push_retry",
      description:
        "ZR-WorkBuddy：本地已 commit 但 push 失败时，仅重试推送（不重新 commit）。" +
        "示例：用户点「重试推送」或说「再推一次」。",
      parameters: {
        job_id: { type: "string", required: true, description: "提交任务 id，如 cc-…" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await eng.runEngine(["code-commit-push-retry", job_id], timeoutMs);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_commit_job",
      description: "ZR-WorkBuddy：按 job_id 查询提交门禁/提交任务。示例：「查提交任务 cc-xxxx」。",
      parameters: {
        job_id: { type: "string", required: true, description: "任务 id，如 cc-…" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await eng.runEngine(["code-commit-job", job_id]);
      },
    }),
  );
}

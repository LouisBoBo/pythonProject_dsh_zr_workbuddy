/**
 * 热插拔 feature：code-dev（本机 Cursor Local 写码）
 * 无 import npm；能力经 ctx.get('mesEngine')；算数在 engine/app/code_dev。
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

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[code-dev] mesEngine 未提供：请启用 mes-bridge");
    return;
  }

  const timeoutMs = Math.max(eng.TIMEOUT_MS || 60000, 120000);

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_dev_status",
      description:
        "ZR-WorkBuddy：查看本机 Cursor Local 写码是否就绪（开关、API Key、cursor-sdk）。" +
        "示例：「本机写码可用吗」「Cursor 写码状态」。",
      parameters: {},
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute() {
        return await eng.runEngine(["code-dev-status"]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_dev_check",
      description:
        "ZR-WorkBuddy：校验本机工程绝对路径是否可作为写码目标目录。" +
        "示例：「检查一下 /Users/me/proj 能不能写码」。",
      parameters: {
        workspace: {
          type: "string",
          required: true,
          description: "本机工程绝对路径，例如 /Users/你/项目",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        return await eng.runEngine(["code-dev-check", workspace]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_dev_start",
      description:
        "ZR-WorkBuddy：仅在用户已明确确认写码方案后启动 Cursor Local 任务。" +
        "聊天面板应走确认卡；Agent 调用时必须 confirmed=true。" +
        "禁止在需求未确认时直接调用。启动后用 mes_code_dev_job 查进度。不会自动 commit。",
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
        confirmed: {
          type: "boolean",
          required: true,
          description: "必须为 true，表示用户已确认写码确认卡/方案",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs,
      async execute(args) {
        const workspace = String(args.workspace || "").trim();
        const message = String(args.message || "").trim();
        if (!args.confirmed) {
          return {
            ok: false,
            detail: "未确认：请先让用户确认写码方案（confirmed=true）后再启动",
            reply: "请先完成需求确认卡，再启动写码。",
          };
        }
        if (!workspace) return { ok: false, detail: "workspace 不能为空" };
        if (!message) return { ok: false, detail: "message 不能为空" };
        return await eng.runEngine(["code-dev-start", workspace, message]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_dev_job",
      description:
        "ZR-WorkBuddy：查询本机写码任务状态与同步结果。示例：「查一下任务 ldj-xxxx」。",
      parameters: {
        job_id: { type: "string", required: true, description: "任务 id，如 ldj-…" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await eng.runEngine(["code-dev-job", job_id]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_dev_cancel",
      description: "ZR-WorkBuddy：取消进行中的本机写码任务。",
      parameters: {
        job_id: { type: "string", required: true, description: "任务 id" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const job_id = String(args.job_id || "").trim();
        if (!job_id) return { ok: false, detail: "job_id 不能为空" };
        return await eng.runEngine(["code-dev-cancel", job_id]);
      },
    }),
  );
}

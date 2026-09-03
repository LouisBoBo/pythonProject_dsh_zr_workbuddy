/**
 * 热插拔 feature：code-review（本机目录直读审码 P0-3）
 * 无 import npm；算数在 engine/app/code_review。
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
    findings: { oneOf: [{ type: "array", items: { type: "object", additionalProperties: true } }, { type: "null" }] },
    files_reviewed: { oneOf: [{ type: "array", items: { type: "string" } }, { type: "null" }] },
  },
};

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[code-review] mesEngine 未提供：请启用 mes-bridge");
    return;
  }

  const timeoutMs = Math.max(eng.TIMEOUT_MS || 60000, 180000);

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_review_status",
      description:
        "ZR-WorkBuddy：查看本机目录审码是否就绪（审码车道开关、LLM、读取上限）。" +
        "示例：「审码功能开了吗」「code review 状态」。",
      parameters: {},
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute() {
        return await eng.runEngine(["code-review-status"]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_review_check",
      description:
        "ZR-WorkBuddy：校验本机工程绝对路径是否可作为审码目标（可读、非敏感系统路径）。" +
        "示例：「检查一下 /Users/me/proj 能不能审码」。",
      parameters: {
        local_path: {
          type: "string",
          required: true,
          description: "本机工程绝对路径或单个源码文件路径",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const local_path = String(args.local_path || "").trim();
        if (!local_path) return { ok: false, detail: "local_path 不能为空" };
        return await eng.runEngine(["code-review-check", local_path]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_review_list",
      description:
        "ZR-WorkBuddy：列出本机工程内可审阅的源码文件（后缀白名单，跳过 node_modules 等）。" +
        "示例：「列出 /Users/me/proj 下 frontend 目录有哪些可审文件」。",
      parameters: {
        local_path: { type: "string", required: true, description: "本机工程绝对路径" },
        scope: {
          type: "string",
          description: "可选相对子路径，如 frontend/src/views/reports",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const local_path = String(args.local_path || "").trim();
        if (!local_path) return { ok: false, detail: "local_path 不能为空" };
        const scope = String(args.scope || "").trim();
        const cmd = scope ? ["code-review-list", local_path, "scope=" + scope] : ["code-review-list", local_path];
        return await eng.runEngine(cmd);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_review_run",
      description:
        "ZR-WorkBuddy：对本机工程直读文件并出 LLM 审查报告（非 Git diff、非 VS Code）。" +
        "可指定 scope 子目录、files 文件列表、focus 审查重点。" +
        "示例：「审一下 /Users/me/proj 的 reports 模块有没有安全问题」。",
      parameters: {
        local_path: { type: "string", required: true, description: "本机工程绝对路径" },
        scope: { type: "string", description: "相对子路径，如 backend/app/routers" },
        files: {
          type: "string",
          description: "可选，逗号或换行分隔的相对文件路径；留空则按优先级采样",
        },
        focus: {
          type: "string",
          description: "可选审查重点，如「SQL 注入」「权限校验缺失」",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs,
      async execute(args) {
        const local_path = String(args.local_path || "").trim();
        if (!local_path) return { ok: false, detail: "local_path 不能为空" };
        const cmd = ["code-review-run", local_path];
        const scope = String(args.scope || "").trim();
        const focus = String(args.focus || "").trim();
        const files = String(args.files || "").trim();
        if (scope) cmd.push("scope=" + scope);
        if (focus) cmd.push("focus=" + focus);
        if (files) cmd.push("files=" + files);
        return await eng.runEngine(cmd, timeoutMs);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_review_report",
      description: "ZR-WorkBuddy：按 report_id 查询已保存的本机审码报告。示例：「查审码报告 cr-xxxx」。",
      parameters: {
        report_id: { type: "string", required: true, description: "报告 id，如 cr-…" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const report_id = String(args.report_id || "").trim();
        if (!report_id) return { ok: false, detail: "report_id 不能为空" };
        return await eng.runEngine(["code-review-report", report_id]);
      },
    }),
  );
}

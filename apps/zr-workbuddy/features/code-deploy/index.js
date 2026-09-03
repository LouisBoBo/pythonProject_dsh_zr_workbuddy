/**
 * 热插拔 feature：code-deploy（按插件增量部署）
 * 无 import npm；算数在 engine/app/code_deploy。
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
    units: { oneOf: [{ type: "array", items: { type: "object", additionalProperties: true } }, { type: "null" }] },
  },
};

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[code-deploy] mesEngine 未提供：请启用 mes-bridge");
    return;
  }

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_deploy_status",
      description:
        "ZR-WorkBuddy：查看按插件增量部署车道是否就绪（开关、SSH、环境白名单）。" +
        "示例：「部署功能开了吗」。",
      parameters: {},
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute() {
        return await eng.runEngine(["code-deploy-status"]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_deploy_prepare",
      description:
        "ZR-WorkBuddy：准备部署确认卡。首次默认全量；也可增量（按 Git diff 算插件）。不执行 rsync。" +
        "示例：「准备部署到预发」「全量部署」。",
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
          description: "强制指定单元，如 feature:code-commit、feature:code-dev",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: Math.max(eng.TIMEOUT_MS || 60000, 120000),
      async execute(args) {
        const parts = ["code-deploy-prepare"];
        const ws = String(args.workspace || "").trim();
        if (ws) parts.push(ws);
        const env = String(args.env || "").trim();
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
        return await eng.runEngine(parts);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_code_deploy_confirm",
      description:
        "ZR-WorkBuddy：人确认后 SSH/rsync。mode=full 全量；incremental 按勾选插件。必须 confirmed=true；模型不得代确认。",
      parameters: {
        job_id: { type: "string", required: true, description: "prepare 返回的 job_id" },
        confirmed: { type: "boolean", required: true, description: "必须为 true" },
        decision: { type: "string", description: "approve|reject" },
        mode: { type: "string", description: "full|incremental" },
        unit_ids: {
          type: "array",
          items: { type: "string" },
          description: "确认时勾选的单元 id；全量可不传",
        },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: Math.max(eng.TIMEOUT_MS || 60000, 300000),
      async execute(args) {
        if (!args.confirmed) {
          return { ok: false, detail: "须人确认：confirmed=true", reply: "未确认，未执行部署" };
        }
        const jobId = String(args.job_id || "").trim();
        if (!jobId) return { ok: false, detail: "job_id 不能为空" };
        const parts = ["code-deploy-confirm", jobId];
        const decision = String(args.decision || "approve").trim();
        parts.push("--decision", decision);
        const mode = String(args.mode || "").trim();
        if (mode) parts.push("--mode", mode);
        const ids = Array.isArray(args.unit_ids) ? args.unit_ids : [];
        for (const id of ids) {
          const s = String(id || "").trim();
          if (s) parts.push("--unit", s);
        }
        return await eng.runEngine(parts);
      },
    }),
  );
}

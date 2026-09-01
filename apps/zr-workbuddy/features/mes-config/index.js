/**
 * 热插拔 feature：mes_config / mes_status
 */
export const name = "mes-config";
export const inject = ["tools"];

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[mes-config] mesEngine 未提供：请启用 mes-bridge");
    return;
  }

  ctx.tools.register(
    eng.defineTool({
      name: "mes_config",
      description: "MES 连接配置：action=test-mes | test-llm | 留空查看状态。",
      parameters: {
        action: { type: "string", description: "test-mes | test-llm | 空" },
      },
      output: {
        schema: { type: "object", additionalProperties: true },
        render: eng.resultRender,
      },
      timeoutMs: 40000,
      async execute(args) {
        const action = String(args.action || "").trim();
        if (action === "test-mes") return await eng.runEngine(["config-test-mes"]);
        if (action === "test-llm") return await eng.runEngine(["config-test-llm"]);
        return await eng.runEngine(["status"]);
      },
    }),
  );

  ctx.tools.register(
    eng.defineTool({
      name: "mes_status",
      description: "MES / LLM / 网络连接状态。",
      parameters: {},
      output: {
        schema: { type: "object", additionalProperties: true },
        render: eng.resultRender,
      },
      timeoutMs: 15000,
      async execute() {
        return await eng.runEngine(["status"]);
      },
    }),
  );
}

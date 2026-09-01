/**
 * 热插拔 feature：mes_ask
 * 无 import；能力经 ctx.get('mesEngine') 注入（由 mes-bridge provide）。
 * inject 必须含 attachments：出图时 attachChart → saveImage，否则 Cordis 会抛
 * cannot get property "attachments" without inject（无图查询不会踩到）。
 */
export const name = "mes-ask";
export const inject = ["tools", "attachments"];

const OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: true,
  properties: {
    ok: { type: "boolean" },
    reply: { type: "string" },
    chart: { oneOf: [{ type: "string" }, { type: "null" }] },
    chart_attachment: { oneOf: [{ type: "object", additionalProperties: true }, { type: "null" }] },
    table: { oneOf: [{ type: "array", items: { type: "object", additionalProperties: true } }, { type: "null" }] },
    note: { oneOf: [{ type: "string" }, { type: "null" }] },
    source: { oneOf: [{ type: "string" }, { type: "null" }] },
    data_source: { oneOf: [{ type: "string" }, { type: "null" }] },
    detail: { oneOf: [{ type: "string" }, { type: "null" }] },
    intent: { oneOf: [{ type: "object", additionalProperties: true }, { type: "null" }] },
  },
};

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[mes-ask] mesEngine 未提供：请启用 mes-bridge");
    return;
  }

  ctx.tools.register(
    eng.defineTool({
      name: "mes_ask",
      description:
        "ZR-WorkBuddy：自然语言查询产量/良率/OEE/缺陷/工单（完工、在制/再制品、总数）等。" +
        "示例：「今日再制品工单有多少个」「分析8月30号良率过低的原因」。",
      parameters: {
        question: { type: "string", required: true, description: "自然语言问题" },
      },
      output: { schema: OUTPUT_SCHEMA, render: eng.resultRender },
      timeoutMs: eng.TIMEOUT_MS || 60000,
      async execute(args) {
        const question = String(args.question || "").trim();
        if (!question) return { ok: false, detail: "问题不能为空" };
        const raw = await eng.runEngine(["ask", question]);
        return await eng.attachChart(ctx, raw);
      },
    }),
  );
}

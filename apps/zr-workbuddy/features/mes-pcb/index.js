/**
 * 热插拔 feature：mes_pcb —— PCB 制造领域专家对话
 * 算数/LLM 在 engine/app/pcb_expert.py（cmd=pcb-ask），本文件只注册 Agent 工具。
 */
export const name = "mes-pcb";
export const inject = ["tools"];

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[mes-pcb] mesEngine 未提供：请启用 mes-bridge");
    return;
  }

  ctx.tools.register(
    eng.defineTool({
      name: "mes_pcb",
      description:
        "【PCB 制造工艺专家，非 MES 查数】回答印制电路板相关的工艺、材料、检测、标准与缺陷问题。" +
        "凡涉及：PCB 工序/流程、叠层、阻抗线宽、钻孔电镀、阻焊丝印、HASL/OSP/ENIG、DFM、" +
        "AOI/飞针/电测分工、IPC 术语、缺陷排障——必须优先调用本工具，不要改用 mes_ask 或泛化对话。" +
        "示例：「PCB 有哪些工序？」「飞针和 AOI 在短路检测上怎么分工？」「Class 2 和 3 孔铜差多少？」",
      parameters: {
        question: {
          type: "string",
          required: true,
          description: "PCB 工艺、材料、检测、标准或缺陷相关的专业问题",
        },
      },
      output: {
        schema: {
          type: "object",
          additionalProperties: true,
          properties: {
            ok: { type: "boolean" },
            reply: { type: "string" },
            detail: { type: "string" },
            source: { type: "string" },
            thinking: { type: "string" },
            note: { type: "string" },
            domain: { type: "string" },
          },
        },
        render: eng.resultRender,
      },
      timeoutMs: 120000,
      async execute(args) {
        const question = String(args.question || "").trim();
        if (!question) return { ok: false, detail: "问题不能为空" };
        return await eng.runEngine(["pcb-ask", question], 120000);
      },
    }),
  );
}

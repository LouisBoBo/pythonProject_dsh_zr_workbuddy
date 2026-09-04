/**
 * 样例第三方 feature（演示安装器；无 npm）。
 * 工具名 mes_sample_ping：探活引擎 status。
 */
export const name = "sample-third-party";
export const inject = ["tools"];

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[sample-third-party] mesEngine 未提供：请启用 mes-bridge（有宿主时）");
    return;
  }

  ctx.tools.register(
    eng.defineTool({
      name: "mes_sample_ping",
      description:
        "样例第三方插件：查询引擎 status。示例：「用样例插件探活一下引擎」。",
      parameters: {},
      output: {
        schema: {
          type: "object",
          additionalProperties: true,
          properties: {
            ok: { type: "boolean" },
            reply: { type: "string" },
            detail: { type: ["string", "null"] },
          },
        },
        render: eng.resultRender,
      },
      timeoutMs: eng.TIMEOUT_MS || 30000,
      async execute() {
        const raw = await eng.runEngine(["status"]);
        if (!raw || raw.ok === false) {
          return {
            ok: false,
            reply: "样例插件：引擎 status 失败",
            detail: (raw && (raw.detail || raw.reply)) || "unknown",
          };
        }
        return {
          ok: true,
          reply: "样例第三方插件工作正常（已调通 runEngine status）",
          detail: null,
        };
      },
    }),
  );
}

# dsh-tools 双实例与「本轮运行失败 reading prepare」

> **状态**：已根治（脚本自动对齐）  
> **相关**：`scripts/check-vendor.sh`、`scripts/plugin.sh`、`scripts/host.sh restart-web`、`plugins/mes-bridge`

---

## 1. 现象

聊天里工具卡（如写码 `mes_code_dev_begin`）**已经出现**，但同轮底部红条：

```text
本轮运行失败
Cannot read properties of undefined (reading 'prepare')
```

右侧常显示 `UNKNOWN`。

易被误判为「Agent 调了 `run_code`」。实际上 **任意工具**（含 `mes_code_dev_begin`）都可能炸。

---

## 2. 根因

1. DSH agent-loop 在记完 tool call（UI 出卡）后调用：

   `ctx.tools[TOOL_RUNTIME_SCHEDULER].prepare(...)`

2. 发布版 `@deepseek-ai/dsh-tools` 里 `TOOL_RUNTIME_SCHEDULER` 使用 **`Symbol(...)`（非 `Symbol.for`）**。  
   进程里若加载 **两份** `dsh-tools`，两份 Symbol 不相等 → `ctx.tools[宿主Symbol]` 为 `undefined` → 读 `.prepare` 报错。

3. 常见双实例来源：市场插件（如 pcb-helper）把 `@deepseek-ai/dsh-tools` 装进  
   `~/.dsh/profiles/web/node_modules/`，盖住宿主包。  
   仓库 `vendor/` 此前已用 `check-vendor.sh` 对齐，**profile 副本原先未管**。

4. `tools.guard` **拦不住**：guard 在 prepare 流水线内部；崩在拿到 scheduler 之前。

---

## 3. 一次性修复

```bash
cd /path/to/DSH-ZR-WorkBuddy
scripts/check-vendor.sh --fix
scripts/plugin.sh --app zr-workbuddy install bridge --restart
# 或仅重启聊天壳：
# scripts/host.sh restart-web
```

验收：

```bash
scripts/check-vendor.sh
# 应看到 vendor 与 profile:web 均为 ✅ realpath 一致

# 宿主日志应有：
# [mes-bridge] TOOL_RUNTIME_SCHEDULER.prepare 可用
```

硬刷新浏览器后再试一句写码/删菜单。

---

## 4. 防复发

| 时机 | 动作 |
|------|------|
| `plugin.sh … install bridge` | `pnpm install` **之后**自动 `check-vendor.sh --fix` |
| `host.sh restart-web` | 启动前自动 `--fix` |
| bridge 启动 | 健康检查：无 `prepare` 则打 FATAL 日志提示执行上述命令 |

人工自检：

```bash
node -e "
const fs=require('fs');
const host=fs.realpathSync(process.env.HOME+'/.nvm/versions/node/v22.23.1/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-tools');
const prof=fs.realpathSync(process.env.HOME+'/.dsh/profiles/web/node_modules/@deepseek-ai/dsh-tools');
console.log('equal', host===prof);
"
```

装完市场插件后又出现同样红条 → 再跑一遍 `check-vendor.sh --fix` + 重启 web。

---

## 5. 与「禁止 run_code」的关系

bridge 仍保留 systemPrompt / `tools.guard` 拒绝 `run_code`（避免 code-mode 旁路）。  
**prepare 红条的硬修复是 realpath 对齐**，不是 guard。

---

## 6. 上游（可选）

宿主源码若改为 `Symbol.for('@deepseek-ai/dsh-tools.scheduler')` 并发布，双副本可共存。  
在此之前：**一进程只能有一份 dsh-tools realpath**。

# 给 Agent / 开发者

**项目：DSH-ZR-WorkBuddy** · **主旨：ZR-WorkBuddy（工作助手）**（不再以「MES 数据分析」为产品定位）。

后续**加功能、写插件必须按本文件**。更白话的目录说明见 `docs/目录结构与用法说明.md`。

---

## 1. 框架 vs 业务（不要写混）

**框架（`scripts/` / `vendor/`）**

- 只负责：脚手架、把 **bridge** 接到 DSH profile、按 `runtime.yaml` 管引擎进程
- **禁止**硬编码：业务 URL、LLM Key、面板文案、具体业务工具名
- 稳定接线：`~/.dsh/link/DSH-ZR-WorkBuddy` → 本仓库；profile 用相对  
  `link:../../link/DSH-ZR-WorkBuddy/apps/zr-workbuddy/...`  
  （业务应用目录为 `zr-workbuddy`。旧 `--app mes-analytics` 由脚本兼容映射。）

**业务（`apps/<应用名>/`）**

| 放哪 | 是什么 |
|---|---|
| `engine/` | 算数真相源（HTTP） |
| `plugins/mes-bridge` | **唯一**常驻 Cordis 包（总管） |
| `plugins/*-runtime` | 库，`dshApp.cordisPlugin: false` |
| `features/*` | **业务功能**（热插拔） |

**铁律：新业务能力只进 `features/`，禁止再往 DSH profile 堆新的正式 Cordis 包。**

### 仓库自定元数据（宿主不识别）

`package.json` 里的 `dshApp: { cordisPlugin, role, deprecated }` 与 `features/*/manifest.json`  
是**本仓库约定**，DSH 宿主源码不读 `dshApp`（仅 `plugin.sh` 的 `is_cordis_plugin` 用来区分常驻包 vs 库）。  
对接 DSH 插件中心时，以真实字段为准：`dsh.client`、`peerDependencies` 等。

### 启停控制面（说清楚）

- **真相源**：`engine/data/plugins.json`（文件）  
- bridge 直接读/写该文件做热插拔；`mes_plugin` enable/disable **不依赖**引擎进程  
- 引擎 `/api/plugins` 是便利写入口（给 `plugin.sh` curl 用），语义上引擎仍是「算数进程」，顺带能改同一份文件  
- 这与 DSH 惯例（loader/config）不同，是本应用有意设计；文档与脚本已按「文件为真相源」实现  

### runtime.yaml 只解析一次

统一实现：`scripts/lib/read_runtime.py`。  
`engine.sh` / `plugin.sh` / `mes-runtime` / `engine/app/runtime_conf.py` 都调用它，改格式只改这一处。

---

## 2. 加功能必须走这条路（写插件规则）

### 2.1 正确流程

```bash
scripts/engine.sh zr-workbuddy ensure
scripts/plugin.sh --app zr-workbuddy new <id> "一句话说明"
# 编辑 apps/zr-workbuddy/features/<id>/index.js 与 manifest.json
# 默认已 enable；约 1s 内热加载，无需重启 DSH
# 注意：改已启用 feature 的 index.js 时，bridge 按 mtime 自动 dispose+reload（约 1 个轮询周期）；
# 也可 mes_plugin action=reload 或 disable→enable
scripts/plugin.sh --app zr-workbuddy features   # 确认状态
```

`<id>` 必须：小写字母开头，仅 `[a-z0-9_-]`。

### 2.2 feature 代码硬性约定

对照现成样板：`features/mes-ask/index.js`。

1. **文件**：每个功能目录必须有 `index.js` + `manifest.json`  
   - 一经放入 `features/<id>/`，引擎 SPA「功能插件」页与 `/api/plugins` **自动列出**（扫描目录，禁止前端写死 id 白名单）  
   - `plugin.sh new` 默认 enable，可在管理页启停  
2. **导出**：`export const name`、`export const inject`、`export function apply(ctx)`  
3. **禁止**在 feature 里 `import` / `require` npm 包（含 `@deepseek-ai/*`、`mes-runtime`）  
   - 一律：`const eng = ctx.get("mesEngine")`；没有就 `return` 并打日志  
4. **inject（Cordis 硬依赖）**  
   - 最低：`["tools"]`  
   - **凡调用 `eng.attachChart(ctx, …)` 出图：必须 `["tools", "attachments"]`**  
   - Cordis 对未 inject 的服务：`ctx.xxx` 会直接抛错（不是 `undefined`）；  
     `mes-runtime.attachChart` 内部只用 `ctx.get("attachments")` 做防御，但 feature 仍须 inject，否则等不到服务挂载  
5. **注册工具**：只用 `eng.defineTool({...})`，`output.render` 用 `eng.resultRender`  
6. **调后厨**：只用 `eng.runEngine(["命令", ...参数])`（走 HTTP `/api/cli`）  
7. **有图**：`return await eng.attachChart(ctx, raw)`（并满足第 4 条 inject）  
8. **副作用必须可卸**：只通过 `ctx.tools.register` / `ctx.on` / `ctx.effect`；  
   禁止模块顶层 `setInterval`、禁止改全局、禁止写死本机绝对路径  
   - **工具清理依赖 Cordis fiber**：`ctx.tools.register` 返回的 disposer 挂在当前 fiber 上；  
     bridge `fiber.dispose()` 时会隐式卸掉该 feature 注册的全部工具。  
     不要自己在模块作用域缓存「全局工具表」绕过 fiber。  
9. **工具名**：全局唯一；本应用建议前缀 `mes_`（如 `mes_ask`），勿与已有工具撞名  
10. **description**：写清能力 + 1～2 个中文示例问法，方便 Agent 选对工具  

### 2.3 什么时候才动 bridge / engine

| 改什么 | 改哪里 | 要不要重启 |
|---|---|---|
| 新工具 / 新业务能力 | `features/<id>/` | **否**（热插拔） |
| 已启用 feature 的 `index.js` | 同目录 | **否**（bridge 按 mtime dispose+`ctx.plugin` 重载） |
| 查数逻辑、意图、业务接口 | `engine/app/*.py` | **只重启引擎**  
  `scripts/engine.sh zr-workbuddy restart` |
| 面板壳、热插拔宿主本身 | `plugins/mes-bridge/` | **重启 DSH**  
  `scripts/plugin.sh --app zr-workbuddy install bridge --restart` |
| 引擎调用封装 | `plugins/mes-runtime/` | 重启 DSH（bridge 依赖它） |

### 2.4 引擎侧加命令时

若 feature 要新 CLI 能力：在 `engine/app/cli_ops.py` 增加命令，并保证：

- `/api/cli` 与 `engine_cli.py` 同一实现（不要只改一处）  
- FastAPI 补齐**中文** `tags` / `summary` / `description`（及参数说明）

### 2.5 扩展功能与第三方（不得推翻架构）

后续加能力**只允许增量**，禁止改动：单 bridge、`plugins.json` 真相源、`read_runtime.py` 唯一解析、  
`cli_ops` 单轨算数、Cordis `ctx.plugin` / fiber 热插拔模型。

**先判类型再动手：**

| 要什么 | 放哪 | 热插拔 | 重启 |
|---|---|---|---|
| 新 Agent 工具 / WorkBuddy 业务能力 | `features/<id>/` | ✅ ~1s | 否 |
| 新查数、意图、业务接口、出图逻辑 | `engine/app/*.py` + `cli_ops` 新命令 | ❌ | 只重启引擎 |
| Node 第三方 npm 库 | `plugins/*-runtime`（封装后经 `mesEngine` 暴露） | ❌ | 改 runtime → 重启 DSH |
| 外部 HTTP / SaaS / 业务 SDK | `engine/app` + `config.yaml` 密钥 | ❌ | 只重启引擎 |
| DSH 全局 Cordis 包（与本应用无关） | profile `cordis.patch.yml`（与 bridge **并列**） | DSH loader | 视 patch |
| WorkBuddy 业务「又一个正式 Cordis 包」 | **禁止** | — | — |

**硬性约束（违反即架构倒退）：**

1. **新 Agent 工具只进 `features/`**  
   - 自建：`plugin.sh new <id>`  
   - 第三方交付：整目录放进 `features/<id>/`（`index.js` + `manifest.json`），再 `enable`  
   - 未来若做 `install-feature`，仍只落地到 `features/`，**不得**变成 profile 新 Cordis 行  

2. **算数只进 `engine/`，经 `runEngine` 暴露**  
   - feature 禁止重复实现分析逻辑；新能力先在 `cli_ops.py` 加命令，feature 只注册工具并 `runEngine`  

3. **feature 禁止 `import` / `require` npm**（含第三方 SDK）  
   - 必须用的 Node 库：封装进 `mes-runtime`（或 bridge 面板专用逻辑），经 `ctx.get("mesEngine")` 调用  

4. **密钥、URL、Token 只进 `engine/config/config.yaml`**  
   - 禁止写进 feature、README 示例、manifest  

5. **DSH 全局第三方插件可以装，但和 ZR-WorkBuddy（`zr-workbuddy` 应用目录）分工**  
   - profile 可并列安装其它 Cordis 包（文件、浏览器等 DSH 生态能力）  
   - **禁止**把 WorkBuddy 业务能力再做成 profile 正式包或第二个 bridge  

6. **不动架构骨架**  
   - 不新增常驻 Cordis 包（唯一 bridge 例外已存在）  
   - 不另造启停机制（真相源仍是 `plugins.json` + `plugins_store` flock）  
   - 不另造 runtime 解析、不另造 HTTP 鉴权协议  
   - 不在 Node 里 `spawn uvicorn`（一律 `engine.sh ensure`）  

7. **收第三方 WorkBuddy feature 时的验收**  
   - 目录结构 + Cordis 导出 + inject 规则 + 工具名唯一 + 可 dispose  
   - 若需新后端能力：同时提供或合并 `cli_ops` 命令，不得只在 Node 侧私接业务系统  

**与 DSH 动态插件（`cordis_define` / `cordis_run`）的关系：**  
那是 DSH 会话内 Agent 临时写插件的路径，**不是**本仓库 `features/` 的替代；  
第三方 WorkBuddy 业务交付仍按 `features/` 目录约定，不混用两条链路。

---

## 3. 写码通用规则

- **密钥**：只写 `engine/config/config.yaml`（gitignore）；提交用 `config.example.yaml`  
- **端口**：只写 `engine/config/runtime.yaml`；不要在 feature 里写死 `8000`  
- **中文文档**：凡新增/改动后端 HTTP 接口，必须中文 tags/summary/description  
- **少造轮子**：能 `runEngine` 解决的，不要在 Node 里再抄一份分析逻辑  
- **提交前**：`scripts/check-secrets.sh`；相关改动跑 `scripts/test.sh zr-workbuddy`  
- **别改** `vendor/` 版本除非有明确兼容理由，并写进说明  

---

## 4. 风险点（必看，防踩坑）

1. **又往 profile `install` 一个正式包**  
   → 破坏「单 bridge」模型，热插拔失效，还要重启。功能请放 `features/`。

2. **feature 里 `import` 了 npm**  
   → 动态 `import(文件)` 时 Node 解析不到依赖，加载直接挂，工具不会出现。

3. **引擎没起来就测工具**  
   → `runEngine` 失败。先：`scripts/engine.sh zr-workbuddy ensure`。

4. **改了 Python 却只刷新页面**  
   → 引擎是独立进程，必须 `engine.sh … restart`。

5. **工具名撞车或改名不通知**  
   → Agent 调错或调不到；改名前先 `mes_plugin` / `features` 看清单。

6. **在 feature 顶层开定时器 / 写全局状态**  
   → `disable` 后可能泄漏或行为诡异；只挂在 `apply(ctx)` 的 Cordis 生命周期上。

7. **把密钥写进 feature / README / 示例代码**  
   → 泄露；一律进 `config.yaml`。

8. **硬编码本机绝对路径**（如 `/Users/xxx/...`）  
   → 换机器全挂；用相对路径或 `mesEngine` / `runtime.yaml`。

9. **只改 `/api/chat` 或只改 CLI**  
   → 面板和 Agent 行为不一致；统一改 `cli_ops.py`。

10. **以为改 `plugins.json` 要重启 DSH**  
    → 不必；bridge 约 1s 轮询。若一直不生效：看引擎是否在跑、id 是否与目录名一致、feature 是否语法错误（看 DSH 终端日志）。

11. **新建 feature 目录名和 `export const name`、工具 `name` 混用**  
    → 目录名 = enable/disable 的 id；工具 `name` 是 Agent 调用名；manifest 的 id 与目录名保持一致。

12. **客户端面板壳不可热卸**  
    → 面板在 bridge 里常驻。「热插拔」仅指 **Agent 工具 / features**，不要说成「一切 UI 都可热插拔」。

13. **坏 feature 拖累邻居（已修）**  
    → bridge 已按单 feature try/catch；失败会标 `live=error`，同轮继续加载其它功能。

14. **出图查询报 cannot get property "attachments" without inject**  
    → feature 调了 `attachChart` 但 `inject` 只有 `["tools"]`。  
    改为 `["tools", "attachments"]`；且代码里用 `ctx.get("attachments")`，不要写 `ctx.attachments`。  
    无图查询不会触发，容易误判为「功能正常」。

15. **cordis.patch 里用 npm 全名当 id 的 `disabled: true`**  
    → insert 的 id 是短名 `dsh-mes-bridge`，全名匹配不到 → 启动 not-found 警告，看起来像被禁用。删掉该类垃圾行。

16. **引擎 host 改成非回环 / 自造鉴权 token**  
    → 本应用约定只绑 `127.0.0.1`，不另造 HTTP 鉴权协议。需要暴露时先走系统层网络隔离，不要在业务里发明 token 头。

17. **在 Node 里直接 `spawn uvicorn`**  
    → 与 `engine.sh ensure` 抢端口。一律 `scripts/engine.sh <app> ensure`（mes-runtime 已如此）。

---

## 5. 日常命令（写全）

```bash
scripts/engine.sh zr-workbuddy ensure
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy enable mes-ask
scripts/plugin.sh --app zr-workbuddy disable mes-config
scripts/plugin.sh --app zr-workbuddy new report "报表"
scripts/test.sh zr-workbuddy
scripts/check-secrets.sh
scripts/check-vendor.sh
```

仅 bridge 首次 / 升级：

```bash
scripts/plugin.sh --app zr-workbuddy install bridge --restart
```

---

## 6. FastAPI

改接口时补中文 `tags` / `summary` / `description`。

## 7. 文档

- 大白话用法：`docs/目录结构与用法说明.md`  
- 本文：写码与写插件的强制规则 + 风险点

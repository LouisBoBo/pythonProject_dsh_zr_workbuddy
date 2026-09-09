# Deep Agents 与 DSH 全方位技术选型对比方案

> **状态**：已定稿（基于两仓源码精读，可立项引用）  
> **日期**：2026-09-07  
> **产品**：ZR WorkBuddy  
> **对照仓库**：  
> - Deep Agents 实现：`/Users/hebo/WorkBuddy/2026-07-23-09-13-55/simplified-workbuddy`  
> - DSH 热插拔实现：本仓库 `DSH-ZR-WorkBuddy`  
> **关联**：[`三大核心目标落地方案.md`](./三大核心目标落地方案.md)、[`功能迁移-写码审码提交自动化.md`](./功能迁移-写码审码提交自动化.md)、[`企业级安全加固方案.md`](../安全/企业级安全加固方案.md)、根目录 `AGENTS.md`  
> **说明**：simplified 仓内另有 2026-08-24 选型稿（当时 DSH 仓尚未落地）。**本文以两边都已实现后的源码为准**，结论与那份「主 harness = Deep Agents、DSH 未采用」的理论稿不同。

---

## 0. 正式结论（可写入立项）

**不要在「全量 Deep Agents」与「全量 DSH」之间单选。**

两仓业务功能大体一致，综合适配度几乎打平，但**峰值完全相反**：

- **Deep Agents 仓**赢在：多工具业务编排、MES 深度、产品壳、测试与交付成熟度。  
- **DSH 仓**赢在：热插拔、按单元增量部署、第三方像装技能一样安装。  

已验证、可长期演进的稳态是：

> 业务编排采用 **Python Agent 能力模型**（当前即 Deep Agents：Tools / Skills / Middleware / Checkpoint）；  
> 写码执行保持 **Cursor 旁路**（确认后 API/CLI 直执，禁止模型二次 tool_call）；  
> 能力包装与发布采用 **DSH 式 `features/` 热插拔 + 按单元部署**；  
> **DeepSeek 只做模型供应商**，不是换框架的理由。  
> 员工验收永远认 **引擎网页 / API / 探活**，Harness 窗口打开与否不作为成败条件。

**明确不推荐：**

1. 用 `dsh web` / Host 全量替换产品内核（接近重做，MES 能力倒退）。  
2. 宣布 DSH 白做、只留 Deep Agents 单体（丢掉本仓已验证的三大核心目标 G1–G3）。  
3. 再开第三套仓长期分叉。

---

## 1. 先纠正三个易混概念

| 名称 | 是什么 | 与 WorkBuddy 的关系 |
|------|--------|---------------------|
| **Deep Agents** | LangChain 的业务 Agent 厚壳：`create_deep_agent` + Tools / Skills / Middleware / Checkpoint | simplified 仓**主对话已落地** |
| **DeepSeek Harness（DSH）** | DeepSeek 的可拼装 coding-agent 运行时：一切皆 Cordis 插件 | 本仓用它的**热插拔写法与可选 Host**；**不是** MES 大脑 |
| **DeepSeek 模型** | `deepseek-chat` 等推理 API | 两边都能挂；选模型 ≠ 选框架 |

另注意：GitHub 上还有第三方仓库名含 `deepseek-harness`（协议适配器）。本文只讨论官方 `deepseek-ai/deepseek-harness` / `@deepseek-ai/dsh`。

### 1.1 本仓最容易写错的一句话

**DSH-ZR-WorkBuddy 并没有把 DSH 当成产品的主 Agent 运行时。**

DSH / Cordis 在本仓的角色是：

1. **插件容器**（唯一常驻包 `plugins/mes-bridge` + `features/` 热插拔）  
2. **可选聊天壳**（同仓 `host/`，常见 `:3080`）  
3. **工程范式**（新能力只进 `features/`、禁止再堆业务正式 Cordis 包）

算数、HITL、MES 查数、写码 Job、审码、提交、部署都在 **Python 引擎**。`AGENTS.md` 与三大核心目标方案已写死：业务验收看引擎网页，不看 Harness 是否打开。

---

## 2. 选型前提：WorkBuddy 到底是什么

| 维度 | 真实画像 |
|------|----------|
| 产品形态 | 企业工作助手（引擎网页 / 可选嵌入 / 桌面），**不是**通用 coding CLI |
| 主入口 | 自然语言对话 + 确认卡 / 图表 / 写码进度 |
| 能力权重 | 懂平台 / 查数 / 分析 ≈ 主战场；写码 / 审码 ≈ 核心但旁路；自动提交 / 自动部署 ≈ 人触发，禁止无人全自动灌生产 |
| 硬约束 | HITL 确认后直执、路径沙箱、密钥不进 feature、引擎默认只绑回环 |
| 交付约束 | 小团队可维护；可换模型；可打桌面包；可对接现场 ERP HTTP |

用户侧能力清单（本文逐项覆盖）：

1. 可对话  
2. 懂平台业务  
3. 可查数  
4. 可分析数据  
5. 可运维  
6. 能写码 / 改码  
7. 能审码  
8. 能人触发提交  
9. 能人触发部署  
10. 能热插拔加能力 / 装第三方  

**选型原则**：谁更能同时保住「领域工具多 + 硬约束用代码强制 + 写码必须旁路」，谁才是主架构。框架官网宣传分不作数。

---

## 3. 两仓在源码里分别是什么

### 3.1 Deep Agents 仓（simplified-workbuddy）

真正的企业助手形态：Vue 产品壳 + FastAPI + LangGraph 多工具环。

```text
Vue 3 / Electron
  → FastAPI :8765（SSE：token / step / confirm / chart / dashboard）
    → create_deep_agent
         Tools（约 40+）+ Skills（16 个目录）+ Middleware + AsyncSqliteSaver
    → 高风险动作：人点确认卡 → API 直执
         local_dev / cursor_dev / git / SSH（模型不再二次 tool_call）
```

关键路径：

| 区域 | 路径 |
|------|------|
| Agent 入口 | `apps/agent/agents/agent.py` → `create_deep_agent(...)` |
| 运行封装 | `apps/api/agent_wrapper.py`（`AgentRunner.stream_chat`） |
| Middleware | `apps/agent/middleware/`（写确认、路径守卫、实体守卫、审计） |
| Skills | `apps/agent/skills/*/SKILL.md` |
| 写码旁路 | `apps/local_dev/`、`apps/cursor_dev/` |
| 前端分流 | `apps/web/src/chatIntent.js`、`ChatView.vue` |
| 插件 | `docs/插件/架构设计方案.md`（**待评审 · 未开工**） |

锁定依赖（`requirements.lock.txt`）：`deepagents==0.7.7`，`langgraph==1.2.11`，`cursor-sdk==1.0.28`。

### 3.2 DSH 仓（本仓库）

平台型分层：薄 JS feature 插在 Cordis 上，厚 Python 引擎做真相源。

```text
引擎 SPA :8000（产品验收）          Host :3080（可选 Cordis 工具环）
              \                         /
               → features/* 薄 JS
                    defineTool → runEngine([...]) → POST /api/cli
                                 ↓
                    engine/app（意图级联 + code_* + HITL + Cursor Local）
```

关键路径：

| 区域 | 路径 |
|------|------|
| 唯一 Cordis 包 | `apps/zr-workbuddy/plugins/mes-bridge/` |
| 运行时库 | `apps/zr-workbuddy/plugins/mes-runtime/`（`runEngine` → `/api/cli`） |
| 热插拔能力 | `apps/zr-workbuddy/features/*`（7 个：mes-ask / mes-pcb / mes-config / code-dev / code-review / code-commit / code-deploy） |
| 算数真相 | `apps/zr-workbuddy/engine/app/cli_ops.py` |
| 启停真相 | `engine/data/plugins.json` + `plugins_store.py` |
| 写码 | `engine/app/code_dev/cursor_agent.py`（Cursor Local，**不是** DSH coding agent） |
| 上游宿主 | 同仓 `host/`（DeepSeek Harness Studio 0.1.0-rc.8） |

样板（`features/mes-ask/index.js`）：禁止 `import` npm；`eng.defineTool` + `eng.runEngine(["ask", question])` + `attachChart`。

### 3.3 引擎 SPA 聊天不是多工具 Agent

本仓 `cli_ops.chat` 的默认路径是**意图级联**，不是 Deep Agents 那种「模型选工具 → 再调工具」循环：

```text
部署意图 → 提交 / 门禁修复 → 审码 → 写码 → PCB → mes-ask
  → 规则 parse_question 或 LLM 意图
  → 同一套 Python handler
```

因此：

- **员工页（:8000）**：规则 / LLM 分流 + 专用 handler，**没有** Cordis 工具环。  
- **Host 聊天（:3080）**：Harness Agent 才按 `mes_*` 工具名调用 feature。  
- 两边最终都进 `/api/cli`，算数单轨；**产品体验并不单轨**。

这是后续融合时最值得补的缺口：把 Python 多工具 Agent 接到引擎 `/api/chat/stream`，替换意图级联作为默认对话。

---

## 4. 框架对比

### 4.1 架构哲学

```text
Deep Agents（LangChain）
  LangGraph 运行时
    → create_agent（薄壳）
      → create_deep_agent（厚壳：Skills / FS / Middleware 默认内置）
        → 业务 Tools + 自定义 Middleware + Checkpoint

DSH（DeepSeek Harness）
  Cordis 插件框架
    → 模型适配器（插件）
    → Agent Loop（插件）
    → 工具 / 权限 / 持久化 / UI（各自插件）
    → 通过配置拼装，而非继承固定中间件栈
    → fiber.dispose 可逆卸载
```

| | Deep Agents | DSH / Cordis |
|--|-------------|--------------|
| 出品 | LangChain（`langchain-ai/deepagents`） | DeepSeek AI（`deepseek-ai/deepseek-harness`） |
| 定位 | 业务 Agent 厚壳 | Coding Agent 可拼装运行时 |
| 语言 | Python，贴合 FastAPI | 主栈 TypeScript / Node；有 Python SDK |
| 成熟度 | simplified 仓已生产试点 | 官方 Developer preview；本仓 Host 钉 rc.8 |
| 强项 | 多工具环、横切强制、长会话、流式 | 热插拔、权限/文件/Shell、宿主可拼装 |
| 弱项 | 不是插件市场；写大仓易烧上下文 | 不天生懂 MES；嵌进企业产品要自建壳 |
| 与模型 | 模型无关 | 默认真 DeepSeek 适配，也可接其它 provider |
| 默认 UI | 无强制 UI（自建 Vue / SPA） | 自带 Web UI（`dsh web` → `:3080`） |
| 哲学 | 有默认、可覆盖 | 全模块化、可替换 |

### 4.2 框架层面的优劣（不含「本仓怎么用」）

**Deep Agents 适合：**

- 领域工具很多、要稳定 tool calling  
- 硬约束必须代码强制（写确认、路径、实体白名单）  
- 软约束用 Skills 按客户 / 场景演进  
- 会话要可恢复（SSE + checkpoint）  
- 与现有 Python 后端同栈  

**Deep Agents 不适合：**

- 运行时热插拔整功能、按插件发版  
- 当本机 IDE / coding CLI  
- 第三方「像装技能一样」进产品  

**DSH 适合：**

- 能力启停、fiber 卸载、插件中心体验  
- 深度定制 coding loop、文件 / Shell / 权限预设  
- 宿主二次开发、生态插件  

**DSH 不适合：**

- 直接当 MES 产品内核  
- 需要稳定公共 API、已完成安全评审、立刻量产的主框架（官方 preview）  
- 用自带 Web UI 替换企业产品壳（iframe / JWT / 图表协议全要重做）  

### 4.3 本仓对 DSH 的用法是「取其范式、不取其内核」

本仓已经用实践证明了一句话：

> DSH 贡献的是插件式工程方法；WorkBuddy 作为独立应用交付员工网页与引擎能力。

这比「把产品迁到 dsh web」更正确。后续选型应**强化这一判断**，而不是退回「全量 Harness」。

---

## 5. 技术实现对比

### 5.1 栈与体量（2026-09 精读估算）

| 项 | Deep Agents 仓 | DSH 仓（本仓） |
|----|----------------|----------------|
| 业务核心 LOC | agent ~28k + api ~8.8k + web ~25k ≈ **62k** | engine ~23k + features ~1.4k + plugins ~4.8k ≈ **31k** |
| 旁路 / 其它 | local_dev ~12k + cursor_dev ~4.8k + automations ~4.2k | 同仓 `host/` 上游约 **1.47M**（非业务，但是仓内负担） |
| 主语言 | Python Agent + Vue | Python 引擎 + JS feature/bridge + 可选 TS Host |
| 关键依赖 | deepagents 0.7.7、langgraph 1.2、cursor-sdk 1.0.28 | fastapi + cursor-sdk + vendor `@deepseek-ai/*` + host rc.8 |
| 测试 | GitHub Actions `make ci`；约 62 个 `test_*.py` | `scripts/test.sh`；约 10 个测试模块；**无业务仓 CI** |
| 桌面 | Electron 33，嵌 Python runtime + web dist | Electron 33，再嵌 Host（更重、版本更脆） |
| 默认端口 | Web 5180 / API 8765 / 探活沙箱 8001 | 引擎 8000（`runtime.yaml`）/ 可选 Host 3080 |

复杂度落点（按业务源码行数示意，不含 `node_modules` / `engine/data` / host 上游）：

```text
Deep Agents 仓：Agent 工具面 ~34% · Vue 壳 ~30% · 写码旁路 ~20% · API ~11% · 自动化 ~5%
DSH 仓业务树：Python 引擎 ~72% · bridge/client ~15% · scripts ~7% · features ~4%
```

**读法：** DSH feature 薄是架构优点（可热插），也是错觉来源——真正加查数 / HITL / Cursor Job 仍要改引擎并重启。

### 5.2 主对话怎么跑

| 层 | Deep Agents 仓 | DSH 仓 |
|----|----------------|--------|
| 用户界面 | Vue 3 + Element Plus + ECharts | 引擎零依赖 SPA + 可选 Host + bridge 卡片 |
| HTTP | FastAPI SSE，事件与卡片一一对应 | `/api/chat[/stream]` + `/api/cli` 单轨 |
| 理解与选工具 | `create_deep_agent` 多工具环 | SPA：意图级联；Host：Harness 选 `mes_*` |
| 硬约束 | Middleware（写确认、路径、实体、审计） | HITL nonce + 路径票 + `plugins.json` 启停 |
| 真改盘 | confirm 后 `local_dev` / `cursor_dev` / git / SSH | confirm 后 `engine/app/code_*` |
| 会话恢复 | LangGraph `AsyncSqliteSaver` | 引擎侧会话较弱；Host 有 session log |

### 5.3 HITL / 安全

两边都钉死同一条铁律：**模型说完 ≠ 已执行**。确认后由后端直执，禁止「模型再说一遍确认」当执行。

| 控制点 | Deep Agents 仓 | DSH 仓 | 评 |
|--------|----------------|--------|----|
| MES 写入 | `WriteConfirmMiddleware` → pending → `/api/writes` confirm 直执 | 引擎侧导入确认（能力面较窄） | 左更完整 |
| 写码 / 提交 / 部署 | 前端意图旁路 + 确认卡 + API 直执 | prepare → nonce → confirm；`code-dev-start` 已关闭 | 同级，本仓 nonce 更硬 |
| 路径隔离 | `FilesystemBackend(virtual_mode=True)` + `HostPathGuardMiddleware` | 审码路径票；写码沙箱拷贝 | 场景不同，都有 |
| 用户隔离 | JWT `sub` + 会话历史隔离 | 引擎默认只绑 `127.0.0.1`，无助手级多用户 JWT | 多用户产品：左 |
| 威胁模型文档 | 分散在功能册 | [`企业级安全加固方案.md`](../安全/企业级安全加固方案.md) + Cursor 铁律 | 本仓更集中 |
| 框架默认危险面 | 写码勿进主环（已旁路） | Creator / `danger-full-access` 不可用于企业默认 | 都靠产品策略收口 |

本仓硬门禁示例（`cli_ops.py`）：`code-dev-start` 直接拒绝，必须走确认卡 HITL nonce → `code-dev-confirm`。

### 5.4 写码 / 审码 / 提交 / 部署实现

**写码链路其实同源**，不该用「换框架」来解决：

```text
对话澄清
  → 人确认
  → Cursor Local 在沙箱改文件
  → 约束同步回工作区
  → 不自动 git commit
```

| 车道 | Deep Agents 仓 | DSH 仓 | 本阶段不做 |
|------|----------------|--------|------------|
| 写码执行 | Cursor Local（默认）+ Cursor Cloud | **仅** Cursor Local | 本仓不做 Cloud |
| 审码 | IDE Bridge + Git 浅克隆 + 贴码 | 本机目录直读 + Viprasol Skill | 本仓不做 VS Code Bridge |
| 提交 | commit-batch 旁路 + 门禁卡 | `code-commit` feature + 门禁 | — |
| 部署 | 预发 SSH / GitHub Actions（人触发） | **按单元** rsync + 引擎探活（G2） | 本仓 MVP 不做境外 CI |

结论：写码手感取决于 **Cursor SDK + 沙箱策略**。用 DSH 替换 Cursor 才是写码执行层的真问题；用 DSH 替换整套 WorkBuddy 解决不了写码。

### 5.5 实现质量：各做得好的与短板

**Deep Agents 仓做得好的**

- 主环协议完整：SSE 与 Vue 卡片一一对应  
- `workbuddy_lane` 把写码 / 审码 / 贴码互斥  
- MES 工具面厚：实体、指标、图表、看板、表结构摸底、能力地图、API 探活沙箱、运维 playbook  
- JWT 用户隔离、HA flock、CI 门禁  

**Deep Agents 仓短板**

- `agent.py` 中央注册 40+ 工具，增删必改核心文件  
- 插件热插拔只有设计文档  
- `ChatView` + `chatIntent.js` 意图正则过重  
- 修一个功能要重打整包 dmg  

**本仓做得好的**

- 分层铁律清楚：唯一 bridge、features 热插、engine 单轨、`runtime.yaml` 一处解析  
- HITL nonce 绑定 workspace / job  
- 按单元 rsync 把「改哪发哪」做成产品能力  
- Feature 契约可验收：无 npm、fiber 可卸、失败隔离、第三方走同一 `install-feature`  

**本仓短板**

- 双入口（`:8000` vs `:3080`）认知税高  
- 引擎聊天不是多工具 Agent，复杂组合任务弱  
- 双栈 + vendor realpath + Host rc.8 预览期，运维面比单 Python Agent 脆  
- SPA 零依赖便于内嵌，产品壳完整度不如 Vue  
- 业务仓无 GitHub Actions  

---

## 6. 业务能力矩阵

两边都覆盖：对话、MES 查数、写码、审码、人触发提交、部署。完成度并不对称。

| 能力 | Deep Agents 仓 | DSH 仓 | 差距性质 |
|------|----------------|--------|----------|
| 可对话 | SSE 多轮 + checkpoint + 停生成锁 | SPA 对话；Host 另有会话 | 左：真 Agent 流；右：双表面 |
| 懂平台 / 资料包 | schema / capability / glossary / profile 工具链 | MES 配置 + 规则/LLM 意图 | 左明显更深 |
| 查数 | 实体守卫、指标、汇总、缺口 | `mes_ask` 一条工具打到引擎 `ask` | 左工具面；右可热关 |
| 分析出图 | ECharts 卡 + 看板协议 | matplotlib / 附件图 + 表 | 产品体验左强 |
| 运维 playbook / API 探活 | 已落地（沙箱 :8001） | 未见对等模块 | 左独有 |
| 文件导入 HITL | 写确认卡 + 审计 | 非主战场 | 左更完整 |
| 本机写码 | Cursor Local 沙箱 + 同步闸门 | 同思路，`features/code-dev` | 同级 |
| Cloud / GitHub 写码 | `cursor_dev` Cloud + 仓白名单 | 明确本阶段不做 | 左独有 |
| 审码 | IDE Bridge + Git 浅克隆 + 贴码 | 本机目录直读 | 场景不同；左覆盖面宽 |
| 人触发提交 | commit-batch 旁路 + 门禁卡 | `code-commit` + 门禁 | 同级 |
| 部署 | 预发 SSH / GitHub Actions | **按单元增量 rsync** + 引擎探活 | 右更贴「改哪发哪」 |
| 自动化任务 | 调度 + Agent → 企微/飞书 | P0-4 规划中，尚未见 feature | 左独有 |
| ERP 登录 / 嵌入 | JWT + 可选 MES 页嵌入 | 引擎本机绑定；MES 客户端登录另计 | 多租户/嵌入：左 |
| 功能热开关 | 设计稿，未实现 | `plugins.json` + 管理页，约 1s | **右独有且已验证** |
| 第三方安装 | 未开工 | `plugin.sh install-feature` 校验→enable | **右独有** |

本仓当前启用 feature（`engine/data/plugins.json` 口径）：`mes-config`、`mes-pcb`、`mes-ask`、`code-dev`、`code-review`、`code-commit`、`code-deploy`。

---

## 7. 可扩展性对比

### 7.1 加一个新能力，实际要动什么

| 要加的东西 | Deep Agents 仓 | 是否重启 | DSH 仓 | 是否重启 |
|------------|----------------|----------|--------|----------|
| 新对话剧本 | `skills/<id>/SKILL.md` | 重启 API | `.dsh/skills` 或引擎提示 | Host 视加载；SPA 改引擎 |
| 新 Agent 工具 | `tools/` + 写入 `agent.py` 的 `TOOLS` | 重启 API | `plugin.sh new` → `features/<id>` | **否（约 1.2s）** |
| 新查数/分析逻辑 | Python 工具实现 | 重启 API | `engine/app` + `cli_ops` 命令 | **只重启引擎** |
| 企业硬拦截 | 新 Middleware | 重启 API | HITL / 引擎守卫 | 重启引擎 |
| 前端卡片 | `ChatView` / 新 Vue 组件 | Vite 热更；发版整包 | SPA 或 `bridge/client.js` | 引擎或 bridge 单元 |
| 只发这一个功能到预发 | 基本做不到（整包） | 整包 | `feature:<id>` rsync | 热加载，不重启引擎 |
| 第三方交付物 | 无正式通道 | — | 目录/zip → 校验 → enable | 热加载 |

### 7.2 热插拔的边界（必须写进方案）

G1 **只保证「工具注册」热插拔**。

查数口径、意图、HITL、Cursor Job 仍在 `engine/app`，改这些必须重启引擎。  
**禁止**把「热插拔」说成一切 UI 与算数都能不停机替换。引擎 SPA 静态资源随 **engine 单元**发布。

### 7.3 三年视角

**若只强化 Deep Agents 仓：**  
优势继续堆在领域工具和产品协议。风险是单体膨胀——工具表、意图正则、`ChatView` 成为所有功能的汇合点。插件方案若仍不落地，现场会变成「整包发版 + 开关靠配置」。可演进路径：在不换主 harness 的前提下做 `PluginRegistry`，向 `create_deep_agent` 动态注册 tools/skills（simplified 仓设计稿已写，未开工）。

**若只强化本仓现状：**  
优势继续堆在发布与生态。风险是 Host 预览破坏、双栈人才、`engine` 仍变单体（只是外套一层薄 JS）。若员工始终只用 SPA，Cordis 工具环会变成维护成本而不是用户价值。可演进路径：把引擎聊天升级为真正的多工具 Agent（甚至嵌入 Deep Agents），同时保住 `features` 契约与单元部署。

### 7.4 风险清单

| 风险 | 主要落在 | 严重度 | 缓解 |
|------|----------|--------|------|
| 中央 `TOOLS` 列表锁死迭代 | Deep Agents 仓 | 高 | 落地插件注册表，禁止再往 `agent.py` 堆 import |
| Host ~1.47M + rc 预览破坏兼容 | 本仓 | 高 | 业务与 host **分轨发版**；禁止把业务焊进 host 内核 |
| 双聊天面协议分叉 | 本仓 | 中高 | 验收只认引擎；Host 当可选壳；卡片协议对齐 |
| 前端意图正则成为暗逻辑 | Deep Agents 仓 | 中 | 显式 lane + 服务端解析 |
| feature 无 npm → 每个 SDK 都要开引擎口 | 本仓 | 中 | 保持铁律；Node 库只进 runtime；密钥只进 yaml |
| 桌面整包体积 / 发版粒度 | 两边 | 中 | 本仓已有单元；Deep Agents 需拆 runtime 与插件包 |
| vendor `dsh-tools` realpath 不一致 | 本仓 | 中 | `scripts/check-vendor.sh` 门禁，勿手改 link |
| 无业务仓 CI | 本仓 | 中 | 把 `test.sh` / `check-features` 接到 CI |

---

## 8. 十二维评分（0–10，源码对照）

评分口径：10 = 该维度已在该仓验证且匹配产品；3 以下 = 仅有设计或方向错配。**不是**框架官网宣传分。

| 维度 | Deep Agents 仓 | DSH 仓 | 说明 |
|------|---------------:|-------:|------|
| Agent 编排 | 9 | 5 | 左：真多工具环；右：Host 有、员工页没有 |
| MES 深度 | 9 | 6 | 左工具链完整；右 `mes_ask` 可热关但面窄 |
| 写码审码 | 8 | 7 | 同 Cursor Local；左多 Cloud / Bridge |
| HITL 安全 | 8 | 8 | 同级；左多用户 JWT，右 nonce 更硬 |
| 热插拔 | 3 | 9 | 左仅设计稿；右约 1.2s 已验证 |
| 增量部署 | 5 | 9 | 左整包/HA；右按单元 rsync |
| 第三方 | 3 | 8 | 左未开工；右 `install-feature` |
| 可维护性 | 7 | 5 | 左单栈单体；右双栈 + Host 负担 |
| 交付成熟 | 8 | 6 | 左 Vue/CI/HA；右 SPA + 预览 Host |
| 测试 CI | 8 | 5 | 左 Actions；右 `test.sh` |
| 产品壳 | 8 | 5 | 左 Vue 卡片协议；右双表面 |
| 平台化 | 5 | 8 | 左缺插件市场；右 G1–G3 已咬合 |
| **均分** | **6.8** | **6.8** | 均分打平，峰值镜像 |

均分相同的含义：全量替换任何一边，都会丢掉另一边已经验证的峰值。

---

## 9. 四条架构选项

| 选项 | 做法 | 适配 | 风险 | 工期体感 | 推荐 |
|------|------|------|------|----------|------|
| **A 强化 Deep Agents** | 主环不动；补 PluginRegistry；写码仍 Cursor | MES 产品 | 低 | 继续演进 | 若北星只是助手 |
| **B 强化 DSH 范式** | `features`/`engine` 不动；给引擎补真 Agent 环 | 平台发布 | 中 | 数周～一季 | 若北星只是平台 |
| **C 全量迁 DSH 当内核** | 用 Host 换产品壳与 MES 工具 | 差 | 极高 | 接近重做 | **否** |
| **D 融合** | Deep Agents 能力模型进引擎；DSH 只做插件与发布 | 北星重叠 | 中（一次搬迁） | 有设计的迁移 | **是（当前北星）** |

本仓三大核心目标（热插拔 / 增量部署 / 第三方）与「企业 MES 助手要深」同时存在，因此默认走 **D**。

选项 C 为什么否：收益几乎只剩「写码手感 / 插件哲学」，而写码已经旁路给 Cursor；A/B/C 类 MES 能力、图表协议、嵌入、JWT、厂区资料包全部要重做。本仓自己已经拒绝了这条路（业务不焊进 `host/`）。

---

## 10. 按北星怎么选（给拍板用）

| 如果北星是 | 选 | 不要做 |
|------------|----|--------|
| 厂区 MES 助手：查数 / 分析 / 值班 / 嵌入，尽快稳 | 继续 Deep Agents 仓为主产品 | 不要用 `dsh web` 换 Vue 壳，不要重写 40+ 工具 |
| 平台：热插拔、改哪发哪、第三方像装技能 | 继续本仓架构铁律 | 不要再往 profile 堆业务 Cordis 包，不要删 bridge |
| **两者都要（真实领导诉求）** | **融合：引擎内补多工具 Agent，外壳保持 features / 单元部署** | 不要再开第三套并行仓长期分叉 |

### 10.1 为什么不能把 DSH 当唯一主框架

产品主价值是懂业务的对话与企业硬约束，不是 coding CLI。本仓已经用实践证明：真正干活的逻辑全在 Python 引擎；Cordis 层是插座。预览期 Host、双栈、双入口会把小团队拖进框架运维。

### 10.2 为什么不能宣布 Deep Agents 已够、DSH 白做

simplified 自己的插件设计稿承认了单体痛点，却还没开工。本仓已经把热插拔、增量部署、第三方安装做成可验收目标（G1–G3）。丢掉这一套，等于放弃领导明确提出的三大核心目标。

### 10.3 模型与框架正交

继续用 DeepSeek（或通义 / 自建）当对话模型即可。**不必**为了用 DeepSeek 模型而换 DeepSeek Harness。同一模型在不同 harness 下的工具行为、上下文、成本可以完全不同。

---

## 11. 融合落地路径（推荐选项 D）

目标：一条产品链同时保住 Deep Agents 的编排深度，和本仓的 G1–G3。

### 11.1 原则（服从现有铁律，不推倒）

1. **simplified 只读对照**，允许拷贝改编进本仓；禁止改源仓。  
2. 新 Agent 能力仍只进 `apps/zr-workbuddy/features/`。  
3. 算数与旁路执行仍只进 `engine/app`，经 `runEngine` → `/api/cli`。  
4. 唯一常驻 Cordis 包仍是 `mes-bridge`。  
5. feature 仍禁止 `import` / `require` npm。  
6. 密钥 / URL 只进 `engine/config/config.yaml`。  
7. 员工验收仍只认引擎网页 / 探活。  
8. 高风险动作仍是 prepare → 人确认 → 直执。

### 11.2 分步

| 步 | 做什么 | 验收 | 不做什么 |
|----|--------|------|----------|
| **D0 冻结分叉** | 新 MES 深度能力优先回流本仓引擎工具，而不是只加在 simplified 的 `agent.py` | 两仓功能清单对照表 | 再开第三仓 |
| **D1 引擎多工具环** | 把 `create_deep_agent`（或等价 Python 工具环）接到引擎 `/api/chat/stream`，替换意图级联作为**默认**对话 | 同一问句可走多工具；SSE 与现有 SPA 卡片兼容 | 用 Host 当员工默认壳 |
| **D2 双注册** | 每个工具：feature 注册到 Cordis（给 Host 用）+ 注册到 Python Agent（给员工页用）；算数只留 engine | disable feature 后两面工具都消失 | 在 Node 里复制一份分析逻辑 |
| **D3 迁 MES 深度** | 按需迁实体目录、图表协议、探活、playbook；能热关的做成 feature | 能力矩阵差距缩小 | 一次搬完 40 个工具 |
| **D4 发布不变** | 继续 G2 单元 rsync；feature 变更不重启引擎；engine 变更才重启引擎 | 改一个 feature 只发该单元 | 把 Host 重启当业务成败 |
| **D5 可选 Host** | Host 保持二次开发 / 生态插件；永不作为员工验收 | 无远端 profile 时跳过宿主重启属正常 | 业务焊进 `host/` |

### 11.3 与现有 P0/P1 的关系

本仓已落地：本机写码、人触发提交、本机审码、按单元部署、第三方 install-feature。  
融合**不推翻**这些车道，只升级「默认对话怎么选工具」。

尚未落地、融合时不要忘：自动化（P0-4，固定模板 + 企微，禁止自动写码提交部署）。若迁 simplified 的 automations，executor 必须重写为引擎调度，**禁止**直接调 Deep Agents 当发版器。

### 11.4 明确不做

- 用 `dsh web` 替换引擎 SPA  
- 让模型直接 ssh / git push / 改生产  
- 把写码主执行塞回 Deep Agents 或 DSH Agent loop  
- 新增第二个业务正式 Cordis 包  
- 在 Node 里 `spawn uvicorn`  
- 为了「用上 DSH coding agent」再叠第三条写码执行栈（Cursor 已经够）

---

## 12. 给不同角色的一页纸

**给领导**

- 两个框架不是谁淘汰谁。一个会「听懂人话、选很多业务工具」；一个会「功能热插拔、改哪发哪、第三方能装进来」。  
- 写码两边都请 Cursor 施工，框架换了也不会让写码突然变强。  
- 建议：引擎继续当员工入口；对话大脑补成真正的 Agent；发布继续按插件单元走。

**给架构 / 主程**

- 本仓 DSH 用法已经正确（范式而非内核）。缺的是引擎侧多工具编排，不是再引入一套 Host 业务。  
- simplified 的插件设计稿，本仓已经实现了更硬的版本——不要倒回去做「Python 单体 + 整包 dmg」。  
- 融合时最大技术债：SSE 卡片协议、feature 启停与 Agent 工具集同步、checkpoint 存哪。

**给现场实施**

- 员工只开引擎页。Host 不是培训必选项。  
- 关一个功能用功能插件页 / `plugin.sh disable`，约 1 秒生效。  
- 改查数口径仍要发 engine 单元并重启引擎——不要承诺「改任何东西都不停机」。

---

## 13. 附录

### 13.1 本仓铁律（与本文一致，禁止用选型推翻）

见根目录 `AGENTS.md`：唯一 bridge、业务不绑宿主、验收看引擎、WorkBuddy 第三方进 `features/`、生态插件进宿主。

### 13.2 simplified 仓关键入口（只读对照）

| 区域 | 路径 |
|------|------|
| 架构分流 | `docs/功能实现/00-总览与架构分流.md` |
| 旧选型稿（理论，已被本文取代为「落地后对照」） | `docs/Agent开发/DeepAgents与DeepSeek-Harness技术选型分析.md` |
| Skills / Middleware 指南 | `docs/Agent开发/DeepAgents-Skills使用指南.md`、`DeepAgents-Middleware使用指南.md` |
| 插件设计（未开工） | `docs/插件/架构设计方案.md` |

### 13.3 本仓关键入口

| 区域 | 路径 |
|------|------|
| 北星 | [`三大核心目标落地方案.md`](./三大核心目标落地方案.md) |
| 分层用法 | [`目录结构与用法说明.md`](../产品与口径/目录结构与用法说明.md) |
| 写码审码提交迁移 | [`功能迁移-写码审码提交自动化.md`](./功能迁移-写码审码提交自动化.md) |
| 安全 | [`企业级安全加固方案.md`](../安全/企业级安全加固方案.md) |
| 单元部署 | [`功能实现/P1-自动化部署-按单元增量.md`](../功能实现/P1-自动化部署-按单元增量.md) |
| 第三方安装 | [`功能实现/P2-第三方插件安装使用功能实现.md`](../功能实现/P2-第三方插件安装使用功能实现.md) |

### 13.4 修订记录

| 日期 | 说明 |
|------|------|
| 2026-09-07 | 首版：基于两仓源码精读的全方位对比；结论为融合（选项 D），而非 8 月理论稿的「只锁 Deep Agents」 |

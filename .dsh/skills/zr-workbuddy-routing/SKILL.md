---
name: zr-workbuddy-routing
description: >-
  ZR-WorkBuddy 工具路由：根据用户意图选择 mes_ask / mes_pcb / mes_code_dev_* /
  mes_config 等热插拔 feature 工具。查数、PCB 工艺、本机写码、连接配置分流。
---

# ZR-WorkBuddy 工具路由

本 Skill 只指导 **选工具与顺序**；业务逻辑在引擎，可调用能力由 `features/` 热插拔注册。
若某工具不存在，说明对应 feature 未启用，勿假装已调用。

## 快速分流

| 用户意图 | 优先工具 | feature id |
| --- | --- | --- |
| 查产量、良率、OEE、工单、缺陷等 **MES 数据** | `mes_ask` | mes-ask |
| PCB 工序、叠层阻抗、DFM、AOI/飞针、IPC、缺陷排障 | `mes_pcb` | mes-pcb |
| 在本机工程 **写代码 / 改页面 / 加功能 / 做报表页** | `mes_code_dev_*`（见 zr-workbuddy-code-dev） | code-dev |
| 测 MES/LLM 连接、看引擎状态 | `mes_config` / `mes_status` | mes-config |

## 边界（易错）

1. **PCB 工艺 ≠ MES 查数**  
   问「PCB 有哪些工序」「Class 2 孔铜」→ `mes_pcb`，不是 `mes_ask`。

2. **做页面/改代码 ≠ 查数**  
   「员工工时报表页面」「加一个列表 CRUD」→ 写码流程（`code-dev`），不是 `mes_ask`。

3. **写码不会自动 commit**  
   本机写码只同步改动到 workspace；提交需用户后续单独确认（P0-2 未开前勿承诺自动提交）。

4. **引擎要先在跑**  
   工具经 `mesEngine.runEngine` 调后厨。若失败，提示：`scripts/engine.sh zr-workbuddy ensure`。

## 各工具一览

### mes-ask（`mes_ask`）

- 自然语言查 MES 指标与工单类数据，可出图。
- 示例：「今日再制品工单有多少」「分析 8 月 30 号良率偏低原因」。

### mes-pcb（`mes_pcb`）

- PCB 制造领域专家，非 MES SQL 查数。
- 示例：「飞针和 AOI 怎么分工」「HASL 和 ENIG 选型」。

### mes-config（`mes_config` / `mes_status`）

- `mes_status`：连接与引擎概况。
- `mes_config`：`action=test-mes` | `test-llm` | 留空同 status。

### code-dev（`mes_code_dev_*`）

- 总流程：**zr-workbuddy-code-dev**
- 需求/UI 子 Skill（写码链路）：  
  `zr-workbuddy-requirements` →（可选）`zr-workbuddy-repo-bootstrap` →  
  （UI 时）`zr-workbuddy-ui-product-design` / `zr-workbuddy-ui-craft` →  
  确认后 `zr-workbuddy-coding-impl`
- 工具：`mes_code_dev_status`、`mes_code_dev_check`、`mes_code_dev_start`、
  `mes_code_dev_job`、`mes_code_dev_cancel`。
- 写码车道须在引擎配置中心开启（`code_dev.enabled`）。

## Feature 未启用时

告知用户（不必重启 DSH）：

```bash
scripts/plugin.sh --app zr-workbuddy features          # 看清单
scripts/plugin.sh --app zr-workbuddy enable <feature-id> # 例如 code-dev
```

写码还需引擎配置中心 → **写码车道** 打开开关。

## 与架构的关系

- **Skill（本文件）**：DSH Agent 上下文，教路由与流程。
- **Feature**：`apps/zr-workbuddy/features/<id>/` 注册工具，~1s 热插拔。
- **Engine**：`engine/app/` 算数与校验；改 Python 需 `engine.sh restart`。

三者分工固定；勿在 Skill 里重复实现引擎逻辑。

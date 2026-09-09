---
name: zr-workbuddy-routing
description: >-
  ZR-WorkBuddy 工具路由：根据用户意图选择 mes_ask / mes_pcb / pcb_count_bom /
  pcb_parse_dimensions / weather_query / weather_forecast / mes_code_dev_* /
  mes_code_review_* / mes_code_commit_* / mes_config 等工具。查数、PCB 工艺、
  BOM 统计、板尺寸、天气、本机写码审码提交分流。
---

# ZR-WorkBuddy 工具路由

本 Skill 只指导 **选工具与顺序**；业务逻辑在引擎或已安装的 DSH 插件，可调用能力由
`features/` 热插拔或公司插件市场 Bundle 注册。
若某工具不存在，说明对应 feature/插件未启用，勿假装已调用。

## 快速分流

| 用户意图 | 优先工具 | 来源 |
| --- | --- | --- |
| 查产量、良率、OEE、工单、缺陷等 **MES 数据** | `mes_ask` | feature mes-ask |
| PCB **工艺问答**（叠层、DFM、AOI/飞针、IPC、缺陷排障） | `mes_pcb` | feature mes-pcb |
| **统计 BOM 清单**（位号+数量文本：有几行、总数量） | `pcb_count_bom` | 插件 @zhongruan/dsh-pcb-helper |
| **解析板尺寸字符串**（如 100x80mm、长宽多少） | `pcb_parse_dimensions` | 插件 @zhongruan/dsh-pcb-helper |
| **查某城市现在天气**（气温、湿度、风力） | `weather_query` | 插件 @zhongruan/dsh-weather |
| **查未来几天天气预报** | `weather_forecast` | 插件 @zhongruan/dsh-weather |
| 在本机工程 **写代码 / 改页面 / 改菜单 / 加功能 / 做报表页** | **立刻** `mes_code_dev_begin`（禁止 Bash 扫仓） | code-dev |
| **本机目录审码**（直读源码，非 Git） | `mes_code_review_*`（见 zr-workbuddy-code-review） | code-review |
| **提交 / git commit / 推送本批代码** | 对话确认卡优先；工具 `mes_code_commit_*` | code-commit |
| 测 MES/LLM 连接、看引擎状态 | `mes_config` / `mes_status` | mes-config |

## 边界（易错）

1. **PCB 工艺问答 ≠ MES 查数**  
   问「PCB 有哪些工序」「Class 2 孔铜」→ `mes_pcb`，不是 `mes_ask`。

2. **BOM 行数/数量统计 ≠ PCB 工艺专家**  
   用户贴了 `R1,10` / `C2,20` 这类清单，问「有多少行」「元器件总共多少」  
   → **必须** `pcb_count_bom`（把原文放进 `bomText`），**禁止**用 `mes_pcb` 闲聊代替统计。  
   若工具不存在，说明未安装公司插件 `@zhongruan/dsh-pcb-helper`，再提示去插件市场安装。

3. **板尺寸字符串解析 ≠ 工艺问答**  
   「120x80mm 长宽多少」「解析板尺寸」→ `pcb_parse_dimensions`（`sizeText`），不是 `mes_pcb`。

3b. **查天气 ≠ 闲聊编造**  
   「深圳今天天气怎么样」「北京未来三天预报」→ `weather_query` / `weather_forecast`（`city` 填城市名）。  
   禁止凭记忆报气温；若工具不存在，提示去插件市场安装 `@zhongruan/dsh-weather`。

4. **做页面/改代码/改菜单 ≠ 查数，也 ≠ 宿主自己改仓**  
   「员工工时报表页面」「加一个列表 CRUD」「物料出库要写在仓库管理菜单」  
   → **只调** `mes_code_dev_begin`，出主聊天写码工具卡。  
   **禁止** Bash / Grep / Read 扫用户工程、禁止宿主 Agent 直接改文件。

5. **写码不会自动 commit**  
   本机写码只同步改动到 workspace；提交走 `code-commit`：**选目录 → 门禁 → 人确认** 后才 git。  
   禁止模型口头「确认一下」就调用 `mes_code_commit_confirm`（须 `confirmed=true` 且用户已点确认卡）。

6. **提交 ≠ 全量审码**  
   「提交代码」走门禁 findings 列表，**不要**调用 `mes_code_review_run` 出「代码审核汇总报告」。

7. **引擎要先在跑**  
   工具经 `mesEngine.runEngine` 调后厨。若失败，提示：`scripts/engine.sh zr-workbuddy ensure`。

## 各工具一览

### mes-ask（`mes_ask`）

- 自然语言查 MES 指标与工单类数据，可出图。
- 示例：「今日再制品工单有多少」「分析 8 月 30 号良率偏低原因」。

### mes-pcb（`mes_pcb`）

- PCB **制造工艺**专家对话，非 MES SQL，也 **不是** BOM 算术统计。
- 示例：「飞针和 AOI 怎么分工」「HASL 和 ENIG 选型」。
- **不要**用于：统计位号清单行数/总数量、解析 `100x80mm` 字符串。

### pcb-helper 插件（`pcb_count_bom` / `pcb_parse_dimensions`）

- 公司市场插件 `@zhongruan/dsh-pcb-helper` 提供。
- `pcb_count_bom`：用户给出多行「位号,数量」，统计行数与总数量。
- `pcb_parse_dimensions`：解析板尺寸字符串。
- 示例：「下面 BOM 有多少行、元器件总共多少」「帮我看下 120x80mm 长宽」。

### weather 插件（`weather_query` / `weather_forecast`）

- 公司市场插件 `@zhongruan/dsh-weather` 提供（Open-Meteo）。
- `weather_query`：城市实况气温、湿度、风力。
- `weather_forecast`：未来 1～7 天预报（默认 3 天）。
- 示例：「深圳现在天气怎么样」「上海未来三天会下雨吗」。

### mes-config（`mes_config` / `mes_status`）

- `mes_status`：连接与引擎概况。
- `mes_config`：`action=test-mes` | `test-llm` | 留空同 status。

### code-dev（`mes_code_dev_*`）

- **主入口：`mes_code_dev_begin`**（改代码/改页面/改菜单第一下就调；见 **zr-workbuddy-code-dev**）
- 工具卡内：选目录 → discuss 选项/确认 → Cursor Local；**不要**用 Bash 摸底代替 begin
- 排障才用：`mes_code_dev_status`、`check`；确认后偶发代调：`start`（须 confirmed）
- 进度：`mes_code_dev_job` / `cancel`
- 写码车道须在引擎配置中心开启（`code_dev.enabled`）。

### code-review（`mes_code_review_*`）

- 本机直读源码 + Viprasol Skill LLM + 规则补种；终稿「代码审核汇总报告」；**非 Git diff、非 VS Code Bridge**。
- 对话确认卡优先走引擎 **`/api/code-review/run/stream`**（SSE 进度 + 终稿逐行流式）。
- Skill：**zr-workbuddy-code-review**
- 工具：`mes_code_review_status`、`check`、`list`、`run`、`report`。
- 审码车道须在配置中心开启（`code_review.enabled`）+ LLM 已配置。

### code-commit（`mes_code_commit_*`）

- 人触发提交：对话出选目录卡 → `POST /api/code-commit/start` 门禁 → 人确认 → `confirm` 才 commit/push。
- Skill（门禁批审，非报告）：**zr-workbuddy-commit-batch-review**
- 工具：`mes_code_commit_status`、`check`、`prepare`、`start`、`confirm`（须 confirmed）、`job`。
- 提交车道须在配置中心开启（`code_commit.enabled`）；默认 `default_push=true`。

## Feature / 插件未启用时

告知用户（不必重启 DSH）：

```bash
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy enable <feature-id>
```

公司插件：设置 → 插件市场 → 安装 `@zhongruan/dsh-pcb-helper` 或 `@zhongruan/dsh-weather`。

写码还需引擎配置中心 → **写码车道** 打开开关；提交还需 **提交车道**。

## 与架构的关系

- **Skill（本文件）**：DSH Agent 上下文，教路由与流程。
- **Feature**：`apps/zr-workbuddy/features/<id>/` 注册工具，~1s 热插拔。
- **公司 DSH 插件**：插件市场 Bundle（如 pcb-helper），与 feature 并列可选。
- **Engine**：`engine/app/` 算数与校验；改 Python 需 `engine.sh restart`。

分工固定；勿在 Skill 里重复实现引擎逻辑。

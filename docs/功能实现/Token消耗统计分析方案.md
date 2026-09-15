# Token 消耗统计分析 · 可行性实施方案

> **状态**：P0 已实现  
> **范围**：**(1) DeepSeek/Ollama LLM**（引擎调用 + 只读采集 DSH 宿主会话）、**(2) Cursor 写码**（引擎通道 + DSH Cursor Job）  
> **验收**：引擎网页「用量」页能按天/车道看到真实或标明来源的 token；DSH 设置左侧「用量」与「插件市场」并列（只读壳）。**不以打开聊天为成败**  
> **不包含（本期）**：多租户计费、自动扣费、改 Cursor 官网额度；不改 DSH / 插件源码

---

## 1. 一句话总结

现在两条消耗都在烧钱/额度，但引擎**把供应商回传的 usage 丢掉了**。做法是：在现有两个调用出口各记一笔流水，落到引擎本地账本，再用引擎网页做统计。不算新架构，不新增 Cordis 包。

---

## 2. 现状（已核对代码）

| 消耗口 | 实际调用 | 供应商能不能给 token | 本仓现在做什么 |
|---|---|---|---|
| **LLM** | `nl_engine._llm_call` / `llm_freeform_stream` → DeepSeek 或 Ollama `/v1/chat/completions` | DeepSeek **会**在 JSON 里给 `usage.prompt_tokens` / `completion_tokens`；流式需加 `stream_options.include_usage`。Ollama 视版本，可能没有 | **只取回复文本，usage 丢弃** |
| **Cursor 写码** | `code_dev/cursor_agent.py`：`Agent.create` → `send` → `run.wait()` | SDK 的 `RunResult.usage` 有 `input_tokens` / `output_tokens` / cache / reasoning。`agent.get_usage()` **仅 Cloud**，本仓是 Local，不能当主路径 | **只读 `result.text`；额度用尽只做文案与 Auto 回退** |

其它车道都走上面两个口之一：

```text
LLM（DeepSeek/Ollama）
  ├─ 聊天 / mes-ask 意图
  ├─ PCB 专家
  ├─ 写码讨论卡（confirm 前文案）
  ├─ 审码（多批次 llm_freeform）
  ├─ 提交门禁 skill 审核（现有字符估算，且没落盘）
  └─ 配置中心测连通

Cursor Local
  └─ 写码确认后的沙箱改码（真正烧 Cursor 额度）
```

**不算本期账本：** 部署（无模型）、引擎 Job SSE 里名叫 `token` 的事件（那是**流式正文**，不是计费 token）。DSH 宿主聊天 token 只读 `~/.dsh/sessions` 会话文件，不改宿主。

身份：写码 Job 已有 `user_id` 字段，但开工时写的是空串。本期按**本机这一套引擎**统计；人维度等有登录再加。

---

## 3. 目标 / 非目标

### 要达到

1. **每次** LLM 调用、**每次** Cursor 写码 run，记 1 条流水（失败也记，token 可为 0，带错误原因）。  
2. 流水带：时间、来源（`llm` / `cursor`）、车道、模型、token 分项、数据质量（供应商真值 / SDK / 估算 / 缺失）。  
3. 引擎网页能看：今日 / 近 7 天 / 近 30 天；LLM vs Cursor；按车道拆开。  
4. 记账失败**不得**让写码/审码/聊天失败。  
5. 日志与 SSE **禁止**回显 API Key。

### 明确不做

- 不新增业务 Cordis 包；账本只在引擎。DSH 设置「用量」是 mes-bridge 只读壳（`settings.section` `id=workbuddy-usage`，`order: 39`，紧挨插件市场 `order: 40`），不另造鉴权、不 HITL。  
- 不把 Job SSE 的 `token` 事件改名（会动四车道契约）；账本事件用 `usage` / `llm_tokens`。  
- 不以 Cursor 官网 Usage 页或 DeepSeek 控制台为验收（那些是对照，不是本产品）。  
- 不在本期做「额度用完自动停写码」策略开关以外的计费系统（可后续加阈值告警）。

---

## 4. 可行性（先判再做）

| 项 | 结论 | 依据 |
|---|---|---|
| LLM 真值 | **高，可做** | 改 `_llm_call` 一处即可覆盖聊天/PCB/讨论/审码/提交/测连通；DeepSeek 响应已有 `usage` |
| LLM 流式 | **高，可做** | 请求加 `stream_options.include_usage`；最后一块 SSE 常带 `usage`（OpenAI 兼容惯例） |
| Ollama | **中** | 无 usage 时记 `quality=missing`，可选用字符估算并标明，**禁止当真值展示** |
| Cursor Local | **中高，可做；要实测** | SDK 类型已有 `RunResult.usage`；Local 是否每次填满需在本机跑一轮确认。空则记 run 发生 + `quality=missing`，界面写「本次 SDK 未回传，请到 Cursor Settings → Usage 对照」 |
| Cursor 美金 | **低，本期不做主指标** | `UsageCost` / `get_usage()` 标了 Cloud-only |
| 人民币成本 | **中，P1** | 用 `config.yaml` 单价表估算，不调支付接口 |
| 多用户 | **低，P2** | 无登录；空 `user_id` 不能假装分人 |
| 历史补账 | **不可行** | 过去调用没存 usage，无法还原 |

**推荐开工条件：** P0 只保证「能记账 + 能看见」；Cursor 若 Local 不回传 usage，页面仍列出写码次数与时长，token 显示「未回传」，不阻塞上线。

---

## 5. 架构（服从铁律）

```text
聊天 / 审码 / 提交 / PCB / 讨论          写码确认后
        │                                    │
        ▼                                    ▼
 nl_engine._llm_call / stream          cursor_agent wait()
        │                                    │
        └──────────► usage_store.append ◄────┘
                         │
                         ▼
              engine/data/usage/events.jsonl
                         │
           ┌─────────────┼─────────────┐──────────────┐
           ▼             ▼             ▼              ▼
     GET /api/usage   引擎 SPA「用量」  设置「用量」   feature usage-stats
     （中文 tags）     ← 业务验收认引擎  并列插件市场    （P1，可选）
```

| 层 | 放哪 | 禁令 |
|---|---|---|
| 算数 / 账本 | `engine/app/usage/` | 禁止在 feature 里自己记一份 |
| 采集 | 只改 `_llm_call`、stream、`cursor_agent` 收尾 | 禁止每个车道复制粘贴记账 |
| 展示 | 引擎 SPA「用量」+ DSH 设置段「用量」 | 设置页只读拉引擎 API；不以打开聊天为验收 |
| Agent 查询 | `features/usage-stats`（P1） | 禁止 npm import；`runEngine(["usage-summary", …])` |
| 密钥 | 仍只在 `config.yaml` | 流水里只留 `model` / `provider`，禁止 key |

---

## 6. 数据模型

单条流水（JSONL，一行一事，`flock` 追加，与 `plugins.json` 同一套谨慎写盘习惯）：

```json
{
  "id": "usg_20260914_ab12",
  "ts": "2026-09-14T10:00:00+08:00",
  "source": "llm",
  "lane": "code_review",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "prompt_tokens": 1200,
  "completion_tokens": 800,
  "cache_read_tokens": 0,
  "cache_write_tokens": 0,
  "reasoning_tokens": 0,
  "total_tokens": 2000,
  "quality": "provider",
  "job_id": "crj-…",
  "ui_session_id": "",
  "user_id": "",
  "ok": true,
  "error_class": ""
}
```

| 字段 | 说明 |
|---|---|
| `source` | 只允许 `llm` \| `cursor` |
| `lane` | `chat` / `pcb` / `code_dev_discuss` / `code_dev_write` / `code_review` / `code_commit` / `config_test` |
| `quality` | `provider`（DeepSeek JSON）/ `sdk`（Cursor RunResult）/ `estimate`（字符估，须在 UI 打标）/ `missing` |
| `total_tokens` | 有则用供应商合计；否则各分项之和 |

日汇总（启动或查询时从 JSONL 滚出来，可缓存 `engine/data/usage/daily/YYYY-MM-DD.json`，丢了能重建）：

- `llm_tokens` / `cursor_tokens` / `by_lane` / `calls` / `missing_calls`

保留策略：流水默认 90 天；超期归档或删除在配置里写死，避免盘涨。配置中心测连通也记账，避免「测一下」变成无主消耗。

---

## 7. 采集怎么改（最小切口）

### 7.1 LLM（一处覆盖全车道）

1. `_llm_call` 解析 `r.json()["usage"]`，`append` 后再返回文本。  
2. 调用方传入 `lane=`（默认 `chat`）；审码/提交/PCB/讨论在现有调用点加关键字参数，**返回值仍是 `str | None`**，不改签名语义。  
3. `llm_freeform_stream`：payload 增加 `stream_options: {include_usage: true}`；读到 usage 后记账，并对调用方多 yield 一次 `{"type":"usage",…}`（调用方可忽略）。  
4. 无 usage：`quality=missing`；**不要**默默用 `(len+1)//2` 冒充真值。提交门禁里现有估算可标 `estimate` 作为对照，P0 仍以供应商为准。

### 7.2 Cursor 写码

在 `run_obj.wait()` 之后：

1. 读 `getattr(result, "usage", None)` 与流里 `type=usage` 消息（二者取非空、可相加但**禁止重复加**——P0 只取 `wait()` 结果，流事件作校验日志）。  
2. 写入 `job["cursor_usage"]`（便于单次写码页回看）并 `usage_store.append(source=cursor, lane=code_dev_write)`。  
3. 记下实际 `model`（含 Auto 回退）。  
4. **不要**调用 `agent.get_usage()`（Local 会报错）。  
5. 额度用尽：已有错误识别保留；另记 `ok=false, error_class=usage_limit`。

### 7.3 上下文（可选 P0）

用 `contextvars` 带 `lane` / `job_id`，避免改 `_llm_call` 的十几处调用漏传。漏传时 `lane=unknown`，仪表盘单独一列，方便补点。

---

## 8. 接口与页面

### 8.1 FastAPI（中文 tags）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/usage/summary` | 查询区间汇总：LLM / Cursor / 分车道 |
| GET | `/api/usage/events` | 最近 N 条流水（脱敏，无 key） |
| GET | `/api/usage/daily` | 按日序列，给折线 |

`tags=["用量统计"]`，参数：`from` / `to`（北京时间自然日）、`source`、`lane`。只读，无需 HITL nonce。

CLI 同源：`cli_ops` 增加 `usage-summary`，供以后 feature 调用。

### 8.2 引擎 SPA

配置中心旁加「用量」：

- 顶栏：今日 LLM token、今日 Cursor token、今日调用次数  
- 图：近 7 日两条线（LLM / Cursor）  
- 表：车道 × token × 次数；`missing` 单独提示  
- 文案：Cursor 与 LLM **不能直接加总成一笔钱**（计价主体不同）

验收看本机引擎口（如 `:8000`）。DSH 设置「用量」与「插件市场」并列，数据同源；改 client.js 后需重启宿主。

### 8.3 feature（P1）

`scripts/plugin.sh new usage-stats "查询本机 token 用量"`  
工具例：`mes_usage_summary`，description 写清「问本机引擎用量，不是 Cursor 官网」。

---

## 9. 分期

| 期 | 做什么 | 验收 | 预估 |
|---|---|---|---|
| **P0** | 采集 + JSONL + 三个只读 API + 引擎用量页 + 设置「用量」 | 跑一轮聊天/审码能看到 LLM 真值；跑一轮写码能看到 Cursor 流水（有 usage 或明确「未回传」）；设置左侧用量与插件市场并列 | 已落地 |
| **P1** | 单价表估算、CSV 导出、写码完成卡带本次 token、feature 查询、90 天清理 | 领导能导出一周表；Agent 能答「今天写码烧了多少」 | 2～3 天 |
| **P2** | 企业总账 + 按人日/月（共用公司 Key） | 管理页能看公司 LLM 合计与工号维度 | 另立项，见 [企业Token用量汇总方案.md](./企业Token用量汇总方案.md) |

P0 不改四车道确认卡主流程；P1 才在写码完成卡加一行用量。

---

## 10. 风险与对策

| 风险 | 对策 |
|---|---|
| Cursor Local `usage` 为空 | 先实测一轮；空则次数+时长+missing，不假装 0 token=没消耗 |
| DeepSeek 流式最后一块无 usage | 非流式路径已有；流式失败则该次 `missing`，不回填估算除非用户打开开关 |
| 审码 20 个批次 = 20 条流水 | 正确；汇总页按 `job_id` 可折叠 |
| 磁盘涨 | 日滚 + 90 天；单行很小 |
| 与 SSE `token` 搞混 | API/UI 一律写「token 用量 / prompt+completion」，禁止用事件名 `token` |
| 把两条账加总成人民币 | UI 拆开两张卡；P1 单价也分 `deepseek` / `cursor` 两套 |

---

## 11. 测试

- unittest：解析 DeepSeek `usage` 样例；无 usage → `missing`；Cursor usage 序列化；JSONL flock 追加。  
- 禁止用真实 Key 打付费单测；fixture JSON 即可。  
- 手工：`engine.sh ensure` 后聊天一句 + 写码一小改，用量页两条来源都有记录。

---

## 12. 建议拍板的三句话

1. **P0 做本机账本 + 引擎页**，不做人维度、不做自动停写。  
2. **LLM 以供应商 usage 为真值**；Cursor 以 SDK `RunResult.usage` 为准，拿不到就标明缺失，不编数字。  
3. **DSH 宿主聊天账单不进这本账**；要进再开 P2。

拍板后按 P0 开工：先改 `nl_engine` + `cursor_agent` + `usage_store`，再补 API 与 SPA。（P0 已落地）

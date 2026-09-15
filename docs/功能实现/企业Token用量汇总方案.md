# 企业 Token 用量汇总 · 实施方案

> **状态**：本机登录 P0 已落地；**本机上报 + 回环汇总 hub + admin 企业用量页**已落地（`usage/report.py`、`usage_hub.py`、`/api/usage-hub/v1/*`、`/api/usage/enterprise/*`）；默认 `report_enabled: false`；生产内网独立汇总服务可另拆  
> **范围**：同事共用**同一把公司 DeepSeek Key** 时，统计 **公司 LLM 总消耗** + **每人每日 / 每月**；Cursor 写码单独一列  
> **验收**：管理侧能按北京时间看到「全公司 LLM 合计」与「工号 × 日 / 月」；与 DeepSeek 控制台总额可对照（允许漏报窗口）；**不以打开聊天为成败**  
> **不包含**：把引擎改成公网多用户服务、改 Cursor 官网额度、自动扣费、按人限流停写（可后续加）

---

## 1. 一句话总结

供应商按 **API Key** 只给一笔总账，分不出张三李四。企业要「总消耗 + 每人每天每月」，只能：**本机继续记账 → 流水带工号 → 上报到内网汇总服务 → 管理页按人滚动**。本机引擎仍只绑回环，不新增业务 Cordis 包，不另造公网鉴权替代企业接入层。

---

## 2. 问题与边界（先判再做）

### 2.1 已经有的

| 能力 | 落点 | 局限 |
|---|---|---|
| 本机 LLM / Cursor 分账 | `engine/data/usage/events.jsonl` + `/api/usage/*` + 引擎页 / DSH「用量」 | 只看见**这一台机器** |
| 当月曲线、分时段、未回传标注 | 用量 UI | 无工号 |
| 流水字段 `user_id` | 模型里已留空 | 写码 Job 也是空串，**不能假装分人** |

### 2.2 供应商能给什么

| 账单 | 谁出 | 能不能按人 |
|---|---|---|
| DeepSeek（公司 Key） | 控制台按 **Key** | **不能**。全公司共用一把 Key = 一笔总额 |
| Cursor 写码 | 各人 Cursor 账号额度 | 与公司 Key **不是一笔钱**，禁止加总成「公司 Key 总消耗」 |
| Ollama 本机 | 通常不计云费用 | 可记次数，管理页单独标注「不计 Key」 |

对照验收（管理页 LLM 合计 vs DeepSeek 控制台）：

> 各机上报的 LLM `total_tokens` 之和 ≈ 同期控制台；对不上**人**是供应商能力问题；对不上**总额**才是漏采 / 重复上报。

### 2.3 明确不做

- 不把 `runtime.yaml` host 改成 `0.0.0.0`「方便同事连一台引擎」。  
- 不在业务里偷偷焊一套引擎 HTTP Token 头替代企业 SSO（见 `docs/安全/企业级安全加固方案.md`：对外暴露 = 企业接入另立项）。  
- 不用操作系统用户名冒充工号（共享机、装包用户名不一致会串账）。  
- 不把各人 JSONL 用网盘对拷再手工加总。  
- 不改 DSH / 插件源码；DSH 会话采集仍只读 `~/.dsh/sessions`。  
- 不新增第二个 bridge / 正式 Cordis 包。  
- 上报失败**不得**让聊天 / 写码 / 审码失败。

---

## 3. 目标

### 3.1 产品口径（给领导）

1. **公司 LLM 总消耗**：所有已上报、带工号的 LLM 流水之和（北京时间日 / 月）。  
2. **每个人每天 / 每月**：同一口径的 LLM；Cursor 另列，文案写清「不是公司 Key」。  
3. **本机用量页按账号**：登录 hebo 只看 hebo；登录 admin 只看 admin；历史无账号流水一次性归到 hebo。  
4. **无工号不上报**：本机未登录产生的流水 `user_id` 为空 → **不上报**（与原方案一致）。

### 3.2 技术目标

1. 每条本机流水有稳定 `user_id`（工号）+ 原有 `id`（上报去重）。  
2. 本机增量上报到内网汇总；用事件 `id` 幂等，重装电脑不把同一天加两次。  
3. 汇总可查：全公司 LLM、按人按日、按人按月；LLM / Cursor 分列。  
4. 密钥仍只在各机 `config.yaml`；上报包**禁止**带 API Key。

---

## 4. 架构（服从铁律）

```text
同事 A 本机                  同事 B 本机
引擎 :8000 只绑回环            同上
events.jsonl + user_id         同上
        │ 定时/开机增量 POST（只出）
        └────────────┬────────────┘
                     ▼
           公司用量汇总（内网）
           去重(id) · 按人滚日/月
                     │
                     ▼
           管理页（内网浏览器）
           总额 · 工号×日 · 工号×月
```

| 层 | 放哪 | 禁令 |
|---|---|---|
| 本机采集 | 已有 `engine/app/usage/` | 禁止 feature 再记一份 |
| 工号 | `config.yaml` → 写流水 `user_id` | 禁止写进 feature / README |
| 上报 | 引擎后台任务（`usage/report.py` 一类） | 禁止 Node `spawn`；失败只打日志 |
| 汇总真相 | **内网独立小服务**或现有 MES 库表 | 禁止把各机引擎端口暴露到公司网当「总账」 |
| 管理 UI | 汇总服务自己的页，或后续引擎 SPA「企业用量」（仅管理员本机反代后访问） | 不以打开 DSH 聊天为验收 |
| 企业 SSO | 汇总服务 / 反代，**单独立项** | 禁止焊进 mes-bridge |

推荐默认：**新建内网「用量汇总」HTTP 服务**（与 WorkBuddy 引擎分进程）。同事电脑不出网段即可；WorkBuddy 仓只负责本机侧（工号 + 上报客户端）。若公司已有 MES 且能加表，汇总也可落 MES，本仓仍只 `POST` JSON，不把 MES SDK 塞进 `features/`。

---

## 5. 身份（已拍板方向 · 本机登录，不做 Feature）

没有稳定用户 ID，后面的日/月表都是假的。身份是**控制面**，不是业务热插拔能力。

### 5.1 对照 simplified-workbuddy（可抄什么、不可抄什么）

路径：`/Users/hebo/WorkBuddy/2026-07-23-09-13-55/simplified-workbuddy`

| 项 | simplified | 本仓怎么用 |
|---|---|---|
| 登录页 UI | Vue `LoginView.vue`（品牌卡 + 账号密码） | **可抄版式/文案结构**，落到引擎 SPA（静态 HTML/CSS），不必引 Vue |
| 会话 | 本地 HS256 JWT，`localStorage` + `Authorization: Bearer` | **可抄模式**：引擎签发短时会话，前端存 token |
| 验密 | **转发外部 ERP**（无本地用户表）；沙箱任意密码 | **不可照搬**：同事共用本仓时没有那套 ERP；须**本机用户库** |
| 注册 API | 无 | 本仓做**种子账号**（首次启动写入），开放自助注册可 P1 |
| 绑定 | API 默认 `0.0.0.0` | **禁止**：引擎仍只绑 `127.0.0.1` |

结论：**抄登录体验与 JWT 会话形态；鉴权真相做在本仓引擎，不代理外部平台。**

### 5.2 为什么不用 Feature 插件

| 若做成 `features/auth` | 问题 |
|---|---|
| feature 禁止 `import` npm、不能当安全真相源 | 密码哈希、用户库、签发会话必须在引擎 |
| 热插拔可被 disable | 身份被关掉 → 用量 `user_id` 又变空，企业总账失效 |
| AGENTS：密钥/控制面进 `engine/` | 登录属于控制面，与 HITL / config 同级 |
| simplified 自己也写明 | auth **不**拆进业务插件 |

| 层 | 放哪 |
|---|---|
| 用户库 / 验密 / 签发会话 / `/api/auth/*` | **`engine/app/auth/`** |
| 登录页 | **引擎 SPA `:8000` 全屏**；**宿主 `:3081` 由 mes-bridge 挂全屏挡板**（版式对齐 simplified LoginView） |
| DSH 侧栏「用量」 | 已登录后只读展示；退出登录会重新拉起挡板 |
| Feature | **不建** `features/login` |

可选 P1：mes-bridge 设置段加「当前账号 / 退出」，数据仍来自引擎。

### 5.3 本机用户库（P0）

- 文件：`engine/data/auth/users.json`（或 sqlite），**gitignore**（与 `usage/` 同策略）。  
- 密码：只存哈希（如 `hashlib.scrypt` / bcrypt），禁止明文。  
- 会话：HS256 JWT（secret 在 `data/auth/` 或 `config.yaml` 的 `auth.jwt_secret`，gitignore）。  
- 接口（中文 tags「账号」）：`POST /api/auth/login`、`GET /api/auth/me`、`POST /api/auth/logout`（可只作客户端清 token）。  
- 登录成功后：`user_id` = 稳定内部 ID（或 username 规范化字符串）；用量 `append_event` 读当前会话，不再靠手填工号。

### 5.4 种子账号（首次启动写入，已有则跳过）

| 用户名 | 密码（仅首次种子） | 角色 | 用途 |
|---|---|---|---|
| `admin` | `admin123` | `admin` | 看企业汇总、管用户（P1） |
| `hebo` | `hebo123` | `user` | 普通同事用量身份 |

说明：种子密码只用于本机/内测；正式推广须强制改密或关掉种子。文档与示例**可写用户名**，**不要**把生产密码写进 git 里的非 example 文件；种子逻辑写在引擎代码里，或 `config.example.yaml` 注明「首次启动内置演示账号」。

### 5.5 与用量的衔接

```text
打开宿主 http://127.0.0.1:3081（或引擎 http://127.0.0.1:8000）
    → mes-bridge client immediately 加载 → 全屏登录挡板（DOM + 可选 shell.overlay）
    → 无有效 mes_auth_session？ → 登录页（版式对齐 simplified LoginView）
    → POST 引擎 /api/auth/login → JWT 写入本源 localStorage
    → 挡板消失，进入宿主主界面 / 引擎主页
    → token 过期或退出登录 → 挡板再次出现
```

未登录：看不到主页；本机后台若无 active 会话则流水 `user_id` 为空 → **不上报**。  
管理员看「每人每日/每月」：P0 可先在引擎 SPA 用 admin 会话；全公司汇总服务仍按企业方案后续做。

### 5.6 明确不做（本阶段）

- 不把登录做成 `features/*`。  
- 不把引擎绑到 `0.0.0.0` 当「公司统一登录机」。  
- 不照搬 simplified 的 ERP 代理登录（除非另立项接公司 IdP）。  
- 不用操作系统用户名冒充 `user_id`。

---

## 5b. 备选（已否决作主路径）

| 方案 | 为何不作主路径 |
|---|---|
| 本机手填工号 | 可作无登录时的降级，但你已要求登录出 ID |
| 仅 Feature 登录壳 | 无验密真相，不安全 |

---

## 6. 数据模型

### 6.1 本机流水（增量字段）

在现有 JSONL 上补齐（缺省兼容旧行）：

```json
{
  "id": "usg_20260914_ab12",
  "ts": "2026-09-14T10:00:00+08:00",
  "source": "llm",
  "lane": "dsh_chat",
  "user_id": "E01234",
  "machine_id": "mch_…",
  "prompt_tokens": 1200,
  "completion_tokens": 80,
  "cache_read_tokens": 0,
  "total_tokens": 1280,
  "quality": "session",
  "reported_at": null
}
```

| 字段 | 说明 |
|---|---|
| `user_id` | 工号；空 = 只留本机、不上报 |
| `machine_id` | 本机稳定 ID |
| `reported_at` | 成功上报时间；空表示待报 |
| `id` | 全局去重键；汇总侧 `UNIQUE(id)` |

旧事件无 `user_id`：补工号后**不回填历史**（无法证明当时是谁）。从配置工号的那天开始进总账。

### 6.2 上报批次

```json
{
  "schema": 1,
  "machine_id": "mch_…",
  "user_id": "E01234",
  "events": [ { "id": "usg_…", "ts": "…", "source": "llm", "…token 分项" } ]
}
```

单批建议 ≤ 200 条；按 `id` 升序。汇总应答：`{ "ok": true, "accepted": ["usg_…"], "duplicate": ["usg_…"] }`。本机把 accepted/duplicate 都标 `reported_at`，避免死循环。

禁止上报：API Key、`config.yaml` 全文、会话原文、绝对路径。

### 6.3 汇总库（建议）

| 表 | 作用 |
|---|---|
| `usage_events` | 明细；主键 `id`；索引 `(user_id, ts)`、`(source, ts)` |
| `usage_day` | 物化：`user_id × 自然日 × source` → tokens / calls / missing_calls |
| `usage_month` | 物化：`user_id × YYYY-MM × source` |

自然日一律 **Asia/Shanghai**，与本机 `summarize` 一致。物化可用上报时增量更新，丢了能从 `usage_events` 重建。

公司总额 = `SUM(usage_day.tokens) WHERE source='llm'`（选定日期范围）。  
每人每天 = 该 `user_id` + `source` + `date`。  
每人每月 = `usage_month` 或对 `usage_day` 按月 `SUM`。

Cursor 行 `source='cursor'` **永不计入**「公司 Key 总额」卡片。

---

## 7. 本机怎么改（WorkBuddy 仓）

### 7.1 配置

`engine/config/config.example.yaml` 增加（真值只在 gitignore 的 `config.yaml`）：

```yaml
usage:
  user_id: ""          # 工号，空则不上报
  display_name: ""     # 可选，仅本机展示
  report_enabled: false
  report_url: ""       # 内网汇总根 URL，如 http://usage.corp.local
  report_token: ""     # 汇总服务下发的机器票据，不是 DeepSeek Key
```

`report_token` 与 LLM Key 同级保密：只进 `config.yaml`，日志 / SSE / 上报失败文案禁止回显。

配置中心：工号输入框 +「上报开关」（默认关）。改配置走现有 PUT，须符合企业加固（变异接口同源 / 票据），**不要**为用量另开一套鉴权。

### 7.2 写流水

`append_event` 自动带上当前 `usage.user_id` 与 `machine_id`。  
`nl_engine` / `cursor_agent` / DSH ingest **不必**每个调用点传人。

### 7.3 上报任务

- 触发：`summarize()` 开头（已有 ingest 节流）或独立 60s 节流；引擎启动后延迟一次。  
- 条件：`report_enabled` 且 `user_id` 合法且 `report_url` 非空。  
- 选出 `reported_at is null` 且 `user_id` 非空的事件。  
- HTTP：仅内网 URL（scheme http/https，host 禁止指向公网 IP 段可作 P1 加强）；超时短（如 5s）；失败下次再报。  
- 实现放 `engine/app/usage/report.py`，由 `store.summarize` 或 startup 调用，try/except 吞掉。

### 7.4 本机 UI

用量页可显示「本机工号：E01234 · 待上报 N 条」；**不**在本机画全公司表（数据不在本机）。

### 7.5 单测

- 无工号：上报函数 0 次 HTTP。  
- 有工号：fixture 事件被打包，`id` 去重后不再出现。  
- 禁止真实外网；mock `urlopen`。

---

## 8. 汇总服务（可本仓 `scripts/` 原型，生产可独立部署）

### 8.1 职责

1. `POST /v1/usage/ingest`：校验机器票据，按 `id` 插入，重复则 duplicate。  
2. `GET /v1/usage/company?from=&to=`：公司 LLM 总额 + 调用次数（可选 Cursor 合计但分字段）。  
3. `GET /v1/usage/people?from=&to=&grain=day|month`：每人序列。  
4. 只绑内网或 `127.0.0.1` + 反代；**不要**教用户把 WorkBuddy 引擎端口映射出去。

中文 tags/summary 与引擎 API 同一套文档习惯。

### 8.2 机器票据（P0 即可用）

汇总侧预置「工号 → ingest token」或「一机一票」。本机 `report_token` 对应该票。P0 不做员工登录管理页；管理页先内网 IP 白名单或反向代理基本认证，P1 再接 SSO。

### 8.3 管理页最低集合

| 块 | 内容 |
|---|---|
| 顶栏 | 所选月公司 LLM tokens、请求次数；旁注「对照 DeepSeek 控制台」 |
| 人 × 月 | 表：工号、LLM tokens、LLM 次数、Cursor tokens（单独列）、未回传次数 |
| 人 × 日 | 选人后当月日历/柱，与本机当月图同一套日粒度 |
| 分账声明 | LLM 与 Cursor 不能加总成一笔钱 |

验收认该页数字，不认聊天窗口。

---

## 9. 分期与工作量

| 期 | 做什么 | 验收 | 预估 |
|---|---|---|---|
| **P0** | **本机登录身份**（引擎用户库 + 登录页 + 种子 admin/hebo）→ 流水带 `user_id`；上报客户端；汇总 ingest + 日/月；最小管理页 | 登录后用量流水有稳定用户；两账号可区分；Cursor 不进公司 Key 总额 | 身份 2～3 天 + 上报汇总 3～5 天 |
| **P1** | 配置中心填工号；待上报条数；管理页按日下钻；CSV；与控制台对账说明 | 领导能导出「上月每人 LLM」 | 2～3 天 |
| **P2** | SSO 注入工号；IP 白名单收紧；阈值邮件（只告警不自动停写） | 换电脑工号仍连续 | 随企业接入 |

P0 开工前必须拍板：**工号用方案 A 还是等 SSO**，以及 **汇总落独立服务还是 MES**。

---

## 10. 与本机方案的关系

| | 本机 [Token消耗统计分析方案.md](./Token消耗统计分析方案.md) | 本方案 |
|---|---|---|
| 账本 | 每机 JSONL | 汇总库 + 本机仍保留 |
| 人 | 无 | 工号 |
| 界面 | 同事自己看 | 管理员看全公司 |
| 引擎绑定 | `127.0.0.1` | **不变** |
| Cursor | 本机一列 | 总账里单独一列 |

本机 P0 已完成的采集、分账、当月图**不推倒**；企业侧只加身份与上报。

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| 同事漏填工号 | 不上报；管理页「覆盖人数」与安装数对照；配置中心提示 |
| 两台电脑填同一工号 | `machine_id` 可查；制度上一人一工号 |
| 漏报（关机、内网断） | 待上报队列；总额对照 DeepSeek，差多少就是窗口内未报 |
| 重复上报 | `id` 唯一；duplicate 也算成功 |
| 把 Cursor 加进公司 Key | UI 两张卡 + 汇总 SQL 默认 `source=llm` |
| 上报打到公网 | P0 文档约束内网 URL；P1 校验 host |
| 票据写进日志 | 与 API Key 同一脱敏规则 |
| 历史无法补人 | 文档写死：工号生效日之后才进总账 |

---

## 12. 测试与验收清单

**本机**

- [ ] `user_id` 空：JSONL 仍增加，无 HTTP 上报  
- [ ] `user_id` 合法且开关开：mock 汇总 200 后 `reported_at` 有值  
- [ ] 上报包无 Key、无会话正文  
- [ ] 聊天/写码在汇总宕机时仍成功  

**汇总**

- [ ] 同一 `id` POST 两次，tokens 不双计  
- [ ] 两人同日 LLM 合计 = 公司当日 LLM  
- [ ] Cursor 事件进库但不进「公司 Key」卡片  
- [ ] 日 / 月与北京时间自然日一致  

**手工（两台机或两个 `user_id` 配置）**

- [ ] 各跑若干 LLM 调用后刷新管理页  
- [ ] 抽一天 DeepSeek 控制台总额与管理页 LLM 数量级一致  

---

## 13. 建议拍板的三句话

1. **身份走引擎本机登录**（抄 simplified 登录页体验 + JWT），**不做 Feature**；种子账号 `admin` / `hebo`。  
2. **总账不在供应商、在上报**：DeepSeek 只负责 Key 总额对照；人维度以登录 `user_id` + 事件 `id` 为准。  
3. **引擎继续只绑回环**；LLM / Cursor 分列；从能登录那天起算企业账，不补历史。

拍板后开工顺序：`engine/app/auth/`（用户库 + login/me）→ 引擎 SPA 登录页 → `append_event` 带会话用户 → 再接上报与汇总。

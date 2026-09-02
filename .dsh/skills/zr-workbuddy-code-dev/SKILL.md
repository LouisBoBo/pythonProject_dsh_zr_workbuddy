---
name: zr-workbuddy-code-dev
description: >-
  ZR-WorkBuddy 本机写码 HITL：需求收集、确认卡、brief 保真，确认后才可调
  mes_code_dev_start。配合 code-dev feature；禁止未确认启动 Cursor Local。
---

# 本机写码（HITL）

配合 feature **code-dev** 注册的 `mes_code_dev_*` 工具。  
聊天面板有专用确认卡与进度流；Agent 须遵守同一套门禁。

## 何时进入写码流程

- 用户要 **改代码、加页面、做报表 UI、修 bug、续改某模块**
- 明确指向 **本机工程目录** 的开发任务

**不要**用 `mes_ask` 代替写码；查数与改代码是两条车道。

## 硬性规则

1. **人先确认，再开工**  
   用户未在确认卡点确认、或未口头明确同意方案前，**禁止**调用 `mes_code_dev_start`。

2. **`mes_code_dev_start` 必须 `confirmed: true`**  
   工具层会拒绝 `confirmed=false`；Skill 不应教 Agent 绕过。

3. **保留原始诉求**  
   跨轮讨论时保留用户第一句原话（目标模块、业务名词）。  
   最终 `message` 应含 `【原始诉求】` 及目标路径/模块，避免泛化成无关 CRUD。

4. **不自动 commit**  
   写码 Job 只同步文件到 workspace；不要承诺已提交 Git。

5. **workspace 须为本机绝对路径**  
   不确定时先 `mes_code_dev_check`。

## 推荐流程

```text
mes_code_dev_status          → 写码是否就绪（开关、Key、SDK）
       ↓
收集需求 + 选项（面板或对话）→ 累积 brief / 原始诉求
       ↓
用户确认方案（确认卡）       → 面板 POST confirm；Agent 侧等价于 confirmed
       ↓
mes_code_dev_check(workspace) → 可选，校验目录
       ↓
mes_code_dev_start           → confirmed=true，message=已确认摘要
       ↓
mes_code_dev_job(job_id)     → 查进度与 synced_files
       ↓
（异常）mes_code_dev_cancel
```

## 工具速查

| 工具 | 用途 |
| --- | --- |
| `mes_code_dev_status` | 写码车道是否开启、Cursor 是否可用 |
| `mes_code_dev_check` | 校验 workspace 路径可否作为写码目标 |
| `mes_code_dev_start` | **仅确认后**启动 Cursor Local Job |
| `mes_code_dev_job` | 查询任务状态、步骤、同步文件列表 |
| `mes_code_dev_cancel` | 取消进行中的 Job |

### `mes_code_dev_start` 参数

- `workspace`：本机工程绝对路径
- `message`：用户已确认的改码需求摘要（含原始诉求与目标模块）
- `confirmed`：必须为 `true`

## 与聊天面板的关系

- 面板内写码走 **讨论 → 选项 → 确认卡 → SSE 进度**；Agent 不要抢跑 start。
- 用户在面板已确认并开工后，Agent 可用 `mes_code_dev_job` 辅助解读进度。
- 若用户只在 DSH 对话里说「开始写吧」但面板未确认，仍应先走确认，再 start。

## 前置条件

1. Feature 已启用：`scripts/plugin.sh --app zr-workbuddy enable code-dev`
2. 引擎配置中心 → **写码车道** 已开启
3. 引擎在跑：`scripts/engine.sh zr-workbuddy ensure`

任一不满足时，先 `mes_code_dev_status`，按返回提示排查，勿强行 start。

## Feature 未启用

工具列表中无 `mes_code_dev_*` 时，说明 code-dev 未加载。  
启用 feature 并打开写码开关后重试；**无需重启 DSH**（bridge ~1s 热插拔）。

## 写码 Skill 链（按阶段）

| 阶段 | Skill | 作用 |
| --- | --- | --- |
| 需求收集 | **zr-workbuddy-requirements** | 选项、brief 保真、防泛化 CRUD |
| 陌生仓库 | **zr-workbuddy-repo-bootstrap** | 摸底后再出方案 |
| UI 定规格 | **zr-workbuddy-ui-product-design** | 登录/工作台/报表界面预期 |
| UI 实施底线 | **zr-workbuddy-ui-craft** | 硬伤清单、全栈 CRUD |
| 确认后实施 | **zr-workbuddy-coding-impl** | Cursor 沙箱内短清单 |

UI 任务：requirements → ui-product-design → 确认卡 → start（message 含界面规格 + craft 约束）。

## 勿做

- 未确认就 `mes_code_dev_start`
- 把「员工工时报表」类需求泛化成「通用消息中心 CRUD」
- 在 Skill 或对话里编造 Job 已完成/已 commit
- 在 feature 代码之外私接 Cursor 或引擎 HTTP（一律走已注册工具）

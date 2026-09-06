---
name: zr-workbuddy-code-dev
description: >-
  ZR-WorkBuddy 本机写码 HITL：用户要改代码/改页面/改菜单时，必须立刻调
  mes_code_dev_begin 出主聊天工具卡。禁止 Bash/Grep/Read 扫仓代写；
  禁止未确认调用 mes_code_dev_start。
---

# 本机写码（HITL）

配合 feature **code-dev** 的 `mes_code_dev_*`。  
**唯一主入口：`mes_code_dev_begin`** → 主聊天工具卡（选目录 → 梳理需求 → 确认 → Cursor Local）。

## 何时必须立刻 begin

用户说以下任一，**第一动作就是 `mes_code_dev_begin`**（可带 message=原话）：

- 写码 / 改代码 / 改页面 / 加功能 / 做报表页  
- **改菜单 / 挪菜单 / 菜单放到某某下**（如「物料出库要写在仓库管理菜单」）  
- 修 bug、续改某模块、Cursor 写码  

**不要**先 Think 很久、不要 Bash/`ls`/`find`、不要 Grep/Read 扫目标工程、不要自己改文件。

## 硬性规则

1. **主入口只能是 `mes_code_dev_begin`**  
   日常写码诉求禁止用 `mes_code_dev_status` / `check` 开场（排障才用）。

2. **禁止宿主侧代写**  
   禁止 Bash、Grep、Read、Write、StrReplace 去摸/改用户工程来「完成写码」。  
   改盘只允许工具卡确认后的 Cursor Local Job。

3. **人先确认，再开工**  
   未在工具卡确认前，**禁止** `mes_code_dev_start`。

4. **`mes_code_dev_start` 必须 `confirmed: true`**  
   仅工具卡已确认、需 Agent 代调时使用。

5. **不自动 commit**  
   写码只同步到 workspace；提交走 `mes_code_commit_begin`。

6. **workspace 用 DSH 已选工作区或用户绝对路径**  
   不确定时可把用户原话放进 `message`，目录交给工具卡默认填充。

## 正确流程（短）

```text
用户说写码/改菜单
    → mes_code_dev_begin（message=用户原话）
    → 主聊天工具卡：目录已填 → 梳理需求 → 选项/确认卡
    → 用户点确认 → Cursor Local + SSE 进度
    → （可选）mes_code_dev_job 看进度
```

## 工具速查

| 工具 | 用途 |
| --- | --- |
| **`mes_code_dev_begin`** | **写码主入口**；出工具卡 |
| `mes_code_dev_status` | 排障：车道是否就绪 |
| `mes_code_dev_check` | 排障：校验路径 |
| `mes_code_dev_start` | **仅确认后**启动 Job |
| `mes_code_dev_job` | 查进度 / synced_files |
| `mes_code_dev_cancel` | 取消进行中 Job |

## 与子 Skill 的关系

`zr-workbuddy-requirements` / `ui-*` / `coding-impl` 描述的是**工具卡内** Cursor/引擎讨论规范，  
**不是**让 DSH Agent 先用 Bash 摸底。Agent 侧仍然：**先 begin，再闭嘴等卡**。

## 勿做

- 用长链路 Think + Bash + Grep「分析完再写」代替 `mes_code_dev_begin`  
- 未确认就 `mes_code_dev_start`  
- 承诺已 commit / 已上线  
- 在 feature 外私接 Cursor 或引擎 HTTP  

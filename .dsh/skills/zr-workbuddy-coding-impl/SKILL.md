---
name: zr-workbuddy-coding-impl
description: >-
  写码实施短清单：少扫描、锁定目标文件、全栈 CRUD 同轮补 API、最小验证。
  Cursor Local Job 实施阶段参考；P0-1 不自动 git commit。
---

# 开发实施（短清单）

借鉴 simplified **ai-coding-implementation**，适配 ZR-WorkBuddy 本机写码链路。

## 何时启用

- 用户 **已确认** 写码方案，`mes_code_dev_start` 已启动或即将启动  
- Cursor 在沙箱内实施复杂业务改码  
- **需求未确认前不要读**（先用 zr-workbuddy-requirements）

## 实施步骤

1. **先锁定目标文件**（glob/grep），不要反复全仓扫描。  
2. **只改本轮需求**；未点名页面/模块不动。  
3. **新建业务菜单/CRUD 页** 且仓库已有后端时：  
   同轮补 **API（路由+模型/schema）+ 前端 api 封装**；不要只写假数据。  
   纯样式微调不要碰后端。  
4. **改完跑最小验证**（单测或关键路径）；失败只修相关文件。  
5. **P0-1 不自动 commit/push** — 完成后汇报 `synced_files`；提交等 P0-2 人确认。  
6. **有界面规格时**：先对齐 zr-workbuddy-ui-craft，再写 UI。

## 与 write_scope 的关系

引擎可能按目标模块限制同步路径（如 `reports/`）。  
requirement 里写清 **目标模块与预期路径**，避免改到 messages 等无关目录。

## 陌生仓库

先读 **zr-workbuddy-repo-bootstrap** 或快速浏览：

- `README`、依赖清单、前后端入口  
- 现有路由/侧栏/同类页  
- 测试命令  

再动手；不要在不熟结构下大面积改。

## 禁止

- 为「通过清单」返工用户未点名的已完成页  
- 扩展无关重构  
- 在 Job 外私改 workspace（一律走沙箱→同步）  
- 声称已 commit（P0-1 未开提交车道）

## 相关 Skill

- **zr-workbuddy-code-dev** — 工具与 HITL  
- **zr-workbuddy-ui-craft** — UI 硬伤  
- **zr-workbuddy-requirements** — 需求保真

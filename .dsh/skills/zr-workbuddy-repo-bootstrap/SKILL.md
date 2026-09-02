---
name: zr-workbuddy-repo-bootstrap
description: >-
  本机工程首次摸底：技术栈、目录、启动与测试方式。陌生仓库写码前先分析；
  先形成方案再等用户确认，禁止贸然大面积改文件。
---

# 本机工程首次分析

借鉴 simplified **repo-bootstrap-analysis**，适配 WorkBuddy **本机 workspace**（非 DeepAgents 虚拟路径）。

## 何时启用

- 第一次在某 **本机绝对路径** 上写码  
- 用户说「不熟这个仓库 / 先分析结构 / 怎么启动」  
- 生成技术方案前  
- **已熟悉的增量小改** 通常不需要全文读取

## 1. 确认 workspace

- 路径须为 **本机绝对路径**（如 `/Users/…/project`）  
- 可用 `mes_code_dev_check` 校验是否可作为写码目标  
- 不要把引擎目录、`.dsh`、`node_modules` 当业务源码

## 2. 优先读取（按存在性）

| 目标 | 常见位置 | 判断内容 |
| --- | --- | --- |
| 项目说明 | `README.md`、`docs/` | 用途、启动方式 |
| Python | `pyproject.toml`、`requirements.txt` | 依赖、测试命令 |
| Node/前端 | `package.json`、`vite.config.*` | 框架、脚本 |
| 后端入口 | `main.py`、`app/`、`routers/` | FastAPI/Flask 等 |
| 前端入口 | `src/`、`views/`、`router/` | 页面与路由结构 |
| 测试 | `tests/`、`pytest.ini` | 最小验证命令 |
| 配置 | `.env.example`、`config/` | 环境变量边界 |

## 3. 分析输出（中文，有证据）

至少包括：

1. **定位**：本地路径、是否 git 仓库  
2. **技术栈**：前后端、数据库、测试框架  
3. **目录结构**：关键目录职责  
4. **启动/测试**：推断命令；不确定则标明  
5. **改造风险**：不宜贸然修改的模块  
6. **下一步**：形成方案 → **等用户确认** → 再 `mes_code_dev_start`

## 4. 生成方案时

1. 先完成摸底  
2. 候选路径 + 推荐方案与理由  
3. 预计修改文件、验证命令、风险点  
4. 询问用户是否确认实施  

**确认前禁止** 调用 `mes_code_dev_start`（`confirmed=true` 也须人先同意方案）。

## 5. 与需求 skill 的配合

摸底结论并入 **requirement 摘要** 的「目标文件/路由」段，  
与 **zr-workbuddy-requirements** 的【原始诉求】一起进确认卡。

## 相关 Skill

- **zr-workbuddy-requirements** — 收集与保真  
- **zr-workbuddy-code-dev** — 确认后开工  
- **zr-workbuddy-coding-impl** — 实施清单

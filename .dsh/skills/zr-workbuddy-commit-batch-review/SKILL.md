---
name: zr-workbuddy-commit-batch-review
description: >-
  提交前本批代码门禁审核（code-commit 专用）。仅由引擎提交门禁 API 调用；
  禁止在 code_review 全量审码车道自动选用。不输出「代码审核汇总报告」终稿，
  只输出结构化过程步骤与 findings（供确认卡展示）。
disable-model-invocation: true
version: 1.0.0
---

# 提交批审（code-commit 门禁 · 非全量审码车道）

## 路由（硬）

| 项 | 约定 |
|----|------|
| **触发** | 用户「提交代码」→ 选目录确认卡 → `POST /api/code-commit/start` |
| **禁止** | `workbuddy_lane=code_review`、全仓 list、`## 代码审核汇总报告` |
| **与全量审码关系** | 共用严重度与检查面；**路由完全独立** |

## 审什么

- **仅**调用方传入的本批相对路径（Git dirty 业务源码 / 写码同步池）
- 不得擅自扩大成全仓；未在本批的文件写「未覆盖」

## 怎么做（专业度）

1. 读 `references/checklist.md`（gate-90 本批版）与 `references/output-schema.md`
2. 对本批每个文件按检查面扫描（正确性 / 安全 / 注入 / 密钥 / 并发 / 日志脱敏）
3. 敏感路径（`.env`、密钥文件）→ 直接 P0 阻断
4. P0/P1 → `blocking: true`；P2 → 警告，不阻断提交

## 输出（硬）

- **只输出 JSON**（见 output-schema），中文
- **禁止** Markdown 报告壳、禁止四段式长文修复（那是全量审码 Skill 的事）
- 必须有：`process_steps`（审核过程）、`summary`（结论）、`findings`、`file_scans`

## 结论用语

- 通过：`未发现阻断或警告 —— 可提交`
- 有警告：`无阻断，N 条警告 —— 确认后可提交`
- 阻断：`N 条阻断 —— 禁止提交`

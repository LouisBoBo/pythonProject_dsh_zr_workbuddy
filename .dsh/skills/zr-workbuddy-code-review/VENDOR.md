# Vendor 说明

| 项 | 值 |
|----|-----|
| 上游 | [Viprasol-Tech/code-review-skill](https://github.com/Viprasol-Tech/code-review-skill) |
| 许可 | MIT（见 `LICENSE`） |
| 纳入文件 | `references/viprasol-skill.md`（上游原文）；`references/workbuddy-gate-90.md`（公司通用门禁叠层，与 simplified-workbuddy 同源） |
| 本地薄封装 | `SKILL.md`（触发 + 映射 + 本仓取码；**不改**上游检查项正文） |
| 迁入来源 | simplified-workbuddy `apps/agent/skills/code-review/` |

升级方式：用上游最新 `skill.md` 覆盖 `references/viprasol-skill.md`，并核对 LICENSE；门禁叠层与 simplified 对齐更新。

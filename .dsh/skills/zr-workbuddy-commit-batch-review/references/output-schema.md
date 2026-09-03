# 提交批审 JSON 输出（仅 API 解析，勿输出其它格式）

```json
{
  "verdict": "pass | warn | blocked",
  "summary": "中文一句话结论",
  "process_steps": [
    "① 范围：本批 N 个文件（非全仓）",
    "② 敏感路径：…",
    "③ 安全/注入：…",
    "④ 正确性：…"
  ],
  "findings": [
    {
      "severity": "P0 | P1 | P2",
      "path": "相对路径",
      "rule": "规则 id",
      "message": "中文，≤120 字",
      "blocking": true
    }
  ],
  "file_scans": [
    {
      "path": "相对路径",
      "status": "pass | blocked",
      "steps": ["① …", "② …"],
      "issues": ["简短问题"]
    }
  ]
}
```

规则：

- `blocking`：P0/P1 为 true，P2 为 false
- `file_scans` 须覆盖本批每个已读文件
- 无问题时 `findings` 可为 `[]`，`verdict=pass`

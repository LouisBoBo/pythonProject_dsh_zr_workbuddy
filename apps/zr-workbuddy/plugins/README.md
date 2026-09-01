# plugins（常驻层）

| 包 | 角色 |
|---|---|
| `mes-bridge` | **唯一** Cordis 常驻包（热插拔宿主 + 面板） |
| `mes-runtime` | 引擎 HTTP 调用库（非 Cordis） |

业务功能在 `../features/`：

```bash
scripts/engine.sh zr-workbuddy ensure
scripts/plugin.sh --app zr-workbuddy enable|disable <id>
scripts/plugin.sh --app zr-workbuddy new <id> "说明"
```

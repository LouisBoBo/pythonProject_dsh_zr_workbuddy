# ZR-WorkBuddy —— 引擎 + 唯一 bridge + 热插拔 features

应用目录为 `zr-workbuddy`（`scripts` / DSH 接线）；产品主旨是 **ZR-WorkBuddy**。

| 目录 | 角色 | 生命周期 |
|---|---|---|
| `engine/` | 业务引擎（HTTP） | `scripts/engine.sh` |
| `plugins/mes-bridge` | 唯一常驻 Cordis 包 | install 后重启一次 |
| `plugins/mes-runtime` | 库 | — |
| `features/*` | 业务能力 | **热插拔，不重启** |

## 日常

```bash
scripts/engine.sh zr-workbuddy ensure
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy disable mes-ask
scripts/plugin.sh --app zr-workbuddy enable mes-ask
scripts/plugin.sh --app zr-workbuddy new report "报表"
```

Agent 内可用工具 `mes_plugin`（list / enable / disable）。

## 首次接线

```bash
scripts/plugin.sh --app zr-workbuddy install bridge --restart
```

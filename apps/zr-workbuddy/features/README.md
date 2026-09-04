# ZR-WorkBuddy —— 引擎 + 唯一 bridge + 热插拔 features

服从 **三大核心目标**（[落地方案](../../../docs/三大核心目标落地方案.md)）：热插拔、按单元部署、第三方进 `features/`。

应用目录为 `zr-workbuddy`；产品主旨是 **ZR-WorkBuddy**（独立引擎网页为主入口）。

| 目录 | 角色 | 生命周期 |
|---|---|---|
| `engine/` | 业务引擎（HTTP + SPA） | `scripts/engine.sh` |
| `plugins/mes-bridge` | 唯一常驻 Cordis 包（热插拔宿主） | 接线升级时按需 |
| `plugins/mes-runtime` | 库 | — |
| `features/*` | 业务能力（含第三方） | **热插拔，不重启** |

## 日常（G1）

```bash
scripts/engine.sh zr-workbuddy ensure
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy disable mes-ask
scripts/plugin.sh --app zr-workbuddy enable mes-ask
scripts/plugin.sh --app zr-workbuddy new report "报表"
```

第三方：整目录符合契约后放入 `features/<id>/` 再 `enable`；一键 `install-feature` 见三大目标 G3。

## 首次接线 bridge（可选）

```bash
scripts/plugin.sh --app zr-workbuddy install bridge --restart
```

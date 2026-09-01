# ZR-WorkBuddy（应用目录 `zr-workbuddy`）

**DSH-ZR-WorkBuddy** 仓库下的业务应用：ZR-WorkBuddy 工作助手。  
应用目录 / `--app` 名为 `zr-workbuddy`；功能请只加在 [`features/`](features/README.md)。

```bash
scripts/engine.sh zr-workbuddy ensure
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy install bridge --restart
```

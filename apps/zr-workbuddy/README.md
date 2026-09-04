# ZR-WorkBuddy（应用目录 `zr-workbuddy`）

**DSH-ZR-WorkBuddy** 仓库下的业务应用：**ZR-WorkBuddy**。服从 [三大核心目标](../../docs/三大核心目标落地方案.md)（热插拔 / 增量部署 / 第三方 features）。  
应用目录 / `--app` 名为 `zr-workbuddy`；功能请只加在 [`features/`](features/README.md)。

```bash
scripts/engine.sh zr-workbuddy ensure
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy install bridge --restart
```

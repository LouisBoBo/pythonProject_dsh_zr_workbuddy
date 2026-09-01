# DSH-ZR-WorkBuddy

DSH 外挂应用仓库。产品主旨是 **ZR-WorkBuddy**（工作助手）。  
**框架只做接线与脚手架；端口 / 面板 / 业务配置 / LLM 都是各应用自己的事。**

## 分层（热插拔）

| 层 | 内容 | 重启？ |
|---|---|---|
| **框架** | `scripts/*`、`vendor/` | — |
| **常驻 bridge** | `plugins/mes-bridge`（唯一 Cordis 包） | 安装/升级时重启一次 |
| **热插拔 features** | `apps/<app>/features/*` | **否** |
| **引擎** | `engine/` HTTP | `engine.sh` 管理 |

## 日常

```bash
scripts/engine.sh zr-workbuddy ensure          # 确保引擎在跑
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy disable mes-ask
scripts/plugin.sh --app zr-workbuddy enable mes-ask
scripts/plugin.sh --app zr-workbuddy new report "报表"
```

引擎：`status` / `stop` / `restart` / `start`（前台）/ `start -d`（后台）  
兼容旧入口：`scripts/start-engine.sh zr-workbuddy`

首次 / bridge 变更：

```bash
scripts/plugin.sh --app zr-workbuddy uninstall legacy --restart
scripts/plugin.sh --app zr-workbuddy install bridge --restart
```

测试：`scripts/test.sh zr-workbuddy`  
约定：`AGENTS.md`  
目录与用法详解：[docs/目录结构与用法说明.md](docs/目录结构与用法说明.md)

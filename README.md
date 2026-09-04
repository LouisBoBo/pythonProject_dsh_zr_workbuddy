# DSH-ZR-WorkBuddy

**ZR-WorkBuddy** 工作助手（仓库名带 DSH，工程写法用其热插拔范式）。

**三大核心目标**（详见 [docs/三大核心目标落地方案.md](docs/三大核心目标落地方案.md)）：

1. **热插拔**：新能力只进 `features/`，启停约 1s  
2. **按单元增量部署**：改哪发哪（人确认后 rsync）  
3. **第三方插件**：像装技能一样装进 `features/`（校验 → 启用）  

业务验收以 **引擎网页 / API** 为准。

## 分层

| 层 | 内容 | 重启？ |
|---|---|---|
| **框架** | `scripts/*`、`vendor/` | — |
| **常驻 bridge** | `plugins/mes-bridge`（唯一 Cordis 包，热插拔宿主） | 升级接线时按需 |
| **热插拔 features** | `apps/<app>/features/*` | **否** |
| **引擎** | `engine/` HTTP + SPA | `engine.sh` 管理 |

## 日常

```bash
scripts/engine.sh zr-workbuddy ensure          # 确保引擎在跑
scripts/plugin.sh --app zr-workbuddy features
scripts/plugin.sh --app zr-workbuddy disable mes-ask
scripts/plugin.sh --app zr-workbuddy enable mes-ask
scripts/plugin.sh --app zr-workbuddy new report "报表"
# 第三方（规划/落地见三大目标 G3）：install-feature …
```

引擎：`status` / `stop` / `restart` / `start`（前台）/ `start -d`（后台）  
兼容旧入口：`scripts/start-engine.sh zr-workbuddy`

首次接线 bridge（可选，热插拔加载器用）：

```bash
scripts/plugin.sh --app zr-workbuddy install bridge --restart
```

测试：`scripts/test.sh zr-workbuddy`  
约定：`AGENTS.md`  
目录与用法：[docs/目录结构与用法说明.md](docs/目录结构与用法说明.md)  
落地方案：[docs/三大核心目标落地方案.md](docs/三大核心目标落地方案.md)

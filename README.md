# DSH-ZR-WorkBuddy

**ZR-WorkBuddy** 工作助手。自有业务在引擎；**真正的第三方 DSH 插件走 Studio 插件中心**（不能靠 `features/` zip）。口径见 [docs/产品与口径/最简产品形态.md](docs/产品与口径/最简产品形态.md)。

1. **热插拔（自有能力）**：`features/` 启停约 1s  
2. **按单元增量部署**：改哪发哪（人确认后 rsync）  
3. **第三方生态插件**：Harness Studio 插件中心安装进 Profile（这就是要 `host/` 的原因）  

业务验收看 **引擎网页 / API**；生态插件验收看 **Studio 插件中心「运行中」**。

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

自有功能包（**不是** DSH 生态插件）：

```bash
scripts/plugin.sh --app zr-workbuddy install-feature /path/to/workbuddy-feature.zip
```

DSH 第三方生态插件：先 `scripts/host.sh wire`，再在 **Studio 插件中心**安装（不要塞进引擎功能页）。

测试：`scripts/test.sh zr-workbuddy`  
约定：`AGENTS.md`  
**两种插件怎么走**：[docs/产品与口径/最简产品形态.md](docs/产品与口径/最简产品形态.md)  
**文档知识库（分类索引）**：[docs/README.md](docs/README.md)  
目录与用法：[docs/产品与口径/目录结构与用法说明.md](docs/产品与口径/目录结构与用法说明.md)  
落地方案：[docs/架构与选型/三大核心目标落地方案.md](docs/架构与选型/三大核心目标落地方案.md)

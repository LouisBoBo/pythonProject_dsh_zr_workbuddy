# ZR-WorkBuddy 对本目录的用法

> 上游完整说明见同目录 [`README.md`](./README.md)。  
> 版本与许可见 [`UPSTREAM.md`](./UPSTREAM.md)。  
> 产品方案见 [`docs/架构与选型/宿主二次开发-同仓host与部署方案.md`](../docs/架构与选型/宿主二次开发-同仓host与部署方案.md)。

## 目标

- 在本仓用源码维护宿主，部署到服务器后可用浏览器访问。  
- **自由安装第三方生态插件**（宿主插件中心 / `dsh plugin add` 一类能力）。  
- 业务仍在 `apps/zr-workbuddy/`，经 **Bridge** 挂载；不把业务写进本树。

## 当前阶段

- [x] 源码已导入 `host/`（无 `node_modules`）  
- [x] 本机 `pnpm install`（约 2.4GB；**未**默认启动桌面）  
- [x] Bridge / profile 接线（P2：`scripts/host.sh wire|verify`）  
- [x] 本机起 web 宿主（P2：默认 `start-web` → PATH `dsh`；引擎 `ensure-engine`）  
- [ ] 远端宿主部署（P3）  
- [ ] 将 `host/` 升到与本机全局 dsh 同主线后再用 `--from-host` 二次开发启动

## 日常入口（只开一个地址 · 主聊天）

**打开：http://127.0.0.1:3080** → **强制刷新** → 点 **「新会话」** → 在中间输入框直接说需求。

**配置中心（不必开 :8000）**：侧栏底 **「设置」** → 左侧导航与「通用 / 模型 / 插件」同级的 **WorkBuddy**（MES、LLM、写码/审码/提交/部署全车道）。保存走引擎 `/api/config` → `config.yaml`。

**写码必须出工具卡**：说「写码 / 改菜单 / …」时应立刻出现 **本机写码** 卡（`mes_code_dev_begin`）。若出现一长串 Bash/Grep 自扫工程，说明走错了——请 **新会话** 再说一遍；宿主已注入写码路由硬约束（改 bridge 后需重启过 `dsh web`）。

WorkBuddy 已挂成宿主 **Agent 工具**（不要找左侧工作区文件夹；**默认不再弹出**右下浮层面板）：

| 你想做的事 | 在主聊天里可以说 | 工具 |
| --- | --- | --- |
| 查数出图 | 「今天正在生产的工单有多少个」 | `mes_ask` |
| PCB 工艺 | 「飞针和 AOI 怎么分工」 | `mes_pcb` |
| 连接/状态 | 「测一下业务连接」 | `mes_config` / `mes_status` |
| 写码 / 审码 / 提交 / 部署 | 直接说目录与需求 | `mes_code_*` |
| **提交代码（主路径）** | 只说「提交代码」 | `mes_code_commit_begin` → **主聊天工具卡**：选目录→勾选文件→门禁→确认 commit/push |
| **审核代码（主路径）** | 只说「审核代码」 | `mes_code_review_begin` → **主聊天工具卡**：选目录→勾选文件→开审 |
| **本机写码（主路径）** | 「写码 / 改代码 / 改页面」 | `mes_code_dev_begin` → **主聊天工具卡**：选目录→填需求→确认后 Cursor 写码（不自动 commit） |
| 启停功能 | 「列出 mes 插件」 | `mes_plugin` |

**关于确认卡**：审码 / 提交 / 写码均在 **主聊天工具卡**（`tool.call.toolview`）里完成，不要用宿主「答题壳」。请**新开会话**并强制刷新后再试。

当前已启用：`mes-config` `mes-pcb` `mes-ask` `code-dev` `code-review` `code-commit` `code-deploy`。

## 本机依赖安装（按需，勿在业务机盲目全量装）


上游要求：**Node `^22.19.0 || >=24`**，**pnpm 11**（见根 `package.json` `packageManager`）。

```bash
cd host
pnpm install          # 依赖很大，请预留磁盘与时间
```

**注意：**

- 依赖写在 `host/node_modules`（已 ignore），**不**改 `apps/zr-workbuddy`。  
- 上游 `lefthook` 可能在**仓库根**生成示例 `lefthook.yml` 并往 `.git/hooks` 塞 hook——装完后应删除（勿提交）。

## P2 接线与启停

```bash
scripts/host.sh wire              # 写 ~/.dsh/link + profile Bridge（不重启）
scripts/host.sh verify            # link / patch / 引擎 / :3080
scripts/host.sh ensure-engine     # 业务引擎
scripts/host.sh start-web         # 默认全局 dsh → http://127.0.0.1:3080
scripts/host.sh stop-web
```

**版本坑（必读）：** 本仓 `host/` 钉的是 **0.1.0-rc.8**；若本机全局 `dsh` 已是 **0.1.1-rc.2**，credentials 为 `version`+`refs` 结构，源码 CLI（`start-web --from-host`）会报错，且还需 `pnpm run build`。日常装生态插件用默认 `start-web` 即可。

## 铁律

1. 新业务能力 → `apps/zr-workbuddy/features/`  
2. 唯一业务常驻 Cordis 包 → `mes-bridge`  
3. 改本树 → 在 `UPSTREAM.md` / 补丁说明可追溯  
4. 业务增量部署仍走现有 G2；本树发版单独做

## 辅助脚本

仓库根：`scripts/host.sh`（见上）。

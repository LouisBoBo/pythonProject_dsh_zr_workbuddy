# 聊天壳与宿主接线（本仓不放 DSH 源码）

> **状态**：2026-09-13 修订——撤掉同仓 `host/` Studio 源码树；聊天壳只认发行版 `dsh`  
> **产品口径**：研发本机工作台 `http://127.0.0.1:3081`（`DSH_HOME=~/.dsh`，profile 含 mes-bridge）。预发「一体入口」用于验收/运维。对外客户倾向 **桌面安装包**（内嵌 npm `@deepseek-ai/dsh`，不发 Studio 源码）。内部仍是引擎 + 壳两个进程。  
> **相关**： [三大核心目标落地方案.md](./三大核心目标落地方案.md) · [P1-自动化部署-按单元增量.md](../功能实现/P1-自动化部署-按单元增量.md) · [AGENTS.md](../../AGENTS.md) · [host维护与更新.md](../宿主与运维排障/host维护与更新.md) · nginx 示例 [`scripts/deploy/nginx-one-entry.example.conf`](../../scripts/deploy/nginx-one-entry.example.conf)

---

## 1. 一句话总结

本仓库只做 **WorkBuddy 业务**（`apps/zr-workbuddy/`：引擎 + `features/` + 唯一 Bridge）。  
聊天壳 / 插件中心用已经发布的 **`dsh` CLI**（本机 `npm i -g @deepseek-ai/dsh`，桌面包打进 `desktop/runtime/host`）。

**不做**：把 DeepSeek Harness Studio 源码树再拷进本仓 `host/`；不把业务焊进 Studio。

---

## 2. 为什么改口

原先同仓塞完整 Studio，是为了「二次开发壳」。实际日常只走 PATH 上的 `dsh`，源码树从未打过补丁，还占掉约 150MB git + 本机数 GB `node_modules`。

| 诉求 | 现在怎么满足 |
| --- | --- |
| 能聊天、能装生态插件 | 跑起来的 `dsh web` + `scripts/host.sh wire` |
| 三大目标 G1/G2/G3 | Bridge + `features/`；业务单元增量；契约包装 `features/`，生态包装插件中心 |
| 桌面一体包 | `scripts/package-desktop.sh` 安装 `@deepseek-ai/dsh` → `desktop/runtime/host`（gitignore） |
| 换皮 / 品牌位 | 走官方 slot（`mes-bridge` client）；不必 fork Studio |
| 改 DSH 内部实现 | **另开独立仓**；本仓不接 |

相对其它做法：

- **整包进 `vendor/`**：与「小依赖、少改 vendor」冲突 → **否**  
- **同仓 `host/` 源码树**：已证明用不上 → **已撤**  
- **只依赖发行版 dsh**：当前口径 → **是**

---

## 3. 目录（业务仓）

```text
DSH-ZR-WorkBuddy/
├── apps/zr-workbuddy/             # 业务：引擎 / features / mes-bridge
├── desktop/                       # 一体包；runtime/host 是打包产物不是源码
├── vendor/                        # 小依赖钉选，不放整宿主
├── scripts/host.sh                # 接线 + 用全局 dsh 启停 :3081
└── docs/                          # 本文等
```

**边界铁律：**

1. 新业务能力只进 `apps/zr-workbuddy/features/`。  
2. 唯一业务 Cordis 常驻包仍是 `mes-bridge`。  
3. `vendor/` 不扩成第二宿主树。  
4. **禁止**再把 Studio 源码导入本仓 `host/`。

---

## 4. 与三大核心目标的对应

| 目标 | 本方案下如何实现 |
| --- | --- |
| **G1 热插拔** | 宿主进程内挂 Bridge；`features/` 启停约 1s |
| **G2 增量部署** | 业务：现有 `feature:*` / `engine` / `bridge` 单元；聊天壳：远端装好 `dsh` 即可，不 rsync Studio |
| **G3 装第三方** | **生态 Cordis/Skill**：Studio 插件中心；**WorkBuddy 契约包**：`install-feature` → `features/` |

员工浏览器：

- 宿主 URL → 聊天壳、生态插件  
- 引擎 URL → 现有业务 SPA（可经 nginx 同域反代）

---

## 5. 部署模型（一体部署 · 一个入口）

```text
本机说「部署到预发」→ 确认一次
  → SSH/rsync 命中的业务单元（改哪发哪）
  → 远端收尾：引擎 ensure/restart + 聊天壳（dsh web）拉起
  → 浏览器只开 entry_url（nginx → 聊天壳）
```

```text
开发机（一份仓库）
  └─ code_deploy 一体车道 → 远端同一目录布局

服务器
  ├─ 聊天壳（PATH 上的 dsh）
  ├─ 引擎（apps/zr-workbuddy/engine）
  └─ nginx（可选）：/ → 聊天壳；/workbuddy/ → 引擎
     示例：scripts/deploy/nginx-one-entry.example.conf
```

| 变更类型 | 运维操作 | 是否重启引擎 | 是否确保聊天壳 |
| --- | --- | --- | --- |
| 只改某个 feature | 一次「部署」确认 | ensure 保活 | 一体模式下确保在跑 |
| 只改引擎 | 同上 | restart | 同上 |
| 改 bridge | 同上 | ensure | 重装 bridge + 重启壳 |
| 首次空目录 | 全量单元 + 同上收尾 | restart | 拉起 |

服务器装好 `dsh` + 一次 `scripts/host.sh wire` 即可。**不要**同步 Studio `node_modules`。

---

## 6. 本机日常

```bash
npm i -g @deepseek-ai/dsh          # 每台机器一次
scripts/host.sh wire
scripts/host.sh up                 # 引擎 + :3081
```

开发请开 `http://127.0.0.1:3081`。桌面一体包是另一套 `DSH_HOME`（默认 :13080），不要和浏览器开发壳混看会话。

已废弃：`scripts/host.sh start-web --from-host`。

---

## 7. 风险与约束

| 风险 | 对策 |
| --- | --- |
| 想改 Logo / 探索语 | 用官方 brand slot + 本仓 `mes-bridge` client，不 fork Studio |
| 想改 DSH 内部 | 独立仓维护 fork；本仓继续只接线发行版 |
| 业务渗进壳 | Code review / AGENTS 铁律 |
| 与「宿主可不上」口径 | 要生态插件就必须跑 `dsh`；纯引擎预发仍可只跑引擎 |

---

## 8. 一句话结论

**本仓 = WorkBuddy 业务；聊天壳 = 发行版 `dsh`。不再同仓养 Studio 源码。**

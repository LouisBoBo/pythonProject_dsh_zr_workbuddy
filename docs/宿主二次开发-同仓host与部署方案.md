# 宿主二次开发：同仓 `host/` 与业务挂载方案

> **状态**：P1 / P1b / **P2 接线已完成**；**一体部署（业务 code_deploy）已按「一次确认、一个入口」收尾**；P3 远端 nginx/首次装机仍可按运维清单手工做一次  
> **产品口径**：研发本机以 `http://127.0.0.1:3080` 为工作台（工作区=本机盘）。预发「一体入口」用于验收/运维，**不等于**把服务器家目录当日常工作区。对外客户下一阶段倾向 **桌面安装包**（本机用、不发全仓源码）。内部仍是引擎+壳两个进程。  
> **决策依据**：要「源码二次开发宿主 + 可装生态插件」，同时保留三大核心目标与现有业务增量部署  
> **上游导入**：`/Users/hebo/Downloads/deepseek-harness-studio-main` → `host/`（`@deepseek-ai/dsh-root@0.1.0-rc.8`，MIT）  
> **版本注意**：本机全局 `dsh` 现为 **0.1.1-rc.2**；`host/` 源码为 **0.1.0-rc.8**。P2 默认用全局 dsh 启 web（credentials `version`+`refs` 兼容）。源码 CLI（`start-web --from-host`）需先对齐版本并 `pnpm run build`，否则会失败。  
> **相关**： [三大核心目标落地方案.md](./三大核心目标落地方案.md) · [P1-自动化部署-按单元增量.md](./功能实现/P1-自动化部署-按单元增量.md) · [AGENTS.md](../AGENTS.md) · [host/WORKBUDDY.md](../host/WORKBUDDY.md) · [host/UPSTREAM.md](../host/UPSTREAM.md) · nginx 示例 [`scripts/deploy/nginx-one-entry.example.conf`](../scripts/deploy/nginx-one-entry.example.conf)

---

## 1. 一句话总结

在本仓库新建独立目录 **`host/`**，放入可二次开发的**完整宿主工程**（钉死上游版本，只改壳与薄补丁）；**卡业务仍全部留在** `apps/zr-workbuddy/`（引擎 + `features/` + 唯一 Bridge）。  
服务器上跑「宿主进程 + 引擎进程」，浏览器可访问；业务继续「改哪发哪」，宿主发版单独设计。

**不做**：把整宿主塞进现有 `vendor/`；不把业务焊进宿主源码。

---

## 2. 为什么用这种方式

| 诉求 | 本方案如何满足 |
| --- | --- |
| 源码二次开发外壳 | `host/` 内完整工程，可改可构建 |
| 随心装生态插件 | 服务器跑宿主后，用宿主侧安装能力（非引擎 zip 冒充） |
| 三大目标 G1/G2/G3 | Bridge + `features/`；业务单元增量；契约包装 `features/`，生态包装宿主 |
| 浏览器访问 | 部署后访问宿主 Web（+ 引擎业务页） |
| 好维护 | 宿主与业务分目录；`vendor/` 仍只放小依赖 |

相对其它做法：

- **整包进 `vendor/`**：与现有「小依赖、少改 vendor」冲突 → **否**  
- **宿主另起一个 Git 仓**：以后发版节奏差很多再拆；现阶段多仓成本高 → **暂不采用**  
- **只依赖官方安装包、不放源码**：无法满足源码二次开发 → **否**

---

## 3. 目标目录结构（确认后落地）

```text
DSH-ZR-WorkBuddy/
├── host/                          # 新建：完整宿主工程（上游钉版本 + 自有补丁）
│   ├── README.md                  # 上游版本、如何构建/启动、补丁说明
│   ├── UPSTREAM.md                # 上游仓库 / tag 或 commit / 许可
│   └── …                          # 宿主源码与构建文件（完整项目）
├── apps/zr-workbuddy/             # 不变：业务应用
│   ├── engine/
│   ├── features/
│   └── plugins/mes-bridge|mes-runtime
├── vendor/                        # 不变职责：小依赖钉选，不放整宿主
├── scripts/                       # 增补：host 构建/启动/部署辅助（确认后加）
└── docs/                          # 本文等
```

**边界铁律（写进 AGENTS，确认执行时同步）：**

1. 新业务能力只进 `apps/zr-workbuddy/features/`，禁止写进 `host/` 内核。  
2. 唯一业务 Cordis 常驻包仍是 `mes-bridge`；不在宿主里堆业务正式包。  
3. `vendor/` 不扩成第二宿主树。  
4. 改 `host/` 必须在 `host/UPSTREAM.md` / 补丁说明中可追溯。

---

## 4. 与三大核心目标的对应

| 目标 | 本方案下如何实现 |
| --- | --- |
| **G1 热插拔** | 宿主进程内挂 Bridge；`features/` 启停约 1s |
| **G2 增量部署** | **业务**：现有 `feature:*` / `engine` / `bridge` 单元不变；**宿主**：单独「宿主发版」（见 §5），不伪装成 `feature:*` |
| **G3 装第三方** | **生态 Cordis/Skill 包**：宿主侧安装（服务器上跑着的 `host`）；**WorkBuddy 契约包**：仍 `install-feature` → `features/` |

员工浏览器：

- 宿主 URL → 聊天壳、生态插件  
- 引擎 URL → 现有业务 SPA（可经 nginx 同域反代）

---

## 5. 部署模型（一体部署 · 一个入口）

运维视角（推荐）：

```text
本机说「部署到预发」→ 确认一次
  → SSH/rsync 命中的业务单元（改哪发哪）
  → 远端收尾：引擎 ensure/restart + 聊天壳（dsh web）拉起
  → 浏览器只开 entry_url（nginx → :3080）
```

内部进程仍是「壳 + 引擎」，但**不要做成两套产品发版**。增量只是少传文件，不是拆运维。

```text
开发机（一份仓库）
  └─ code_deploy 一体车道 → 远端同一目录布局

服务器
  ├─ 聊天壳 :3080（PATH 上的 dsh；不必每次同步整棵 host/node_modules）
  ├─ 引擎 :8091（apps/zr-workbuddy/engine）
  └─ nginx（可选）：/ → 聊天壳；/workbuddy/ → 引擎
     示例：scripts/deploy/nginx-one-entry.example.conf
```

| 变更类型 | 运维操作 | 是否重启引擎 | 是否确保聊天壳 |
| --- | --- | --- | --- |
| 只改某个 feature | 一次「部署」确认 | ensure 保活 | 一体模式下确保在跑 |
| 只改引擎 | 同上 | restart | 同上 |
| 改 bridge | 同上 | ensure | 重装 bridge + 重启壳 |
| 首次空目录 | 全量单元 + 同上收尾 | restart | 拉起 |

说明：`host/` 源码二次开发仍可本地改；**日常一体部署不强制 rsync 2GB+ node_modules**。服务器装好 `dsh` + 一次 `wire` 即可。

---

## 6. 实施阶段（确认后按序执行）

| 阶段 | 内容 | 产出 |
| --- | --- | --- |
| **P0 确认** | 本文评审；定上游仓库与许可、钉死的 tag/commit | **已完成**（用户指定 Downloads 源码并要求执行） |
| **P1 入仓** | 创建 `host/`，导入源码，写 `UPSTREAM.md` + `WORKBUDDY.md`；`.gitignore` | **已完成**（排除 node_modules；约 151MB 源码树） |
| **P1b 本机依赖** | `cd host && pnpm install` 冒烟（不启动） | **已完成**（~2.4GB；已清理根目录误装 lefthook） |
| **P2 接线** | 脚本：link Bridge、profile 指向本仓 `apps/zr-workbuddy`；本机起宿主 + ensure 引擎 | **已完成**（`scripts/host.sh`：verify/wire/ensure-engine/start-web/stop-web；默认 start-web=全局 dsh） |
| **P3 远端** | 服务器首次：装 dsh、wire、nginx 一体入口；之后走 code_deploy 一体车道 | **运维清单 + nginx 示例已补**；首次装机仍按环境手工一次 |
| **P4 单元（可选）** | 若需同步可构建的 `host/` 源码再增 `host` 单元 | **非必须**（一体部署默认用全局 dsh） |

**P2 本机验收（已做）**：`verify OK`；引擎 `:8000`；宿主 web `:3080` HTTP 200；mes-bridge 热载 features。  
**未改**：业务 `code_deploy` 默认行为、`auto_restart_bridge`。

---

## 7. 风险与约束

| 风险 | 对策 |
| --- | --- |
| 仓体积变大 | 接受；大二进制/缓存不进 git；文档标明 |
| 上游升级痛苦 | 钉版本；补丁尽量薄；升级只动 `host/` |
| 业务渗进宿主 | Code review / AGENTS 铁律；禁止 features 逻辑进 host |
| 与旧「宿主可不上」口径 | 本方案是**产品线升级**：要生态插件与宿主浏览器则服务器必跑 `host`；纯引擎预发仍可只跑引擎 |
| 许可 | 导入前核对上游 License，写入 `UPSTREAM.md` |

---

## 8. 确认清单（请你勾选）

请确认或批注后回复「确认执行」：

- [ ] 采用同仓 **`host/`** 放完整宿主工程，**不**塞进 `vendor/`  
- [ ] 业务保持 **`apps/zr-workbuddy/`**，不焊进宿主  
- [ ] 接受：生态插件 = 服务器跑宿主；业务增量 = 现有 G2  
- [ ] 接受：宿主发版与 `feature:*` 分开  
- [ ] 上游来源与版本由你指定（或确认后由执行人写入 `UPSTREAM.md`）  
- [ ] 许可合规已了解  

---

## 9. 一句话结论

**同仓 `host/`（完整宿主）+ `apps/zr-workbuddy`（完整业务）是适合本仓库的主流 monorepo 做法；确认后再拷源码与接线，避免先动刀再改口。**

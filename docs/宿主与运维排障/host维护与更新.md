# 聊天壳实施步骤（日常使用 + 升级 dsh）

> 按编号做即可。仓库根默认：`/Users/hebo/ai_projects/DSH-ZR-WorkBuddy`  
> **本仓不放 DSH Studio 源码。** 聊天壳 = 本机全局 `dsh`（`npm @deepseek-ai/dsh`）。桌面包另钉版本，见 `scripts/package-desktop.sh` 的 `DSH_NPM_VERSION`（当前默认 `0.1.1-rc.2`）。

---

## 先看你要做哪一件

| 你现在想做的事 | 跳到哪一节 |
|----------------|------------|
| 平时打开插件中心、装第三方插件 | **A. 日常使用** |
| 插件中心坏了 / 领导要求换新版 Studio | **B. 升级 dsh 发行版** |
| 改查数、写码、部署 | **不要动 dsh**，改 `apps/zr-workbuddy/` |
| 聊天红条「reading prepare」 | **D. prepare 排障**（dsh-tools 双实例） |

---

## A. 日常使用（不更新代码）

### 步骤 A1：启动业务引擎

打开终端，执行：

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/engine.sh zr-workbuddy ensure
```

**成功：** 终端没有报错。浏览器打开 `http://127.0.0.1:8000` 能看到 WorkBuddy 网页。  
（端口若打不开，看 `apps/zr-workbuddy/engine/config/runtime.yaml` 里写的端口。）

### 步骤 A2：把 WorkBuddy 接到 Studio（每台电脑做一次即可）

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh wire
scripts/host.sh verify
```

**成功：** `verify` 打印里能看到 link / Bridge / 引擎探活是 OK。  
换电脑、重装系统后再做一遍 A2。

### 步骤 A3：打开 Studio（插件中心在这里）

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh start-web
```

**成功：** 浏览器打开 `http://127.0.0.1:3081` 能看到 DSH/Studio 界面。  
（WorkBuddy 开发壳 **:3081** / `~/.dsh`（工作区 + mes-bridge）；干净官方壳可选 **:3080**；桌面一体包 **:13080**。）  
若打不开：看终端有没有报「PATH 无 dsh」——需要：

```bash
npm i -g @deepseek-ai/dsh
```

**界面像全新官方壳、没有工作区？** WorkBuddy 应与工作区共用 **`~/.dsh`**，在 **`:3081`** 启动。一键纠正：

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh fix-ports      # 固定 WorkBuddy → :3081
scripts/verify-ports.sh        # 自检：3081 日志须含 [mes-bridge]
```

浏览器请开 **http://127.0.0.1:3081** → **新会话** → 硬刷新。需要官方 Harness 时再单独：`DSH_HOME=~/.dsh dsh web --port 3080 --no-open`。

### 步骤 A4：装第三方插件

1. 在 `3081` 页面左侧找到 **「插件」**（或「插件中心」），点进去。  
2. **设置 → 插件市场**：公司插件在最前（也可点「中软」分类）；后面是官方社区插件。搜索要装的插件 → 点安装 → 等它显示完成。  
3. 打开 **「已安装」**，状态要同时有：**已启用**、**运行中**。  
4. 回到中间对话框，用一句话让它用这个插件（例如插件说明里的示例）。

更细的状态口径见 [插件中心使用说明.md](./插件中心使用说明.md)。  
**不要**把这个插件的 zip 传到 `8000` 网页的「功能插件」里——那条路装不了这类插件。

### 步骤 A5：用完怎么停（可选）

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh stop-web
```

引擎要停再用：`scripts/engine.sh zr-workbuddy stop`。

---

## B. 升级 dsh 发行版

**只有 A4 一直装不上、或官方要求换版本时才做 B。平时跳过整节。**  
做之前关掉 Studio：先执行步骤 A5。

### 步骤 B1：看现在是哪一版

```bash
dsh --version
```

桌面包另看 `scripts/package-desktop.sh` 里的 `DSH_NPM_VERSION`。

### 步骤 B2：升级本机全局 CLI

```bash
npm i -g @deepseek-ai/dsh@<目标版本>
dsh --version
```

**成功：** 打印的号等于目标版本。

### 步骤 B3：若要打新桌面包，改钉版本再打包

编辑 `scripts/package-desktop.sh` 的 `DSH_NPM_VERSION`，然后：

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
./scripts/package-desktop.sh
```

### 步骤 B4：重新接线并打开

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh wire
scripts/host.sh verify
scripts/host.sh start-web
```

浏览器打开 `http://127.0.0.1:3081`，按 **A4** 再装一个第三方插件。

**成功（四条都要）：**

1. 3081 页面能打开  
2. 能进插件中心  
3. 插件变成「已启用 / 运行中」  
4. 再执行 `scripts/engine.sh zr-workbuddy ensure`，8000 业务网页仍可用  

---

## C. 禁止（做错会很难收）

1. 不要把 Studio 源码 zip 再拖进本仓建 `host/`。  
2. 不要为了改 WorkBuddy 功能去改 `@deepseek-ai/dsh` 的安装目录。  
3. 不要把商店插件 zip 传到 8000 的功能插件页。  
4. 不要把升级 dsh 当成「部署业务」——部署业务仍用原来的「部署到预发」确认卡。

---

## D. prepare 排障（dsh-tools 双实例）

聊天出现「本轮运行失败 / reading prepare」时：

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/check-vendor.sh --fix
scripts/host.sh restart-web
```

完整根因与验收见 [dsh-tools双实例与prepare报错.md](./dsh-tools双实例与prepare报错.md)。  
装市场插件后若复发，再跑一遍 `--fix`（`plugin.sh install` / `restart-web` 已自动对齐）。

---

## 修订

| 日期 | 说明 |
|------|------|
| 2026-09-07 | 改为逐步实施：A 日常开插件中心；B 升级 10 步（下载→备份→覆盖→装依赖→验收→改记录） |
| 2026-09-09 | 增 D：prepare / dsh-tools realpath；链到运维排障专篇 |
| 2026-09-13 | 撤同仓 `host/` 源码树；B 改为升级发行版 `dsh` / 桌面包 `DSH_NPM_VERSION` |

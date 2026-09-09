# host 实施步骤（日常使用 + 升级）

> 按编号做即可。仓库根默认：`/Users/hebo/ai_projects/DSH-ZR-WorkBuddy`  
> 当前仓里 host 版本：**0.1.0-rc.8**（看 `host/package.json` 的 `"version"`）

---

## 先看你要做哪一件

| 你现在想做的事 | 跳到哪一节 |
|----------------|------------|
| 平时打开插件中心、装第三方插件 | **A. 日常使用**（不用更新 host） |
| 插件中心坏了 / 领导要求换新版 Studio | **B. 升级 host** |
| 改查数、写码、部署 | **不要动 host**，改 `apps/zr-workbuddy/` |
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

**成功：** 浏览器打开 `http://127.0.0.1:3080` 能看到 DSH/Studio 界面。  
若打不开：看终端有没有报「PATH 无 dsh」——需要本机已安装 `dsh` 命令，或按 `scripts/host.sh start-web --from-host`（要求已经 `cd host && pnpm install`）。

### 步骤 A4：装第三方插件

1. 在 `3080` 页面左侧找到 **「插件」**（或「插件中心」），点进去。  
2. 搜索要装的插件 → 点安装 → 等它显示完成。  
3. 打开 **「已安装」**，状态要同时有：**已启用**、**运行中**。  
4. 回到中间对话框，用一句话让它用这个插件（例如插件说明里的示例）。

**失败常见原因：** 只显示「已安装」但不是「运行中」→ 等重启结束，或看插件详情是否还要填密钥。  
**不要**把这个插件的 zip 传到 `8000` 网页的「功能插件」里——那条路装不了这类插件。

### 步骤 A5：用完怎么停（可选）

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh stop-web
```

引擎要停再用：`scripts/engine.sh zr-workbuddy stop`。

---

## B. 升级 host（整棵换成新版 Studio）

**只有 A4 一直装不上、或官方要求换版本时才做 B。平时跳过整节。**  
做之前关掉 Studio：先执行步骤 A5。

下面把「新版本文件夹」写成：`/tmp/studio-new`  
你解压到别处，就把命令里的路径一起改掉。

### 步骤 B1：看现在是哪一版

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
python3 -c "import json; print(json.load(open('host/package.json'))['version'])"
```

**记下打印出来的版本号**（现在应是 `0.1.0-rc.8`）。升完还要再看一次，确认变了。

### 步骤 B2：下载带版本号的新 Studio

1. 打开浏览器：<https://github.com/fufankeji/deepseek-harness-studio/releases>  
2. 选一个**写了版本号**的 Release（例如 `0.1.0-rc.14`），不要下 unnamed 的 Source 随便乱下。  
3. 下载源码 zip / tar，解压。  
4. 解压后的目录里必须能直接看到 `package.json`。  
5. 把这个目录复制或改名为 `/tmp/studio-new`（或你记住的路径）。

检查：

```bash
ls /tmp/studio-new/package.json
```

**成功：** 能列出这个文件。列不出来说明路径不对，不要做 B3。

### 步骤 B3：备份本仓自己的说明文件

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
cp host/UPSTREAM.md /tmp/wb-UPSTREAM.md
cp host/WORKBUDDY.md /tmp/wb-WORKBUDDY.md
test -f host/PATCHES.md && cp host/PATCHES.md /tmp/wb-PATCHES.md
```

**成功：** `/tmp/wb-UPSTREAM.md` 和 `/tmp/wb-WORKBUDDY.md` 存在。  
这一步是防止下一步覆盖时把你们写的说明删掉。

### 步骤 B4：用新版本覆盖 `host/` 文件夹

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
rsync -a --delete \
  --exclude node_modules \
  --exclude .dsh-build \
  --exclude dist \
  --exclude .git \
  /tmp/studio-new/  host/
```

注意：`host/` 后面有斜杠；`/tmp/studio-new/` 换成你 B2 的真实路径。  
这一步会把 `host/` 里旧源码换成新的，**依赖目录 node_modules 不会拷进去**。

### 步骤 B5：把说明文件拷回去

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
cp /tmp/wb-UPSTREAM.md host/UPSTREAM.md
cp /tmp/wb-WORKBUDDY.md host/WORKBUDDY.md
test -f /tmp/wb-PATCHES.md && cp /tmp/wb-PATCHES.md host/PATCHES.md
```

### 步骤 B6：看版本号是不是已经变了

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
python3 -c "import json; print(json.load(open('host/package.json'))['version'])"
```

**成功：** 打印的号和 B1 不同，且等于你在 GitHub 上下的那一版。  
若还是旧号：B4 路径指错了，不要做 B7，从头检查 B2。

### 步骤 B7：安装依赖（要较长时间、占较多磁盘）

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy/host
pnpm install
```

**成功：** 命令结束退出码 0，`host/node_modules` 目录出现。  
若提示没有 `pnpm`：先安装 pnpm 11，再执行本步。  
若仓库根多出 `lefthook.yml`：删掉这个文件，不要 git 提交它。

### 步骤 B8：重新接线

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh wire
scripts/host.sh verify
```

**成功：** 和 A2 一样，verify 为 OK。

### 步骤 B9：打开并试装一个插件

```bash
cd /Users/hebo/ai_projects/DSH-ZR-WorkBuddy
scripts/host.sh start-web
```

浏览器打开 `http://127.0.0.1:3080`，按 **A4** 再装一个第三方插件。

**成功（四条都要）：**

1. 3080 页面能打开  
2. 能进插件中心  
3. 插件变成「已启用 / 运行中」  
4. 再执行 `scripts/engine.sh zr-workbuddy ensure`，8000 业务网页仍可用  

缺任何一条都算升级没完成，不要改 git、不要告诉别人已经升完。

### 步骤 B10：改版本记录（给人看的）

用编辑器打开 `host/UPSTREAM.md`，改这几行：

- **版本**：改成 B6 打印的号  
- **上游来源**：改成 GitHub 这个 Release 的网址（不要只写 Downloads 路径）  
- **导入日期**：改成今天  

保存文件。

---

## C. 禁止（做错会很难收）

1. 不要把 `~/Downloads/某个文件夹` 直接拖进 `host/` 覆盖（没有版本号）。  
2. 不要提交 `host/node_modules`。  
3. 不要为了改 WorkBuddy 功能去改 `host/packages` 里面的文件。  
4. 不要把商店插件 zip 传到 8000 的功能插件页。  
5. 不要把升级 host 当成「部署业务」——部署业务仍用原来的「部署到预发」确认卡。

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

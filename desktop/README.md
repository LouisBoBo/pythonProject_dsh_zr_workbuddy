# 桌面安装包（宿主一体）

默认产出：**内嵌 Host（dsh web）+ 内嵌引擎**。安装后在设置 / WorkBuddy 配置中心填 Key 即可用，不依赖本机另装 `dsh`。

## 打包（本机 Mac）

```bash
# 宿主一体：electron-builder 只出 dir+zip（默认不再打 dmg）
./scripts/package-desktop.sh

# 已有 runtime 缓存时
SKIP_RUNTIME=1 SKIP_HOST=1 SKIP_NODE=1 SKIP_MARKET=1 SKIP_PNPM=1 ./scripts/package-desktop.sh

# 需要 DMG（拖到「应用程序」安装盘；自研 ULFO，带 15s 预检 + 超时）
MAKE_DMG=1 DMG_FORMAT=ULFO ./scripts/package-desktop.sh
```

产物：
- **主推** `desktop/release/ZR WorkBuddy-*.zip`（解压 → `.app` 拖进「应用程序」）
- DMG：打开后把 **ZR WorkBuddy.app** 拖到旁边的 **Applications**（应用程序）即可

**为何曾经打很久还不成功**
1. electron-builder 内置 dmg = UDRW + zlib，对 ~1GB 一体包极慢且易失败  
2. 脚本里再 `ditto` 一遍 1.1G 纯浪费时间  
3. 把 `Applications` 快捷方式放进 `-srcfolder` 会偶发跟进整盘程序目录 → 假死（现改为挂载后再加链接）  
4. 多次强杀 `hdiutil` 后，本机 `diskimages-helper` 会卡死（连 1KB 测试镜像也挂）→ 需 `killall diskimages-helper` 或重启后再 `MAKE_DMG=1`

前置：本机已 `npm i -g @deepseek-ai/dsh`（默认整包拷进安装包；约 +280MB）。  
也可用 `HOST_FROM_GLOBAL=0` 改走 `npm install`（更慢）。`DSH_NPM_VERSION` 仅在该模式下生效。

## 安装后

1. 打开 dmg，把 **ZR WorkBuddy.app** 拖到 **Applications**（未签名：第一次请 **右键 → 打开**）
2. 启动后进入聊天壳
   - **设置 → 模型**：填 API Key
   - **设置 → WorkBuddy**：配各车道（密钥写入本机引擎 `config.yaml`）
   - **设置 → 插件市场**：公司插件在最前，后面是 DSH 社区插件（内嵌 `dshmarket` + `pnpm`，不必本机 sudo 装 pnpm）
3. 自有写码/审码/提交功能在 **WorkBuddy / 引擎功能插件页**，不要用插件市场当这条通道

## 配置会不会丢

WorkBuddy 的 Key / MES / SSH / 工作区写在本机：

`~/Library/Application Support/zr-workbuddy-desktop/persist/`

升级安装包会刷新内嵌代码，但会把这份配置拷回去。  
**用户后来在引擎「功能插件」页装上的 WorkBuddy 功能**（安装包里没有的 `features/<id>`）也会进 `persist/user-features/`，升级后自动填回。出厂打进安装包的功能以新包为准。  
**不要删** `~/Library/Application Support/zr-workbuddy-desktop/`，否则等于清数据重装。

## 说明

- 密钥不进安装包
- 一体包用隔离 `DSH_HOME`（在 Application Support 下），不复用本机 `~/.dsh`
- 端口：桌面壳默认 **:13080**；浏览器开发壳用 **:3081**（`scripts/host.sh`），勿混开以免以为「会话丢了」
- 未做 Apple 公证

# 桌面安装包（宿主一体）

默认产出：**内嵌 Host（dsh web）+ 内嵌引擎**。安装后在设置 / WorkBuddy 配置中心填 Key 即可用，不依赖本机另装 `dsh`。

## 打包（本机 Mac）

```bash
# 宿主一体（默认，体积大、首次构建很久）
./scripts/package-desktop.sh

# 已有 desktop/runtime 引擎、host、Node、dshmarket、pnpm 暂存时
SKIP_RUNTIME=1 SKIP_HOST=1 SKIP_NODE=1 SKIP_MARKET=1 SKIP_PNPM=1 ./scripts/package-desktop.sh

# 旧版：仅引擎壳（需本机 dsh 才有聊天壳）
./scripts/package-desktop.sh engine
```

产物：`desktop/release/ZR WorkBuddy-*.dmg`

前置：本机已 `npm i -g @deepseek-ai/dsh`（默认整包拷进安装包；约 +280MB）。  
也可用 `HOST_FROM_GLOBAL=0` 改走 `npm install`（更慢）。`DSH_NPM_VERSION` 仅在该模式下生效。

## 安装后

1. 打开 dmg，拖到「应用程序」（未签名：**右键 → 打开**）
2. 启动后进入聊天壳
   - **设置 → 模型**：填 API Key
   - **设置 → WorkBuddy**：配各车道（密钥写入本机引擎 `config.yaml`）
   - **设置 → 插件市场**：装 DSH 社区插件（内嵌 `dshmarket` + `pnpm`，不必本机 sudo 装 pnpm）
3. 自有写码/审码/提交功能在 **WorkBuddy / 引擎功能插件页**，不要用插件市场当这条通道

## 配置会不会丢

WorkBuddy 的 Key / MES / SSH / 工作区写在本机：

`~/Library/Application Support/zr-workbuddy-desktop/persist/`

升级安装包会刷新内嵌代码，但会把这份配置拷回去。  
**不要删** `~/Library/Application Support/zr-workbuddy-desktop/`，否则等于清数据重装。

## 说明

- 密钥不进安装包
- 一体包用隔离 `DSH_HOME`（在 Application Support 下），不复用本机 `~/.dsh`
- 未做 Apple 公证

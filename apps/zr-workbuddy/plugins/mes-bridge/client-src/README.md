# mes-bridge client 源码（esbuild → 单文件）

交付契约不变：宿主仍只加载 `lib/client.js`（`dsh.client` 单入口）。

开发在 `client-src/`；构建用 esbuild 打成 CJS，再包一层 `RUNTIME` + `ModuleLoader` 外壳写入 `lib/client.js`。

## 目录

| 路径 | 说明 |
|---|---|
| `entry.js` | esbuild 入口（组装 lanes / login / space 等） |
| `styles.css` | 面板样式真相源 |
| `styles.css.sha256` | CSS 内容校验用（可选对照） |
| `lanes/*.js` | 写码 / 审码 / 提交 / 部署等车道 |
| `lanes/code-dev-persist.js` | 写码车道：本地持久化 + pipeline 步骤（纯逻辑） |
| `.build/` | 中间产物（gitignore；勿手改） |

`lib/client.js` 须保留：`/*RUNTIME_BEGIN*/`、`window.__ModuleLoader__.load`、`createBridgeModule` 包装路径。

## 改代码或样式

CSS 仍只改 `client-src/styles.css`；JS 改对应 `client-src/**`。**不要**手改 `lib/client.js`。

```bash
# 在仓库根，或用 mes-bridge 的 npm script：
node scripts/build-mes-bridge-client.mjs
node scripts/build-mes-bridge-client.mjs --check

# 等价：
cd apps/zr-workbuddy/plugins/mes-bridge
pnpm run build:client
pnpm run check:client
```

依赖：`esbuild@0.25.0` 为 mes-bridge **devDependency**（pnpm）。若本机未装，构建脚本会尝试 `npx esbuild`。

## 构建脚本行为摘要

1. esbuild：`entry.js` → bundle（`--loader:.css=text`，`react` external）
2. 包上 RUNTIME + ModuleLoader，要求导出 `createBridgeModule`
3. 烟测 factory 形状后写盘；`--check` 只校验已有产物

## 注意

- 改完必须跑一遍 build；未重建则宿主仍跑旧 `lib/client.js`
- 烟测环境是 mock DOM，登录挡板等副作用可能打 console 警告，只要 `CHECK OK` / 写盘成功即可

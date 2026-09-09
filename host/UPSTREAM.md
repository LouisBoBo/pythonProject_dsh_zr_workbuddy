# 上游说明（UPSTREAM）

本目录 `host/` 为 **DeepSeek Harness Studio** 完整源码树的受控拷贝，供 ZR-WorkBuddy **二次开发宿主**使用。

| 项 | 值 |
| --- | --- |
| 本地导入来源 | `/Users/hebo/Downloads/deepseek-harness-studio-main` |
| 包名 | `@deepseek-ai/dsh-root` |
| 版本 | `0.1.0-rc.8`（见 `package.json`） |
| 许可 | MIT（见 `LICENSE`，Copyright (c) 2026 DeepSeek） |
| 导入日期 | 2026-09-04（北京时间） |
| 导入方式 | `rsync` 拷贝；**已排除** `node_modules/`、`.dsh-build/`、各类 `dist` 与本机垃圾 |

## 与本仓其它目录的关系

| 路径 | 职责 |
| --- | --- |
| `host/` | 宿主壳：Web/桌面、插件中心、可装生态插件 |
| `apps/zr-workbuddy/` | **业务**（引擎 / features / Bridge），禁止焊进本目录内核 |
| 仓库根 `vendor/` | 业务侧小依赖钉选；**不是**本目录内的 `host/vendor/` |

本目录内另有上游自带的 `vendor/`、`packages/`、`apps/`——均为 **Harness Studio 工程内部结构**，勿与本仓 `apps/zr-workbuddy` 混淆。

## 升级策略

日常**不要**更新 `host/`。完整步骤（备份说明文件、rsync 排除项、接线、插件中心验收）见仓库文档：

**[docs/宿主与运维排障/host维护与更新.md](../docs/宿主与运维排障/host维护与更新.md)**

摘要：

1. 只用上游确定的 Release / tag，不要从本机无名 `Downloads` 覆盖。  
2. `rsync` 排除 `node_modules`、`.dsh-build`、`dist`、`.git`；先备份 `UPSTREAM.md`、`WORKBUDDY.md`（及 `PATCHES.md`）。  
3. `cd host && pnpm install`，再 `scripts/host.sh wire` / `verify`；插件中心装一个第三方能「运行中」才算成功。  
4. 改本文件：版本号、tag、日期。自有补丁尽量薄，记入 `PATCHES.md`（若无补丁可暂不建）。  
5. **禁止**把 `features/` 业务逻辑合并进本树。

## 第三方声明

另见上游 `THIRD_PARTY_NOTICES.md`。

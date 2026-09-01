# vendor 锁定说明

本目录存放 DSH / Cordis 相关 npm 包的本地副本或**指向宿主的 symlink**，供插件 `link:` 引用。

## 关键：`@deepseek-ai/dsh-tools` 必须与宿主同一 realpath

Agent 循环用宿主安装树里的 `dsh-tools` 取 `TOOL_RUNTIME_SCHEDULER` Symbol；  
若 profile/vendor 解析到**另一份同版本文件**，会出现：

`Cannot read properties of undefined (reading 'prepare')` → UI「本轮运行失败」。

```bash
scripts/check-vendor.sh          # 检查
scripts/check-vendor.sh --fix   # 把 vendor/@deepseek-ai/dsh-tools 链到宿主
# 然后重启 DSH
```

## 原则

- **不要**随意升级或替换 vendor 内包版本；与本机已安装的 DSH 宿主兼容性优先。
- 发版 / CI：跑 `scripts/check-vendor.sh`（`test.sh` 已调用）。
- 新增/升级包时：在应用 `VERSION` 旁记录日期与原因，并跑 `scripts/test.sh`。
- 插件 `package.json` 中 `@deepseek-ai/*` 一律 link 到本仓库 `vendor/`。

## 与应用版本

`apps/<app>/VERSION` 表示业务版本；vendor/宿主接线变更应在提交说明中单独标出。

# 可安装的第三方样例插件

本目录下的包**符合** WorkBuddy `features/` 契约，可用「功能插件」页上传 zip，或：

```bash
scripts/plugin.sh --app zr-workbuddy install-feature docs/examples/<id>
scripts/plugin.sh --app zr-workbuddy install-feature docs/examples/dist/<id>.zip
```

| 包 | 说明 |
|----|------|
| [sample-third-party](./sample-third-party/) | 探活引擎 `status`（演示契约） |

预打 zip：`docs/examples/dist/*.zip`。

**不要**拿任意 Git 整仓往安装器里塞。样例装进 `features/` 后属于本机状态，不必提交 `features/sample-*`。

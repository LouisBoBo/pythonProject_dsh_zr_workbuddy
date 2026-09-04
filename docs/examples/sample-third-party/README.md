# 样例第三方插件

演示 G3 / P2 安装契约，**不是**业务功能。

## 能力

- 工具名：`mes_sample_ping`
- 示例问法：「用样例插件探活一下引擎」

## 安装

```bash
scripts/plugin.sh --app zr-workbuddy install-feature docs/examples/sample-third-party
```

或在引擎「功能插件」页上传本目录打成的 zip。

## 说明

- 禁止在本目录 `import` / `require` npm
- 算数一律 `eng.runEngine([...])`
- 未跑 DSH 时：安装与启停仍以引擎页为准

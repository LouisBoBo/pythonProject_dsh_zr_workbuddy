# dsh-background — DeepSeek Harness 背景插件

给 DeepSeek Harness 界面设置自定义背景（图片或渐变）。

## 使用

插件加载后，在浏览器 Console 执行：

```js
__dshBg.set('url(https://example.com/bg.jpg) center/cover no-repeat')
__dshBg.set('linear-gradient(135deg, #0f172a, #1e3a8a)')
__dshBg.get()    // 查看当前值
__dshBg.reset()  // 恢复默认
```

持久化在 `localStorage['dsh-bg']`。

## 机制

- 客户端 bundle 覆盖主题令牌 `--dsw-alias-bg-base` 与 `html/body` 背景。
- 包声明 `dsh.client.platform = web`，Host 半区为空实现。

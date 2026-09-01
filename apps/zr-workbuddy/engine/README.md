# ZR-WorkBuddy 引擎

**DSH-ZR-WorkBuddy** 的业务引擎：ZR-WorkBuddy 工作助手 — **对话 → 查数/分析 → 图表可视化**，内置配置中心。

## 当前能力（P0–P4 骨架已落地）

- **💬 工作助手（聊天界面）**：输入中文问题 → 自动出图（matplotlib PNG）+ 文字回复 + 数据表。
  支持查询类型：趋势（折线）、对比（柱状）、排名（TOP）、占比（饼图）、单值；
  指标：OEE、良率、不良率、产量、达成率、停机/告警、缺陷占比。
- **生产系统直连查询**：在配置中心填好连接（地址/账号/企业编码）后，聊天可查询**真实业务数据**
  （OEE / 日产量报表 / 质量 KPI / 缺陷分布 / 告警趋势 / 工单状态统计等分析接口），无需本地同步；
  未配置时回退演示数据，并在回复中标注数据源。
- **LLM 意图引擎**：聊天先由大模型理解用户意图（更懂自然语言，如"今天正在生产的工单有多少个"），
  再查数；失败自动回退规则引擎。支持两种提供方：
  - **DeepSeek API**：配置中心④填 Key（需外网，网络探测每 60 秒自动重试，恢复即生效）
  - **Ollama 本地**：填 Base URL（http://127.0.0.1:11434）与已拉取的模型名，无需外网
- **⚙️ 配置中心**：业务连接（测试连接）、**接口清单（上传 Swagger/OpenAPI 或 Markdown 接口文档自动解析）**、
  **数据字典（上传 xlsx/csv/txt/docx/md 自动解析归类）**、DeepSeek Key（测试 Key），
  保存到 `config/config.yaml`（密钥脱敏）。
- **离线优先**：图表用 matplotlib 渲染（中文字体 Hiragino 已实测）；自然语言先用内置规则引擎，
  DeepSeek API 代码已预留 —— 配置 Key 且网络可用时自动升级为 LLM 解析。
- **演示数据**：业务接入完成前，内置 120 天合成数据（3 产线 / 6 产品 / 白夜班）跑通全流程。

## 启动

端口与 host 见 `config/runtime.yaml`（业务配置）。

```bash
scripts/engine.sh zr-workbuddy ensure    # 后台确保就绪
scripts/engine.sh zr-workbuddy status
scripts/engine.sh zr-workbuddy stop
# 兼容: scripts/start-engine.sh zr-workbuddy
```

业务连接 / LLM 等写在 `config/config.yaml`（从 `config.example.yaml` 复制，勿提交）。
## 目录结构

```
zr-workbuddy/             # 应用目录名（脚本 --app）；产品为 ZR-WorkBuddy
├── app/
│   ├── main.py            # FastAPI 入口：/api/chat 聊天 + 配置 API + 状态
│   ├── analyzer.py        # 分析引擎：指标计算 + matplotlib 图表渲染（离线）
│   ├── nl_engine.py       # 自然语言引擎：规则引擎（主用）+ DeepSeek 预留
│   ├── demo_data.py       # 演示数据生成（离线合成数据）
│   ├── config_store.py    # 配置读写（YAML、脱敏、合并、备份）
│   └── static/index.html  # SPA：聊天界面 + 配置中心（零依赖）
├── config/config.yaml     # 运行时配置（界面写入，含密钥，勿提交）
├── data/                  # 数据仓库与 matplotlib 缓存
└── requirements.txt
```

## API 一览

| 接口 | 说明 |
|---|---|
| `POST /api/chat` | 中文问题 → `{reply, chart(PNG base64), table, intent, source}` |
| `GET /api/status` | 演示数据规模、网络状态、LLM 配置状态 |
| `GET/PUT /api/config` | 读取/保存配置（密钥脱敏回显） |
| `POST /api/config/import/swagger` | 上传接口文档：OpenAPI JSON/YAML **或 Markdown**（表格/请求方式+请求路径/GET /path 自动识别） |
| `POST /api/config/import/swagger/text` | 粘贴接口文档原文解析（同上，自动识别格式） |
| `POST /api/config/import/swagger/url` | 填接口文档 URL（如 `http://127.0.0.1:8009/docs`），自动抓取并转 `/openapi.json` 等，支持可选 Basic 认证 |
| `POST /api/config/import/dictionary` | 上传数据字典（xlsx/csv/txt/docx），自动解析字段、建议标准字段名、按关键词归类 |
| `POST /api/config/test/mes` | 测试业务连接（认证/可达性诊断） |
| `POST /api/config/test/deepseek` | 测试 DeepSeek Key |

## 安全说明

- 密码/Token/API Key 保存在本地 `config/config.yaml`，界面回显时脱敏（`••••••••`）
- 仅监听本机（默认 127.0.0.1）

## 路线图

- **P1 数据接入**：按配置中心填写的接口清单/数据字典，实现同步器 → SQLite 标准表 → 聊天切真实数据
- **P2 分析引擎增强**：预聚合日表、异常/突变洞察、pytest 单测
- **P4 扩展**：仪表盘页（KPI 卡片 + 筛选联动）、数据管理页（同步日志、质量报告）
- **P5 报告**：图文分析报告导出

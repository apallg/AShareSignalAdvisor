# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Apallg投研 — A股量化分析平台。三层 Docker 部署：Vue 3 前端 (Nginx) → FastAPI 后端 → MySQL 8.0。

## 常用命令

### 后端

```bash
# 启动后端开发服务器（Windows Git Bash 需用完整 Python 路径，避免 Microsoft Store 拦截）
/c/Users/Apallg/AppData/Local/Programs/Python/Python311/python -m backend.main

# 直接指定 uvicorn 启动（可选 reload）
/c/Users/Apallg/AppData/Local/Programs/Python/Python311/python -c "import uvicorn; uvicorn.run('backend.main:app', host='0.0.0.0', port=8000, reload=False)"

# 终止占用 8000 端口的进程
powershell -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force }"

# 安装依赖
pip install -r requirements.txt
```

### 前端

```bash
cd frontend
npm run dev      # Vite 开发服务器
npm run build    # 生产构建 → dist/
```

### Docker

```bash
docker-compose up -d              # 启动全部服务
docker-compose up -d --build backend  # 重建后端
docker-compose logs -f backend    # 查看日志
```

### 数据库

```bash
python -m db.setup                # 初始化表
mysql -u root -p qilin_stock < db/setup.sql   # 或直接导入 SQL
```

## 架构概览

```
前端 (Vue 3 + ECharts, Nginx 80)
  │  /api/*  →  proxy_pass backend:8000
  ▼
后端 (FastAPI, :8000)
  ├── backend/api/    端点 (market, stock, sectors, portfolio, alerts,
  │                    backtest, sentiment, news, trading, live_trading,
  │                    strategies, scheduler)
  ├── core/           数据层 (多源行情、MySQL储存、实时行情、定时调度)
  ├── engine/         回测引擎 (backtrader Cerebro + PandasData)
  ├── strategies/     策略库 (自动发现、热拔插注册表)
  ├── execution/      交易执行 (FakeBroker + live/ 实盘引擎)
  ├── nlp/            情绪分析管道
  ├── agents/         5角色 AI 辩论面板
  └── utils/          工具 (LLM客户端、缓存、通知)
         │
         ▼
MySQL 8.0 (qilin_stock 库)
```

## 关键设计

### 通知系统
`utils/notifier.py` — 双通道：**企业微信机器人** 为主，**Coze Workflow** 为备用。`send_risk_alert()` 优先走企微，失败/未配置时自动降级到 Coze。WECOM_BOT_KEY 支持完整 webhook URL 或纯 key。通知触发条件：扫描评分 ≥ `risk_threshold`（每只股票可单独设置，默认 7）。

### 风险扫描引擎
`core/portfolio_manager.py` — `PortfolioScanner` 扫描持仓，调用多 Agent 辩论 → 解析风险评分/等级/建议 → 持久化告警 → 推送通知。关键参数：
- `include` dict 控制启用的数据源：`{"daily", "technical", "financial", "patterns", "realtime"}` — 默认全开，可选关闭
- `threshold` 控制最低记录评分，`scan_all()` 中单只异常不影响其他股票

### 交易日定时扫描
`core/scheduler.py` — `TradingDayScheduler` 在后台线程运行，计算下一个交易日早盘/尾盘时间并等待触发。默认配置：周一至周五 09:35 + 14:55，阈值 7，**跳过财务指标**（数据源不稳定）。API 端点 `/api/scheduler/*` 支持 start/stop/trigger/status。前端告警页顶部显示调度器状态栏。

### 数据获取四级回退链
`core/data_fetcher.py` — `_get_with_fallback`：内存缓存 → 多数据源串行尝试 (miniQMT → 腾讯HTTP → 网易HTTP → akshare → BaoStock) → MySQL 持久缓存回退。实时行情有 30 秒类级别缓存避免重复请求。

### 策略热拔插
`strategies/registry.py` — `auto_discover()` 扫描 `classic/`、`hybrid/`、`community/`、`custom/` 子目录，自动注册所有 `BaseStrategy` 子类。新增策略只需创建 `.py` 文件继承 `BaseStrategy`，无需改注册表。

### 策略双轨制：回测 + 实盘
- **回测版** — 继承 `BaseStrategy`，基于 backtrader，用于 `/backtest` 和 `/lab`
- **实盘版** — 继承 `LiveStrategy` (`execution/live/base.py`)，`check_signal(df)` 直接返回 `{action, size_ratio, reason}`
- `execution/live/strategies.py` 自动发现 `LiveStrategy` 子类，API 保存/删除后热重载

### 实盘策略运行引擎
`execution/live/runner.py` — `StrategyRunner` 后台线程轮询行情 → 计算指标 → 调用策略 → 向 FakeBroker 下单。信号日志上限 1000 条，超出截断至 500。

### 交易执行层
```
策略信号 → BaseBroker 抽象接口 (execution/base.py)
              ├── FakeBroker  模拟撮合（MySQL 记录，虚拟资金）
              └── QmtBroker  xtquant.XtQuantTrader（需券商权限）
```
`BaseBroker._persist_order()` / `_persist_trade()` 由子类继承，避免重复代码。

### Agent 辩论面板
`agents/panel.py` — 5 个 Agent (技术/基本面/资金面/宏观/风控) 各自输出分析，风控官看到前 4 者后再输出风险评估，主持人综合全部给出最终决议（含风险评分/等级/建议）。

### LLM 客户端
`utils/llm_client.py` — OpenAI 兼容接口，支持 DeepSeek 和通义千问。MD5(input) 响应缓存避免短期内重复调用。

### 前端路由
Vue Router: `/market`(大盘) `/stock`(个股) `/sectors`(板块) `/portfolio`(持仓) `/alerts`(告警，含扫描+阈值管理) `/backtest`(回测) `/lab`(策略实验室) `/sentiment`(情绪) `/trading`(交易面板) `/live`(策略实盘) `/editor`(策略编辑器)

### 前端共享组件与组合式函数
- `MetricCard.vue` — 指标卡片（值+标签+颜色）
- `DataTable.vue` — 通用数据表格（列定义+插槽+空状态）
- `composables/useBroker.js` — 券商类型查询复用，避免各页面重复请求

### 配置
`config.py` — 所有配置通过 `python-dotenv` 加载环境变量。`.env` 含 API 密钥和数据库密码（已加入 `.gitignore`）。`.env.example` 作为模板。

### API 响应格式
所有端点统一返回 `{"data": ...}` 或 `{"status": "ok"}`。前端 axios 拦截器 (`api/index.js`) 自动剥离 `response.data` → 调用方取 `.data` 可得业务数据。POST 请求的 JSON body 参数需用 `Body()` 显式注解（FastAPI 不会自动将普通 dict 参数从 body 解析）。

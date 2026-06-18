# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

麒麟投研 — A股量化分析平台。采用三层 Docker 部署：Vue 3 前端 (Nginx) → FastAPI 后端 → MySQL 8.0。

## 常用命令

### 后端

```bash
# 启动后端开发服务器
python -m backend.main

# 安装依赖
pip install -r requirements.txt
```

### 前端

```bash
cd frontend
npm run dev      # 启动 Vite 开发服务器
npm run build    # 构建生产包 → dist/
```

### Docker

```bash
# 启动全部服务 (MySQL + 后端 + 前端)
docker-compose up -d

# 单独重建某服务
docker-compose up -d --build backend

# 查看日志
docker-compose logs -f backend
```

### 数据库

```bash
# 初始化数据库表
python -m db.setup
```

## 架构概览

```
前端 (Vue 3 + ECharts, Nginx 80)
  │  /api/*  →  proxy_pass backend:8000
  ▼
后端 (FastAPI, :8000)
  ├── backend/api/    端点层 (market, stock, sectors, portfolio, alerts, backtest, sentiment, news)
  ├── core/           数据层 (多源行情获取、MySQL储存、实时行情、选股器、持仓管理)
  ├── engine/         回测引擎 (封装 backtrader Cerebro + 自定义 PandasData 含技术指标列)
  ├── strategies/     策略库 (自动发现、热拔插注册表)
  ├── nlp/            情绪分析管道 (采集→LLM分类→因子计算→定时调度)
  ├── agents/         5角色 AI 辩论面板 (技术/基本面/资金/宏观/风控 → 主持人综合)
  └── utils/          工具 (LLM客户端、缓存、通知)
         │
         ▼
MySQL 8.0 (qilin_stock 库)
```

## 关键设计

### 数据获取三级回退链
`core/data_fetcher.py` 中通过 `_get_with_fallback` 实现：内存缓存 → 多数据源串行尝试 (腾讯HTTP → 网易HTTP → akshare → BaoStock) → MySQL 持久缓存回退。所有数据写入时同时持久化到 MySQL 作为下次启动的冷缓存。

### 策略热拔插
`strategies/registry.py` 的 `auto_discover()` 在 import 时扫描 `classic/`、`hybrid/`、`community/`、`custom/` 子目录，自动注册所有 `BaseStrategy` 子类。新增策略只需在对应目录下创建 `.py` 文件并继承 `BaseStrategy`，无需修改注册表。

### LLM 客户端
`utils/llm_client.py` — OpenAI 兼容客户端，支持 DeepSeek 和 通义千问。通过 MD5(input) 做响应缓存，避免短时间内重复调用。

### 情绪分析管道
`nlp/` 模块：`SentimentCollector` 爬取新浪个股新闻 → `SentimentAnalyzer` 批量调用 LLM 做情绪分类 → `SentimentFactorCalculator` 计算日度情绪因子 → `SentimentScheduler` 每30分钟自动执行一次。

### Agent 辩论面板
`agents/panel.py` — 5个独立 Agent (技术/基本面/资金面/宏观/风控) 各自输出分析，风控官看到前4者分析后输出风险评估，最后由主持人综合全部输出给出最终决议。

### 前端路由
Vue Router: `/market`(大盘) `/stock`(个股) `/sectors`(板块) `/portfolio`(持仓) `/scan`(选股) `/alerts`(告警) `/backtest`(回测) `/lab`(策略实验室) `/sentiment`(情绪)

### 配置
`config.py` — 所有配置通过环境变量 (`python-dotenv`) 加载。`.env` 包含 API 密钥和数据库密码（已加入 `.gitignore`）。

### QMT 交易执行层（开发中 — FakeBroker 阶段）

QMT 需券商权限，当前采用**渐进式开发**策略：

```
策略信号 → Execution抽象接口 (execution/base.py)
              ├── FakeBroker (当前阶段) — 本地模拟撮合、无外部依赖
              └── QmtBroker (权限开通后) — 对接 xtquant.XtQuantTrader
```

**FakeBroker 功能：**
- 按最新价模拟成交（买一/卖一）
- 记录全部委托/成交到 MySQL
- 维护虚拟资金和持仓
- 与后续 QmtBroker 接口完全一致，切换时策略层零改动

**开发顺序：**
1. `execution/` 抽象接口 + FakeBroker ← 当前
2. 数据库 orders/trades/accounts 表
3. 后端 trading API 端点
4. 前端交易面板
5. 权限开通后 → 新增 QmtBroker 实现，替换即可

### 完整 QMT 对接方案（权限开通后执行）

miniQMT (迅投 QMT 极简模式) 是券商提供的量化交易接口，通过 `xtquant` Python SDK 提供行情 + 交易能力。

**对接方案：**

1. **新数据源** — `core/data_sources/miniqmt_source.py` 实现 `BaseSource` 接口
   - 实时行情：`xtdata.get_full_tick()` / `xtdata.subscribe_quote()`
   - 历史K线：`xtdata.get_market_data_ex()` 替代现有的 HTTP 爬取链
   - 分笔数据：`xtdata.get_tick_data()`
   - miniQMT 数据源作为主源，现有 HTTP 源作为备源

2. **交易执行层** — 新建 `execution/` 模块
   - `execution/broker.py` — 封装 `xtquant.xttrader.XtQuantTrader`，下单/撤单/持仓查询
   - `execution/order_manager.py` — 订单状态跟踪、错误处理、重连机制
   - `execution/position_manager.py` — 持仓同步、资金查询
   - 交易回调 → WebSocket/SSE 推送至前端

3. **回测对接** — 策略已在 backtrader 中实现，miniQMT 历史数据可直接作为 `QuantDataFeed` 输入做回测。实盘时策略信号通过执行层下达到 miniQMT。

4. **数据库新增** — `orders` 表 (委托记录)、`trades` 表 (成交记录)、`accounts` 表 (账户资金)

5. **前端新增** — 交易面板 (`/trading`)、委托/成交/持仓视图

**依赖：**
- `xtquant` (迅投官方 Python SDK，需券商 QMT 客户端安装)
- 本地运行 QMT 客户端，miniQMT 模式基于本地 socket 通信，无需网络

**限制：**
- 需要券商开通 QMT 权限
- 需要 Windows 环境（已满足）
- xtquant 来自 QMT 安装目录，非 PyPI 包

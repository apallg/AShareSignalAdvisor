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

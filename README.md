# AShareSignalAdvisor
仅供大A量化教学
## 项目概述

Apallg投研 — A股量化分析平台 部署：Vue 3 前端 (Nginx) → FastAPI 后端 → MySQL 8.0。

## 常用命令

### 后端

```bash
# 启动后端（Windows 需完整 Python 路径 + OpenBLAS_NUM_THREADS=1 防 numpy 崩溃）
OPENBLAS_NUM_THREADS=1 /c/Users/Apallg/AppData/Local/Programs/Python/Python311/python -c "import uvicorn; uvicorn.run('backend.main:app', host='0.0.0.0', port=8000, reload=False)"

# 终止占用 8000 端口的进程
powershell -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force }"

# 安装依赖
pip install -r requirements.txt

# 清理 QMT 残留锁文件（连接失败时）
rm -f "D:/迅投极速交易终端 睿智融科版/userdata_mini/down_queue_win_"* "D:/迅投极速交易终端 睿智融科版/userdata_mini/up_queue_win_"* "D:/迅投极速交易终端 睿智融科版/userdata_mini/lock_"*
```

### 前端

```bash
cd frontend
npm run dev      # Vite 开发服务器 → http://localhost:5173
npm run build    # 生产构建 → dist/
```

### Docker

```bash
docker-compose up -d                   # 启动全部服务
docker-compose up -d --build backend   # 重建后端
docker-compose logs -f backend         # 查看日志
```

### 数据库

```bash
python -m db.setup                     # 初始化表
mysql -u root -p qilin_stock < db/setup.sql
```

## 架构概览

```
前端 (Vue 3 + ECharts, Vite :5173)
  │  /api/* → proxy → backend:8000
  ▼
后端 (FastAPI, :8000)
  ├── backend/api/   14 个路由模块 (market/stock/sectors/portfolio/alerts/
  │                  backtest/sentiment/news/trading/live_trading/
  │                  strategies/scheduler/qlib)
  ├── core/          数据层 (多源行情/MySQL储存/实时行情/定时调度/
  │                  交易日历/信号融合/板块扫描)
  ├── engine/        回测引擎 (backtrader + 参数优化器)
  ├── strategies/    策略库 (自动发现/热拔插, 30+ 策略, 4 个子目录)
  ├── execution/     交易执行 (FakeBroker/QmtBroker/EasytraderBroker + live/ 实盘引擎)
  ├── nlp/           情绪分析管道 (采集→LLM分类→因子计算→定时调度)
  ├── agents/        5 角色 AI 辩论面板 + 策略代码生成提示词
  └── utils/         基础设施 (LLM客户端/缓存/通知/配置管理)
         │
         ▼
MySQL 8.0 (qilin_stock 库, 14 张表)
```

## 模块详解

### backend/api/ — API 端点

所有端点统一返回 `{"data": ...}` 或 `{"status": "ok"}`。前端 axios 拦截器自动剥离 `response.data`。

#### market.py — 大盘行情
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/indices` | 四大指数实时报价 |
| GET | `/index-chart` | 指数历史走势 (默认上证, 120 天) |
| GET | `/top-gainers` | 涨幅榜 top N |
| GET | `/top-losers` | 跌幅榜 top N |
| GET | `/sectors` | 板块表现快照 |

#### stock.py — 个股分析
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/{code}` | 股票基本信息 |
| GET | `/{code}/daily` | 日K线 OHLC |
| GET | `/{code}/indicators` | 技术指标 + 金叉/死叉 + K线形态 |
| GET | `/{code}/realtime` | 实时报价 |
| GET | `/{code}/financial` | 财务数据 |
| GET | `/{code}/capital-flow` | 资金流向 |
| POST | `/{code}/analyze` | AI 分析 (single/panel 模式) |
| POST | `/{code}/analyze/stream` | AI 分析 SSE 流式输出 |

`stream` 端点：并行运行 4 个 agent → 风控官 → 主持人，通过 SSE 逐块输出 (`text/event-stream`)，前端打字机效果。

#### sectors.py — 板块选股
依赖 `core/stock_scanner.py` — `SectorScanner`。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/list` | 板块列表 (优先同花顺→东财) |
| GET | `/{sector}/stocks` | 成分股 (miniQMT SW2 前缀匹配→akshare) |
| GET | `/{sector}/support-resistance` | 批量支撑/压力位扫描 |

#### portfolio.py — 持仓管理
依赖 `core/database.py` — `HoldingsRepo`。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/holdings` | 全部持仓 |
| POST | `/holdings` | 添加持仓 (code/name/shares/cost_price/risk_threshold) |
| PUT | `/holdings/{code}` | 更新持仓字段 (灵活部分更新) |
| DELETE | `/holdings/{code}` | 删除持仓 |

#### alerts.py — 风险告警
依赖 `core/portfolio_manager.py` — `PortfolioScanner`。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 告警列表 (可按等级过滤) |
| GET | `/stats` | 按等级统计 (最近 200 条) |
| GET | `/channels` | 通知通道状态 (企微/Coze) |
| POST | `/test` | 发送测试通知 |
| POST | `/scan/{code}` | 单只持仓扫描 (可配 include/threshold) |
| POST | `/scan` | 批量扫描全部持仓 |

扫描时 `include` dict 控制数据源：`{technical, financial, patterns, realtime}` 可逐个关闭。

#### trading.py — 交易执行
依赖 `execution/` broker 工厂。**`get_broker()` 是关键入口**：延迟加载单例，自动检测断连并重连。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/broker` | 券商类型 (fake/qmt/easytrader) |
| GET | `/account` | 账户摘要 (现金/市值/总资产/盈亏) |
| GET | `/orders` | 委托列表 (可按状态过滤) |
| POST | `/orders` | 下单 (symbol/side/quantity/price_type/price) |
| DELETE | `/orders/{id}` | 撤单 |
| GET | `/trades` | 成交记录 |
| GET | `/positions` | 当前持仓 |
| POST | `/account/cash` | 模拟入金 (仅 FakeBroker) |
| PUT | `/account/cash` | 设置余额 (仅 FakeBroker) |
| POST | `/account/withdraw` | 模拟出金 (仅 FakeBroker) |

#### live_trading.py — 策略实盘
依赖 `execution/live/runner.py`。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/strategies` | 可用实盘策略列表 |
| POST | `/start` | 启动策略运行器 |
| POST | `/stop/{id}` | 停止运行器 |
| GET | `/status` | 全部运行器状态 |
| GET | `/signals` | 最近信号日志 |
| GET | `/trading-time` | 当前交易时段状态 |
| GET/PUT | `/signal-fusion/config` | 信号融合配置 |
| GET/PUT | `/force-close/config` | 强制平仓配置 |

启动运行器时 `interval_sec` 最小 10 秒。强制平仓默认 14:54，原因 `FORCE_CLOSE_REASON`。

#### backtest.py — 策略回测
依赖 `engine/backtest.py` + `strategies/registry.py`。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/strategies` | 全部回测策略列表 |
| POST | `/run` | 运行回测 (strategy/codes/dates/cash/commission) |
| POST | `/optimize` | 参数网格搜索优化 |
| GET | `/result/{id}` | 查询回测结果 |
| GET | `/history` | 最近回测历史 |

#### scheduler.py — 定时扫描调度
薄封装 `core/scheduler.py`。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/status` | 调度器状态 |
| POST | `/start` | 启动 |
| POST | `/stop` | 停止 |
| POST | `/trigger` | 手动触发一次 |

#### strategies.py — 策略文件管理 + AI 生成
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/files` | 列出所有策略文件 |
| GET | `/file?path=` | 读取源码 |
| POST | `/file` | 写入 (仅 custom/ 和 community/) |
| DELETE | `/file` | 删除 (仅 custom/ 和 community/) |
| POST | `/generate` | AI 生成策略 (3 阶段：编写→代码审查→逻辑审查) |

路径安全：`_safe_path()` 防止目录遍历攻击。

#### sentiment.py — 情绪数据
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/{code}` | 个股情绪历史 (默认 30 天) |
| GET | `/market/overview` | 全市场情绪聚合 + 7 天趋势 |
| GET | `/sectors/rank` | 板块情绪排名 |

#### news.py — 新闻数据
依赖 `nlp/collector.py` + `nlp/analyzer.py`。
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/{code}` | 个股最近新闻 |
| GET | `/{code}/refresh` | 强制采集+分析单只股票 |
| GET | `/latest/list` | 全部最新新闻 |

#### qlib.py — Qlib AI 量化
依赖 `qlib_integration/` 包。
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/data/sync` | MySQL→Qlib 数据同步 (并发锁) |
| GET | `/data/status` | 数据丰富度状态 |
| GET | `/models` | 可用模型 + 默认参数 |
| POST | `/models/train` | 启动训练 (异步后台) |
| GET | `/models/train/{job}` | 轮询训练进度 |
| POST | `/models/predict` | 使用模型生成预测 |
| POST | `/backtest/run` | Qlib 回测 |
| GET | `/experiments` | MLflow 实验列表 |

### core/ — 数据层

#### data_fetcher.py — 多源数据获取 (核心)
`DataFetcher` 类：统一数据入口。日K线 **7 级回退链**：miniQMT → 腾讯 IFZQ HTTP → 网易 163 HTTP → akshare (东财) → BaoStock → MySQL 过期缓存 → 异常。实时行情有 30 秒类级别 `_spot_cache` 避免重复全市场快照。`_get_with_fallback()` 实现内存缓存→API→MySQL 三级缓存。支持 `_retry()` 装饰器 (默认 3 次重试，3 秒间隔)。

关键方法：`get_stock_daily()`, `get_realtime_quote()`, `get_stock_name()`, `get_market_indices()`, `get_index_daily()`, `get_top_gainers()`, `get_top_losers()`, `get_sector_performance()`, `get_stock_financial()`, `get_capital_flow()`

#### analyzer.py — 技术分析
`Analyzer` 全静态方法：`add_indicators(df)` 计算 MA5/10/20/60, EMA5/20, MACD, RSI14, KDJ, 布林带, VOL_MA5/20, ATR14 (依赖 `ta` 库)。`detect_cross_signals()` 检测金叉/死叉。`detect_kline_patterns()` 识别十字星/锤子线/吞没/三白兵等。`get_analysis_context()` 生成 LLM 可读的分析文本块。

#### database.py — MySQL 数据库
`Database` 类：线程安全的连接管理 (单例)，14 张表。关键修复：`ssl={"ssl_disabled": True}` 解决 MySQL 8.0 `caching_sha2_password` SSL 握手间歇性失败。`_is_connection_alive()` 通过 socket `getsockname()` + `ping()` 检查连接。`_execute_with_retry()` 失败后强制关闭 socket 并重连。

Repository 类：`HoldingsRepo`, `RiskAlertRepo`, `SettingsRepo`, `DailyQuotesRepo`, `DataCacheRepo`, `AnalysisHistoryRepo`。均通过 `Database.fetchone/fetchall/execute` 访问。

#### realtime.py — 实时行情引擎
`RealtimeEngine`：统一实时行情入口，facade 模式封装数据源注册表。`get_indices()` 获取四大指数。`get_sina_sectors()` 抓取新浪板块排名 (缓存 300s)。排行榜查询 (`get_top_gainers/losers/volume_ranking`) 优先新浪 JSON API，回退 akshare。

#### stock_scanner.py — 板块扫描器
`SectorScanner`：`get_all_sectors()` 板块列表 (同花顺→东财→硬编码回退，缓存 24h)。`get_sector_stocks()` 成分股 (东财 akshare→miniQMT SW2 前缀模糊匹配，缓存 5min)。`scan_support_resistance()` 多线程 (ThreadPoolExecutor, 10 workers) 计算每只股票的布林带/MA60/20日低点/MA20 支撑位和压力位，距关键位 2-3% 时标记信号。

#### portfolio_manager.py — 持仓扫描
`PortfolioScanner`：编排器模式，遍历全部持仓→采集多维数据→调用 `DebatePanel` LLM 辩论→解析风险评分/等级/建议→持久化告警→推送通知。`include` dict 控制数据维度开关。正则提取 LLM 输出中的 "风险评分: X/10"。

#### trading_time.py — 交易时间工具
模块级函数式 API (无类)：`is_trading_day()` (akshare 交易日历→weekday 回退)、`is_trading_time()` (9:30-11:30, 13:00-15:00)、`get_trading_session()`、`time_until_close()`、`next_trading_time()`。缓存每日刷新。

#### signal_fusion.py — 信号融合投票
`SignalFusion`：6 个独立投票方法 (`_vote_macd/rsi/ma/kdj/bb/volume`)，加权求和得 `FusionResult(score, action, confidence, reasons)`。默认权重：MACD=1.0, RSI=0.8, MA=0.7, KDJ=0.5, BB=0.6, VOL=0.3。两种模式：`filter` (置信度<阈值则丢弃信号) 和 `override` (融合分数覆写原信号)。

#### scheduler.py — 定时扫描调度
`TradingDayScheduler` 单例 daemon 线程：计算下一个交易日早盘/尾盘时间→sleep→触发扫描。默认 09:35 + 14:55，阈值 7，跳过财务指标。`get_scheduler()` 获取全局单例。

#### data_sources/ — 实时数据源
- `base.py`：`BaseRealtimeSource` 抽象基类
- `sina_source.py`：新浪财经 (JS 变量格式解析，GBK 编码)
- `tencent_source.py`：腾讯财经 (`~` 分隔格式)
- `miniqmt_source.py`：miniQMT `xtdata` 封装 (`get_full_tick()` / `get_kline()`)
- `registry.py`：按类别管理主/备源 (`stock_daily`/`realtime`/`financial`/`sectors`/`sentiment`)
- `scraper/`：爬虫基类 (`BaseScraper` 带速率限制+UA 轮换) + `SinaNewsScraper`

### execution/ — 交易执行

#### 抽象层
`base.py` — `BaseBroker` 抽象接口：`connect()`, `place_order()`, `cancel_order()`, `get_orders()`, `get_trades()`, `get_positions()`, `get_account()`。提供 `_persist_order()` / `_persist_trade()` 共享 MySQL 持久化方法。

`__init__.py` — `create_broker(type)` 工厂函数 + `is_fake_broker()` 类型检查。

#### FakeBroker — 模拟撮合
本地模拟，初始资金 100 万，接受 `price_provider` 回调获取行情价。市价单立即成交，限价单检查价格后成交或挂单。额外提供 `add_cash/set_cash/withdraw_cash`。

#### QmtBroker — miniQMT 实盘
关键行为：
- `connect()`：清理残留锁文件→创建 `XtQuantTrader`→启动 `run_forever()` daemon 线程→同步持仓/资产
- `_normalize_symbol()`：自动补全 `.SH`/`.SZ` 后缀 (6xx/5xx→SH, 0xx/3xx/2xx→SZ)
- `place_order()`：该 QMT 版本**仅支持 `FIX_PRICE=11`**，不支持 `LATEST_PRICE=5` 和 `PRTP_MARKET=12`。市价单自动获取行情价 (tick→PreClose 回退)
- `_TraderCallback`：异步回调更新本地状态，线程安全 (threading.Lock)
- 数据同步方法 (`_sync_orders/trades/positions/asset`) 有 1 秒最小间隔限流

#### EasytraderBroker — 同花顺 GUI 自动化
通过 `easytrader` (pywinauto) 操控同花顺客户端，对接银河证券 (`yh_client`)。`connect()` 使用 `WMCopy` 网格策略避免验证码弹窗。所有公开方法由 `threading.Lock` 保护。

#### execution/live/ — 实盘策略引擎
- `base.py`：`LiveStrategy` 轻量基类 (不依赖 backtrader)，`check_signal(df)` 返回 `{action, size_ratio, reason}`
- `strategies.py`：`LIVE_STRATEGIES` 自动发现 `LiveStrategy` 子类，`reload_live_strategies()` 热重载
- `runner.py`：`StrategyRunner` 单例 (`get_runner()`) — 后台线程轮询行情→计算指标→调用策略→信号融合 (可选)→下单。信号日志上限 1000 条。交易时间外休眠，强制平仓窗口内自动清仓

### strategies/ — 策略库

#### 注册表
`registry.py`：`auto_discover()` 扫描 4 个子目录，自动注册所有 `BaseStrategy` 子类。`register()` 手动注册。`_find_live_key()` 关联对应的 `LiveStrategy` 子类。双轨制：每个策略文件同时包含回测版 (`BaseStrategy`) 和实盘版 (`LiveStrategy`)。

#### classic/ — 9 个经典策略
| 策略 | 文件 | 核心逻辑 |
|------|------|----------|
| 金叉策略 | golden_cross.py | 快线上穿慢线买入，死叉/止损/止盈卖出 |
| 布林带策略 | bollinger.py | 触及下轨买入，触及上轨/中轨卖出 |
| 突破策略 | breakout.py | 突破 N 日最高价买入，跌破最低价卖出 |
| 均值回归 | mean_reversion.py | Z-score < -2 买入，回归卖出 |
| 动量策略 | momentum.py | ROC 为正且价格>均线买入 |
| 网格策略 | grid.py | 等间距挂单，触碰即成交 |
| 海龟策略 | turtle.py | 突破入场 + ATR 跟踪止损 |
| 低波动策略 | low_vol.py | 变异系数低时买入 |
| 价值策略 | value.py | PE<15 且 ROE>10 买入 |
| 多头排列 | bull_arrangement.py | 短>中>长均线多头排列买入 |

#### hybrid/ — 3 个混合策略
需要额外数据列 (`ai_factor`, `sentiment`)。
| 策略 | 核心逻辑 |
|------|----------|
| AI 过滤金叉 | 金叉 + AI 评分≥6 才买入 |
| 情绪加成 | 金叉 + 情绪系数调整仓位 (0.3x-1.5x) |
| 多因子评分 | 技术/AI/情绪加权得分≥阈值买入 |

#### custom/ — 4 个自定义策略
`test.py` (板块条件概率)、`test2.py` (金叉复制品)、`钟航健.py` (板块龙头追涨)、`钟云锋.py` (与钟航健相同代码)。

### engine/ — 回测引擎

- `backtest.py`：`BacktestEngine` 封装 `bt.Cerebro`，添加数据→策略→分析器→运行→收集指标
- `data_feed.py`：`QuantDataFeed(bt.feeds.PandasData)` 扩展 20+ 额外数据列 (技术指标/AI因子/情绪/基本面/成交量)，缺失列自动填 0
- `analyzer.py`：`calculate_metrics()` 从 backtrader 分析器提取夏普比率/最大回撤/年化收益/胜率/盈亏比/权益曲线
- `reporter.py`：`serialize_result()` JSON 序列化，`result_to_chart_data()` ECharts 适配
- `optimizer.py`：`GridOptimizer` 网格搜索 (笛卡尔积)，`GeneticOptimizer` 遗传算法 (精英/交叉/变异)，适应度函数加权：夏普×10 + 总收益×0.5 - 最大回撤×0.5 + 胜率×0.1

### nlp/ — 情绪分析管道

- `collector.py`：`SentimentCollector` 通过 `SinaNewsScraper` 采集个股新闻，MD5(title+date) 去重，INSERT IGNORE 入 `raw_news` 表
- `analyzer.py`：`SentimentAnalyzer` 用 DeepSeek 批量分类新闻情感 (每批 50 条)，输出 `{sentiment, score(-1~1), confidence(0~1)}`
- `factor.py`：`SentimentFactorCalculator` 按日聚合 emotion，计算平均分/积极率/消极率/数量，写入 `sentiment_daily` 表
- `scheduler.py`：`SentimentScheduler` 用 APScheduler `BackgroundScheduler` 每 30 分钟自动采集+分析+计算因子

### agents/ — AI 辩论面板

- `base_agent.py`：`BaseAgent` 持有 `LLMClient` + 角色提示词 + `CacheManager`
- `prompts.py`：所有提示词模板 (技术/基本面/资金面/宏观/风控/主持人/策略代码生成/代码审查/逻辑审查/板块分析)
- `panel.py`：`DebatePanel` 编排 6 个 agent — 前 4 个并行分析 (ThreadPoolExecutor, 60s 超时)→风控官审查→主持人综合→输出完整投研纪要
- `scheduler.py`：`Scheduler` 纯线程定时器，默认每日 4 次扫描 (8:30/11:30/15:30/20:00)

### utils/ — 基础设施

- `llm_client.py`：`LLMClient` OpenAI 兼容接口，支持 DeepSeek/通义千问。`chat()` 阻塞调用，`chat_with_cache()` MD5 去重，`chat_stream()` SSE 生成器
- `cache_manager.py`：`CacheManager` 封装 `diskcache`，`get_with_fallback()` 三级回退 (本地→函数调用→MySQL)
- `notifier.py`：双通道通知 — `WeComNotifier` (企微机器人 webhook, markdown 格式) 为主，`CozeNotifier` (Coze Workflow API) 为备用。`send_risk_alert()` 先企微后 Coze 自动降级
- `config_manager.py`：读写 `settings.json`，`get_api_key_status()` 检查各 LLM 提供商 API Key 配置状态
- `signal_notifier.py`：`SignalNotifier` 管理交易信号记录和 Coze 推送

### frontend/ — 前端

12 个页面，Composition API (`<script setup>`)，无 Pinia/Vuex，每个视图自管理状态。

#### 全局模式
- API 调用：`api.get/post/put/delete`，拦截器自动解包 `response.data`
- 错误处理：统一 `catch (e) { error.value = e.message }`
- 多个 API 调用用 `Promise.all` 并行化
- 多图表用 `useChart()` 解构重命名

#### 共享组件
- `MetricCard.vue` — 指标卡片 (value/label/color/delta)
- `DataTable.vue` — 通用表格 (columns/rows/title/emptyText, 支持 slot 和 format)
- `LoadingSpinner.vue` — 加载指示器
- `ToggleSwitch.vue` — 开关组件 (v-model)
- `TermTooltip.vue` — 金融术语悬浮提示 (31 个术语)

#### 共享组合式函数
- `useChart.js` — ECharts 生命周期管理 (init/render/dispose + resize)
- `useBroker.js` — 券商类型查询 (`cashEnabled/brokerType/brokerLabel/loadBroker`)

#### 路由
| 路径 | 视图 | 功能 |
|------|------|------|
| `/market` | MarketView | 指数+涨跌榜+板块热点+走势图 |
| `/stock` | StockView | K线+技术指标+AI 分析 (SSE 流式 5 角色辩论) |
| `/sectors` | SectorView | 板块选股+支撑/压力位批量扫描 |
| `/portfolio` | PortfolioView | 持仓管理+模拟资金管理 |
| `/alerts` | AlertView | 风险告警+定时调度+逐只/批量扫描+阈值管理 |
| `/backtest` | BacktestView | 回测 (动态参数表单+资金曲线+交易明细) |
| `/lab` | StrategyLab | 网格搜索/遗传算法参数优化 |
| `/sentiment` | SentimentView | 市场情绪+板块排名+个股情绪柱状图 |
| `/trading` | TradingView | 下单+委托/成交/持仓+资金总览 |
| `/live` | LiveTradingView | 实盘策略运行+信号融合配置+强制平仓开关 |
| `/editor` | StrategyEditor | 策略代码编辑器 (文件列表+编辑器+AI 生成) |
| `/qlib` | QlibLab | AI 模型训练/预测/回测 (Options API) |

#### 前端全局状态
`AlertView` 中 `scannedCodes` 缓存扫描结果 (上限 200)，`expanded` 控制详情展开。`LiveTradingView` 通过 `setInterval(5000)` 轮询运行器状态，`setInterval(30000)` 轮询账户。`BacktestView` 策略变更时动态渲染参数输入框。

## 配置

`config.py` — 通过 `python-dotenv` 加载 `.env`。`.env.example` 作为模板。关键配置组：

- **LLM**：`LLM_PROVIDER` (deepseek/qwen), API Key, Model, Base URL
- **MySQL**：Host/Port/User/Password/Database, `MYSQL_ENABLED` 自动判断
- **Broker**：`BROKER_TYPE` (fake/qmt/easytrader), QMT 路径/账号/session_id, 同花顺账号/密码/exe路径
- **通知**：`WECOM_BOT_KEY` (支持完整 URL 或纯 key), `COZE_API_TOKEN/BOT_ID/WORKFLOW_ID`
- **定时扫描**：早盘/尾盘时间 (默认 09:35/14:55), 阈值 (默认 7)
- **强制平仓**：开关/时间 (默认 14:54)/原因
- **信号融合**：开关/模式 (filter/override)/最小置信度/各指标权重
- **qlib**：开关/数据目录/模型/因子集/线程数/训练超时
- **缓存**：各类数据 TTL (行情 1h/LLM 5min/名称 24h/财务 24h)

## 关键设计要点

### QMT Broker 注意事项
1. **Session 锁文件**：进程异常退出后残留的 `lock_*_win_{id}` 文件阻止同 session_id 重连，`_cleanup_stale_locks()` 自动清理
2. **`run_forever()` 必须运行**：daemon 线程维持心跳和处理异步回调，否则 `order_stock()` 挂死
3. **仅支持 `FIX_PRICE=11`**：该 QMT 版本不支持 `LATEST_PRICE=5` 和 `PRTP_MARKET=12`
4. **市价单曲线**：自动获取行情价 (tick→PreClose 回退)，非活跃时段 `get_full_tick()` 返回空字典
5. **符号必须带后缀**：`_normalize_symbol()` 自动补全 `.SH`/`.SZ`

### MySQL SSL
`ssl={"ssl_disabled": True}` + 健壮的连接检查 + 重试前强制关闭 socket

### OpenBLAS 线程冲突
Windows 上启动后端必须设 `OPENBLAS_NUM_THREADS=1`，否则 ThreadPoolExecutor 中 numpy 操作导致内存分配失败

### 策略双轨制
每个策略文件同时包含 `BaseStrategy` 子类 (backtrader 回测) 和 `LiveStrategy` 子类 (无 backtrader 依赖的纯 Python 实盘版)。`auto_discover()` 和 `LIVE_STRATEGIES` 两个注册表独立管理。

### 数据回退链
日K线 7 级回退 (miniQMT→腾讯→网易→akshare→BaoStock→MySQL→异常)，实时行情 3 级回退 (miniQMT→akshare→缓存)。几乎所有数据路径都有多层容错。

### API 响应格式
所有端点 `{"data": ...}` 或 `{"status": "ok"}`。POST 请求 JSON body 参数需用 `Body()` 显式注解。

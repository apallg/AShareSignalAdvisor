import sys
import logging
import math
import json
from pathlib import Path
from typing import Any
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


def _sanitize_float(v: Any) -> Any:
    """递归清理 NaN/Infinity 为 None，确保 JSON 可序列化"""
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(v, dict):
        return {k: _sanitize_float(vv) for k, vv in v.items()}
    if isinstance(v, (list, tuple)):
        return [_sanitize_float(item) for item in v]
    return v


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        sanitized = _sanitize_float(content)
        return json.dumps(
            sanitized,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="Apallg投研 - A股量化分析",
    version="1.0.0",
    default_response_class=SafeJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.api import stock, market, sectors, portfolio, alerts, backtest, sentiment, news, trading, live_trading, strategies, scheduler as scheduler_api
from backend.api import qlib as qlib_api

app.include_router(market.router, prefix="/api/market", tags=["大盘"])
app.include_router(stock.router, prefix="/api/stock", tags=["个股"])
app.include_router(sectors.router, prefix="/api/sectors", tags=["板块"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["持仓"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["告警"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])
app.include_router(sentiment.router, prefix="/api/sentiment", tags=["情绪"])
app.include_router(news.router, prefix="/api/news", tags=["新闻"])
app.include_router(trading.router, prefix="/api/trading", tags=["交易"])
app.include_router(live_trading.router, prefix="/api/live", tags=["实盘"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["策略管理"])
app.include_router(scheduler_api.router, prefix="/api/scheduler", tags=["定时扫描"])
app.include_router(qlib_api.router, prefix="/api/qlib", tags=["Qlib ML"])

import time
import threading

def _init_database():
    for attempt in range(30):
        try:
            from core.database import Database
            if Database.is_available():
                Database.create_tables()
                logger.info(f"数据库表已就绪 (第{attempt+1}次尝试)")
                return
            else:
                logger.info(f"数据库未启用 (第{attempt+1}次尝试)")
        except Exception as e:
            logger.warning(f"数据库连接中... (第{attempt+1}次: {e})")
        time.sleep(2)
    logger.warning("数据库初始化已跳过")

def _init_baostock_industry():
    """启动时预加载 baostock 行业分类缓存，确保板块查询回退时有数据可用"""
    try:
        from core.data_fetcher import DataFetcher
        fetcher = DataFetcher()
        ind_map = fetcher.get_industry_map()
        if ind_map:
            logger.info(f"BaoStock 行业映射已缓存 ({len(ind_map)}只)")
        else:
            logger.warning("BaoStock 行业映射为空，板块回退可能不可用")
    except Exception as e:
        logger.warning(f"BaoStock 行业映射初始化失败: {e}")


@app.on_event("startup")
def startup():
    threading.Thread(target=_init_database, daemon=True).start()
    from core.scheduler import get_scheduler
    get_scheduler().start()
    _init_qlib_data()
    threading.Thread(target=_init_baostock_industry, daemon=True).start()


def _init_qlib_data():
    """启动时检查 qlib 数据目录，如果为空则从数据库同步"""
    import config
    data_dir = config.QLIB_DATA_DIR
    cal_file = data_dir / "calendars" / "day.txt"
    if not cal_file.exists() and config.MYSQL_ENABLED:
        try:
            from qlib_integration.bridge import QlibDataBridge
            bridge = QlibDataBridge(data_dir)
            result = bridge.sync_all()
            logger.info(f"qlib 数据初始化完成: {result}")
        except Exception as e:
            logger.warning(f"qlib 数据初始化跳过 (数据库可能无数据): {e}")

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Apallg投研", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    logger.info("启动 Apallg投研 API 服务器 http://0.0.0.0:8000")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)

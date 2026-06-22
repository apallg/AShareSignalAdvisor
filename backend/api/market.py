"""大盘数据 API"""
from fastapi import APIRouter
from core.data_fetcher import DataFetcher
from core.realtime import RealtimeEngine

router = APIRouter()
fetcher = DataFetcher()
rt = RealtimeEngine()


@router.get("/indices")
def get_indices():
    """四大指数实时行情"""
    return {"data": rt.get_indices()}


@router.get("/index-chart")
def get_index_chart(index_name: str = "上证指数", days: int = 120):
    """指数历史走势"""
    try:
        df = fetcher.get_index_daily(index_name, days)
        if df is None or df.empty:
            return {"data": []}
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        return {"data": [], "error": str(e)}


@router.get("/top-gainers")
def top_gainers(n: int = 20):
    """涨幅榜"""
    return {"data": rt.get_top_gainers(n)}


@router.get("/top-losers")
def top_losers(n: int = 20):
    """跌幅榜"""
    return {"data": rt.get_top_losers(n)}


@router.get("/sectors")
def get_sectors():
    """板块热点"""
    try:
        df = fetcher.get_sector_performance()
        if df is None or df.empty:
            return {"data": []}
        return {"data": df.to_dict(orient="records"), "source": fetcher.get_sources().get("sectors", "未知")}
    except Exception as e:
        return {"data": [], "error": str(e)}

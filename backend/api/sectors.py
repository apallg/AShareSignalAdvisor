"""板块选股 API"""
import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from core.stock_scanner import SectorScanner
from core.sector_heatmap import scan_sector_heatmap as _scan_sector_heatmap
from core.data_fetcher import DataFetcher

router = APIRouter()
scanner = SectorScanner()
logger = logging.getLogger(__name__)


@router.get("/list")
def list_sectors():
    """获取所有板块"""
    try:
        df = scanner.get_all_sectors()
        if df is None or df.empty:
            return {"data": []}
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        logger.error(f"板块API异常: {e}")
        return JSONResponse(status_code=503, content={"data": [], "error": str(e), "retry": True})


@router.get("/hot")
def hot_sectors(limit: int = Query(20, ge=5, le=50)):
    """
    热门板块排行

    按涨跌幅绝对值降序排列，返回最活跃的板块。
    """
    try:
        fetcher = DataFetcher()
        df = fetcher.get_sector_performance()
        if df is None or df.empty:
            return {"data": []}
        if "涨跌幅" in df.columns:
            df["abs_pct"] = df["涨跌幅"].astype(float).abs()
            df = df.sort_values("abs_pct", ascending=False)
        result = []
        for _, row in df.head(limit).iterrows():
            result.append({
                "name": str(row.get("板块名称", "")),
                "pct_chg": round(float(row.get("涨跌幅", 0)), 2),
            })
        return {"data": result}
    except Exception as e:
        logger.error(f"板块API异常: {e}")
        return JSONResponse(status_code=503, content={"data": [], "error": str(e), "retry": True})


@router.get("/scan-all")
def scan_all_sectors(
    max_per_sector: int = Query(30, ge=10, le=50),
    max_results: int = Query(200, ge=50, le=500),
):
    """
    全板块支撑/压力位扫描

    遍历所有板块，对成交量靠前的股票做支撑/压力分析，
    只返回有交易信号的股票，跨板块混合排序。
    """
    try:
        results = scanner.scan_all_sectors_sr(
            max_per_sector=max_per_sector, max_results=max_results,
        )
        return {"data": results}
    except Exception as e:
        logger.error(f"板块API异常: {e}")
        return JSONResponse(status_code=503, content={"data": [], "error": str(e), "retry": True})


@router.get("/dense-zones-all")
def scan_all_dense_zones(
    max_per_sector: int = Query(30, ge=10, le=50),
    max_results: int = Query(200, ge=50, le=500),
    window: int = Query(40, ge=20, le=120),
    n_zones: int = Query(3, ge=1, le=10),
):
    """
    全板块密集成交区扫描

    遍历所有板块，对成交量靠前的股票做密集区分析，
    按盈亏比降序排列，跨板块混合。
    """
    try:
        results = scanner.scan_all_sectors_dz(
            max_per_sector=max_per_sector, max_results=max_results,
            window=window, n_zones=n_zones,
        )
        return {"data": results}
    except Exception as e:
        logger.error(f"板块API异常: {e}")
        return JSONResponse(status_code=503, content={"data": [], "error": str(e), "retry": True})


@router.get("/{sector_name}/stocks")
def get_sector_stocks(sector_name: str):
    """获取板块下股票"""
    try:
        df = scanner.get_sector_stocks(sector_name)
        if df is None or df.empty:
            return {"data": []}
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        logger.error(f"板块API异常: {e}")
        return JSONResponse(status_code=503, content={"data": [], "error": str(e), "retry": True})


@router.get("/{sector_name}/support-resistance")
def scan_support_resistance(sector_name: str):
    """批量扫描板块内接近支撑位/压力位的股票（布林带+均线法）"""
    try:
        results = scanner.scan_support_resistance(sector_name)
        return {"data": results}
    except Exception as e:
        logger.error(f"板块API异常: {e}")
        return JSONResponse(status_code=503, content={"data": [], "error": str(e), "retry": True})


@router.get("/{sector_name}/dense-zones")
def scan_dense_zones(
    sector_name: str,
    max_stocks: int = Query(80, ge=10, le=200),
    window: int = Query(40, ge=20, le=120),
    n_zones: int = Query(3, ge=1, le=10),
):
    """
    板块密集成交区扫描（成交量加权密度剖面算法）

    相比支撑/压力位扫描，此端点提供：
    - 量价加权的真实筹码分布
    - 多密集区同时检测（不只是最近支撑/压力）
    - 盈亏比计算
    - 板块级别聚合统计（支撑占比/压力占比/多空状态）
    """
    try:
        result = scanner.scan_dense_zones(
            sector_name, max_stocks=max_stocks,
            window=window, n_zones=n_zones,
        )
        return {"data": result}
    except Exception as e:
        logger.error(f"板块API异常(dense-zones): {e}")
        return JSONResponse(status_code=503, content={"data": {}, "error": str(e), "retry": True})


@router.get("/heatmap")
def sector_heatmap(
    stock_count: int = Query(200, ge=50, le=500),
    window: int = Query(40, ge=20, le=120),
    n_zones: int = Query(3, ge=1, le=10),
):
    """
    全市场板块热力图

    按行业聚合统计密集区支撑/压力分布，
    返回每个行业的多空状态、平均盈亏比、支撑占比等。
    """
    try:
        result = _scan_sector_heatmap(
            stock_count=stock_count, window=window, n_zones=n_zones,
        )
        return {"data": result}
    except Exception as e:
        logger.error(f"板块API异常: {e}")
        return JSONResponse(status_code=503, content={"data": [], "error": str(e), "retry": True})

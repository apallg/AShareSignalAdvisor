"""板块选股 API"""
from fastapi import APIRouter
from core.stock_scanner import SectorScanner

router = APIRouter()
scanner = SectorScanner()


@router.get("/list")
def list_sectors():
    """获取所有板块"""
    try:
        df = scanner.get_all_sectors()
        if df is None or df.empty:
            return {"data": []}
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        return {"data": [], "error": str(e)}


@router.get("/{sector_name}/stocks")
def get_sector_stocks(sector_name: str):
    """获取板块下股票"""
    try:
        df = scanner.get_sector_stocks(sector_name)
        if df is None or df.empty:
            return {"data": []}
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        return {"data": [], "error": str(e)}


@router.get("/{sector_name}/support-resistance")
def scan_support_resistance(sector_name: str):
    """批量扫描板块内接近支撑位/压力位的股票"""
    try:
        results = scanner.scan_support_resistance(sector_name)
        return {"data": results}
    except Exception as e:
        return {"data": [], "error": str(e)}

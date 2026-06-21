"""风险告警 API"""
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Body

router = APIRouter()


@router.get("/")
def list_alerts(limit: int = 50, level: str = ""):
    from core.database import RiskAlertRepo
    alerts = RiskAlertRepo.get_recent(limit)
    if level:
        alerts = [a for a in alerts if a["risk_level"] == level]
    return {"data": alerts}


@router.get("/stats")
def alert_stats(limit: int = 200):
    from core.database import RiskAlertRepo
    alerts = RiskAlertRepo.get_recent(limit)
    stats = {"high": 0, "mid": 0, "low": 0}
    for a in alerts:
        level = a.get("risk_level", "")
        if level == "高风险":
            stats["high"] += 1
        elif level == "中风险":
            stats["mid"] += 1
        else:
            stats["low"] += 1
    return {"data": stats}


@router.get("/channels")
def notification_channels():
    from utils.notifier import get_channel_status
    return {"data": get_channel_status()}


@router.post("/test")
def test_notification():
    from utils.notifier import send_test_notification
    result = send_test_notification()
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"data": result}


@router.post("/scan/{code}")
def scan_single(code: str, threshold: int = Body(0), include: Optional[Dict[str, bool]] = Body(None)):
    """扫描单只持仓，include 可选: {"technical":true,"financial":true,"patterns":true,"realtime":true}"""
    from core.database import HoldingsRepo
    from core.portfolio_manager import PortfolioScanner
    holding = HoldingsRepo.get_by_code(code)
    if not holding:
        raise HTTPException(404, f"未找到持仓: {code}")
    try:
        scanner = PortfolioScanner()
        result = scanner.scan_holding(holding, include=include)
        if result and result["risk_score"] >= threshold:
            scanner._persist_alert(result)
            scanner._notify_if_needed(result, holding)
        return {"data": result}
    except Exception as e:
        raise HTTPException(500, f"扫描 {code} 失败: {e}")

@router.post("/scan")
def trigger_scan(threshold: int = Body(5), include: Optional[Dict[str, bool]] = Body(None)):
    """批量扫描全部持仓，include 可选: {"technical":true,"financial":false,...}"""
    from core.portfolio_manager import PortfolioScanner
    try:
        scanner = PortfolioScanner()
        results = scanner.scan_all(threshold=threshold, include=include)
        return {"data": {"count": len(results), "results": results}}
    except Exception as e:
        raise HTTPException(500, f"扫描失败: {e}")

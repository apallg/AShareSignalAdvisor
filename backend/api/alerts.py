"""风险告警 API"""
from fastapi import APIRouter

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
    """查询通知通道状态"""
    from utils.notifier import get_channel_status
    return {"data": get_channel_status()}


@router.post("/test")
def test_notification():
    """发送测试通知"""
    from utils.notifier import send_test_notification
    result = send_test_notification()
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(400, result["error"])
    return {"data": result}


@router.post("/scan")
def trigger_scan():
    """手动触发持仓扫描"""
    try:
        from core.portfolio_manager import PortfolioScanner
        scanner = PortfolioScanner()
        results = scanner.scan_all(threshold=0)
        return {"data": {"count": len(results), "results": results}}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(500, f"扫描失败: {e}")

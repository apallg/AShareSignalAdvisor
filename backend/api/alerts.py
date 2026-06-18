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

"""持仓管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class HoldingCreate(BaseModel):
    code: str
    name: str
    shares: int
    cost_price: float
    buy_date: str = ""
    alerts_enabled: bool = True
    risk_threshold: int = 7


@router.get("/holdings")
def list_holdings():
    from core.database import HoldingsRepo
    return {"data": HoldingsRepo.get_all()}


@router.post("/holdings")
def add_holding(h: HoldingCreate):
    from core.database import HoldingsRepo, Database
    if not Database.is_available():
        raise HTTPException(503, "数据库未连接")
    HoldingsRepo.add(h.code, h.name, h.shares, h.cost_price,
                     h.buy_date, h.alerts_enabled, h.risk_threshold)
    return {"status": "ok"}


@router.put("/holdings/{code}")
def update_holding(code: str, data: dict):
    """更新持仓：risk_threshold, alerts_enabled 等"""
    from core.database import HoldingsRepo
    HoldingsRepo.update(code, **data)
    return {"status": "ok"}


@router.delete("/holdings/{code}")
def delete_holding(code: str):
    from core.database import HoldingsRepo
    HoldingsRepo.delete(code)
    return {"status": "ok"}

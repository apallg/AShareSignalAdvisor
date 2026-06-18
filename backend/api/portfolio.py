"""持仓管理 + 风险扫描 API"""
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# 前端数据源勾选 → 后端 include 字段映射
_FRONTEND_INCLUDE_MAP = {
    "tech": "technical",
    "fundamental": "financial",
    "capital": "capital_flow",
    "news": "sentiment",
    "market": "market_env",
}


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


@router.delete("/holdings/{code}")
def delete_holding(code: str):
    from core.database import HoldingsRepo
    HoldingsRepo.delete(code)
    return {"status": "ok"}


@router.post("/scan")
def scan_portfolio(threshold: int = 5, include: Optional[Dict[str, bool]] = None):
    """批量风险扫描"""
    from core.portfolio_manager import PortfolioScanner
    # 翻译前端 key → 后端 key
    if include:
        include = {_FRONTEND_INCLUDE_MAP.get(k, k): v for k, v in include.items()}
    scanner = PortfolioScanner()
    alerts = scanner.scan_all(threshold=threshold, include=include)
    return {"data": alerts}

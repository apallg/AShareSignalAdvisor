"""交易执行 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_broker = None


def get_broker():
    global _broker
    if _broker is None:
        from core.data_fetcher import DataFetcher
        fetcher = DataFetcher()

        def price_provider(symbol):
            try:
                q = fetcher.get_realtime_quote(symbol)
                price = q.get("最新价") or q.get("price") or 0
                return float(price)
            except Exception:
                return 0

        from execution import FakeBroker
        _broker = FakeBroker(price_provider=price_provider)
        _broker.connect()

        # 从账户表恢复资金状态
        try:
            from core.database import Database
            if Database.is_available():
                row = Database.fetchone(
                    "SELECT * FROM accounts WHERE id=%s", (_broker.account_id,))
                if row:
                    _broker._cash = float(row["cash"])
                    _broker._frozen = float(row["frozen"])
                else:
                    _broker._save_account()
        except Exception:
            pass

    return _broker


class OrderRequest(BaseModel):
    symbol: str
    name: str = ""
    side: str  # "buy" | "sell"
    quantity: int
    price_type: str = "market"  # "market" | "limit"
    price: float = 0


@router.get("/account")
def get_account():
    broker = get_broker()
    return {"data": broker.get_account()}


@router.get("/orders")
def list_orders(status: str = ""):
    broker = get_broker()
    orders = broker.get_orders(status=status or None)
    return {"data": list(reversed(orders))}


@router.get("/orders/{order_id}")
def get_order(order_id: str):
    broker = get_broker()
    order = broker.get_order(order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    return {"data": order}


@router.post("/orders")
def place_order(req: OrderRequest):
    if req.side not in ("buy", "sell"):
        raise HTTPException(400, "side 必须为 buy 或 sell")
    if req.price_type not in ("market", "limit"):
        raise HTTPException(400, "price_type 必须为 market 或 limit")
    if req.quantity <= 0:
        raise HTTPException(400, "数量必须大于 0")

    broker = get_broker()
    try:
        order_id = broker.place_order(
            req.symbol, req.name, req.side, req.quantity,
            req.price_type, req.price)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    order = broker.get_order(order_id)
    broker._save_account()
    return {"data": order}


@router.delete("/orders/{order_id}")
def cancel_order(order_id: str):
    broker = get_broker()
    ok = broker.cancel_order(order_id)
    if not ok:
        raise HTTPException(400, "订单无法撤销（可能已成交）")
    broker._save_account()
    return {"status": "ok"}


@router.get("/trades")
def list_trades(symbol: str = ""):
    broker = get_broker()
    trades = broker.get_trades(symbol=symbol or None)
    return {"data": list(reversed(trades))}


@router.get("/positions")
def get_positions():
    broker = get_broker()
    return {"data": broker.get_positions()}

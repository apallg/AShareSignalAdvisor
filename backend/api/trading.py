"""交易执行 API"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

_broker = None


def _make_price_provider():
    from core.data_fetcher import DataFetcher
    fetcher = DataFetcher()
    def price_provider(symbol):
        try:
            q = fetcher.get_realtime_quote(symbol)
            return float(q.get("最新价") or q.get("price") or 0)
        except Exception:
            return 0
    return price_provider


def get_broker():
    global _broker
    if _broker is not None:
        if not _broker.connected:
            logger.warning("Broker 连接已断开，尝试重连...")
            try:
                ok = _broker.connect()
                if ok:
                    logger.info("Broker 重连成功")
                else:
                    logger.warning("Broker 重连失败")
            except Exception as e:
                logger.warning(f"Broker 重连异常: {e}")
        return _broker

    from config import BROKER_TYPE, BROKER_QMT, BROKER_FAKE, BROKER_EASYT
    from execution import create_broker

    if BROKER_TYPE == BROKER_EASYT:
        from config import EASYTRAIDER_USER, EASYTRAIDER_PASSWORD, EASYTRAIDER_EXE_PATH
        if not EASYTRAIDER_USER:
            raise RuntimeError("EASYTRAIDER_USER 未配置，请在 .env 中设置同花顺账号")
        broker = create_broker(BROKER_EASYT,
                                user=EASYTRAIDER_USER,
                                password=EASYTRAIDER_PASSWORD,
                                exe_path=EASYTRAIDER_EXE_PATH)
        try:
            broker.connect()
            _broker = broker
        except Exception as e:
            logger.warning(
                f"Easytrader 连接失败，回退到模拟交易: {e}\n"
                f"请确认同花顺客户端已打开并登录银河证券，然后重启后端"
            )
            _broker = create_broker(BROKER_FAKE, price_provider=_make_price_provider())
            _broker.connect()

    elif BROKER_TYPE == BROKER_QMT:
        from config import QMT_USERDATA_DIR, QMT_ACCOUNT, QMT_SESSION_ID
        if not QMT_ACCOUNT:
            raise RuntimeError("QMT_ACCOUNT 未配置，请在 .env 中设置 QMT 资金账号")
        broker = create_broker(BROKER_QMT,
                                userdata_dir=QMT_USERDATA_DIR,
                                account=QMT_ACCOUNT,
                                session_id=QMT_SESSION_ID)
        ok = broker.connect()
        if not ok:
            logger.warning(
                "QMT Broker 连接失败（miniQMT 可能未启动或未登录），"
                "后续请求将自动重试连接。请确保：\n"
                "  1. 迅投极速交易终端 已启动\n"
                "  2. 账户已登录\n"
                "  3. userdata_mini 路径正确"
            )
        _broker = broker

    else:
        _broker = create_broker(BROKER_FAKE, price_provider=_make_price_provider())
        _broker.connect()

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


def is_fake_broker():
    from execution import is_fake_broker as check
    return check(get_broker())


class OrderRequest(BaseModel):
    symbol: str
    name: str = ""
    side: str  # "buy" | "sell"
    quantity: int
    price_type: str = "market"  # "market" | "limit"
    price: float = 0


@router.get("/broker")
def get_broker_info():
    broker = get_broker()
    from execution import is_fake_broker
    is_fake = is_fake_broker(broker)
    return {"data": {
        "type": broker.account_id.split("-")[0].lower() if is_fake else "broker",
        "is_fake": is_fake,
        "account_id": broker.account_id,
        "cash_enabled": is_fake,
    }}


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
    if is_fake_broker():
        broker._save_account()
    return {"data": order}


@router.delete("/orders/{order_id}")
def cancel_order(order_id: str):
    broker = get_broker()
    ok = broker.cancel_order(order_id)
    if not ok:
        raise HTTPException(400, "订单无法撤销（可能已成交）")
    if is_fake_broker():
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


class CashRequest(BaseModel):
    amount: float


@router.post("/account/cash")
def add_cash(req: CashRequest):
    if not is_fake_broker():
        raise HTTPException(400, "QMT 实盘不支持模拟出入金")
    broker = get_broker()
    try:
        return {"data": broker.add_cash(req.amount)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/account/cash")
def set_cash(req: CashRequest):
    if not is_fake_broker():
        raise HTTPException(400, "QMT 实盘不支持模拟出入金")
    broker = get_broker()
    try:
        return {"data": broker.set_cash(req.amount)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/account/withdraw")
def withdraw_cash(req: CashRequest):
    if not is_fake_broker():
        raise HTTPException(400, "QMT 实盘不支持模拟出入金")
    broker = get_broker()
    try:
        return {"data": broker.withdraw_cash(req.amount)}
    except ValueError as e:
        raise HTTPException(400, str(e))

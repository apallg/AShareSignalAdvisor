"""
FakeBroker — 本地模拟撮合，无需 QMT 权限，用于开发调试。
接口与 BaseBroker 完全一致，后续切换 QmtBroker 时策略层零改动。
"""
import uuid
import logging
from datetime import datetime
from collections import OrderedDict
from .base import BaseBroker

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_FILLED = "filled"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"


class FakeBroker(BaseBroker):
    def __init__(self, initial_cash=1000000, commission_rate=0.0003,
                 stamp_duty=0.001, price_provider=None):
        self._cash = initial_cash
        self._frozen = 0  # 冻结资金（限价单）
        self._commission_rate = commission_rate
        self._stamp_duty = stamp_duty  # 仅卖出
        self._price_provider = price_provider or (lambda s: 0)

        self._orders = OrderedDict()
        self._trades = []
        self._holdings = {}  # symbol -> {shares, avg_cost}

        self._connected = False
        self._account_id = "FAKE-" + uuid.uuid4().hex[:8].upper()

    def connect(self):
        self._connected = True
        logger.info(f"FakeBroker 已连接, 账户: {self._account_id}")
        return True

    def disconnect(self):
        self._connected = False

    @property
    def connected(self):
        return self._connected

    @property
    def account_id(self):
        return self._account_id

    def place_order(self, symbol, name, side, quantity, price_type, price=None):
        if not self._connected:
            raise RuntimeError("Broker 未连接")

        order_id = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()
        price = float(price) if price else 0

        order = {
            "id": order_id,
            "symbol": symbol,
            "name": name,
            "side": side,
            "quantity": int(quantity),
            "price_type": price_type,
            "price": price,
            "filled_qty": 0,
            "filled_price": 0,
            "status": STATUS_PENDING,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        current_price = self._price_provider(symbol)
        est_cost = (price or current_price) * int(quantity)
        if side == "buy" and est_cost > self._cash - self._frozen:
            order["status"] = STATUS_REJECTED
            self._orders[order_id] = order
            logger.warning(f"资金不足拒绝: {order_id}")
            self._persist_order(order)
            return order_id

        if price_type == "market" or price <= 0:
            fill_price = current_price or price
            self._fill_order(order, fill_price)
        else:
            if current_price and (
                (side == "buy" and current_price <= price) or
                (side == "sell" and current_price >= price)
            ):
                self._fill_order(order, price)
            else:
                self._frozen += est_cost

        self._orders[order_id] = order
        self._persist_order(order)
        logger.info(f"下单: {symbol} {side} {quantity}股 @ {price or '市价'} → {order['status']}")

        return order_id

    def cancel_order(self, order_id):
        order = self._orders.get(order_id)
        if not order or order["status"] != STATUS_PENDING:
            return False
        current_price = self._price_provider(order["symbol"])
        est_cost = (order["price"] or current_price) * order["quantity"]
        self._frozen = max(0, self._frozen - est_cost)
        order["status"] = STATUS_CANCELLED
        order["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._persist_order(order)
        return True

    def get_order(self, order_id):
        return self._orders.get(order_id)

    def get_orders(self, status=None):
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o["status"] == status]
        return orders

    def get_trades(self, symbol=None):
        if symbol:
            return [t for t in self._trades if t["symbol"] == symbol]
        return list(self._trades)

    def get_positions(self):
        result = []
        for symbol, h in self._holdings.items():
            if h["shares"] <= 0:
                continue
            price = self._price_provider(symbol)
            market_value = h["shares"] * price
            cost = h["shares"] * h["avg_cost"]
            result.append({
                "symbol": symbol, "shares": h["shares"],
                "avg_cost": round(h["avg_cost"], 3),
                "current_price": round(price, 3),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(market_value - cost, 2),
            })
        return result

    def get_account(self):
        positions = self.get_positions()
        total_market = sum(p["market_value"] for p in positions)
        total_pnl = sum(p["unrealized_pnl"] for p in positions)
        return {
            "account_id": self._account_id,
            "cash": round(self._cash, 2),
            "frozen": round(self._frozen, 2),
            "available": round(self._cash - self._frozen, 2),
            "market_value": round(total_market, 2),
            "total_assets": round(self._cash + total_market, 2),
            "unrealized_pnl": round(total_pnl, 2),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def add_cash(self, amount):
        if amount <= 0:
            raise ValueError("充值金额必须大于0")
        self._cash += amount
        self._save_account()
        return self.get_account()

    def set_cash(self, amount):
        if amount < 0:
            raise ValueError("资金不能为负")
        self._cash = amount
        self._save_account()
        return self.get_account()

    def withdraw_cash(self, amount):
        if amount <= 0:
            raise ValueError("出金金额必须大于0")
        if amount > self._cash - self._frozen:
            raise ValueError(f"可用资金不足 (可用: {self._cash - self._frozen:.2f})")
        self._cash -= amount
        self._save_account()
        return self.get_account()

    def _fill_order(self, order, fill_price):
        qty = order["quantity"]
        cost = fill_price * qty
        commission = max(5, cost * self._commission_rate)
        stamp = cost * self._stamp_duty if order["side"] == "sell" else 0
        total_cost = cost + commission + stamp

        if order["side"] == "buy":
            if total_cost > self._cash - self._frozen:
                order["status"] = STATUS_REJECTED
                return
            self._cash -= total_cost
            h = self._holdings.get(order["symbol"], {"shares": 0, "avg_cost": 0})
            old_total = h["shares"] * h["avg_cost"]
            h["shares"] += qty
            h["avg_cost"] = (old_total + cost) / h["shares"] if h["shares"] > 0 else fill_price
            self._holdings[order["symbol"]] = h
        else:
            h = self._holdings.get(order["symbol"])
            if not h or h["shares"] < qty:
                order["status"] = STATUS_REJECTED
                return
            h["shares"] -= qty
            self._cash += cost - commission - stamp

        order["filled_qty"] = qty
        order["filled_price"] = fill_price
        order["status"] = STATUS_FILLED
        order["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        trade = {
            "id": "T" + order["id"][:14] + uuid.uuid4().hex[:4].upper(),
            "order_id": order["id"],
            "symbol": order["symbol"],
            "name": order["name"],
            "side": order["side"],
            "price": round(fill_price, 3),
            "quantity": qty,
            "amount": round(cost, 2),
            "commission": round(commission, 2),
            "stamp_duty": round(stamp, 2),
            "trade_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._trades.append(trade)
        self._persist_trade(trade)

    def _save_account(self):
        try:
            from core.database import Database
            if not Database.is_available():
                return
            Database.execute(
                "INSERT INTO accounts (id,cash,frozen,market_value,total_assets) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "cash=VALUES(cash),frozen=VALUES(frozen),"
                "market_value=VALUES(market_value),total_assets=VALUES(total_assets)",
                (self.account_id, self._cash, self._frozen, 0, self._cash))
        except Exception as e:
            logger.debug(f"account持久化跳过: {e}")

"""
交易执行抽象接口，所有 Broker 实现必须遵循此接口
"""
import logging

logger = logging.getLogger(__name__)


class BaseBroker:
    def _persist_order(self, order):
        try:
            from core.database import Database
            if not Database.is_available():
                return
            Database.execute(
                "INSERT INTO orders (id,symbol,name,side,quantity,price_type,price,"
                "filled_qty,filled_price,status,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE filled_qty=VALUES(filled_qty),"
                "filled_price=VALUES(filled_price),status=VALUES(status),"
                "updated_at=VALUES(updated_at)",
                (order["id"], order["symbol"], order["name"], order["side"],
                 order["quantity"], order["price_type"], order["price"],
                 order["filled_qty"], order["filled_price"], order["status"],
                 order["created_at"], order["updated_at"]))
        except Exception as e:
            logger.debug(f"order持久化跳过: {e}")

    def _persist_trade(self, trade):
        try:
            from core.database import Database
            if not Database.is_available():
                return
            Database.execute(
                "INSERT INTO trades (id,order_id,symbol,name,side,price,quantity,"
                "amount,commission,stamp_duty,trade_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (trade["id"], trade["order_id"], trade["symbol"], trade["name"],
                 trade["side"], trade["price"], trade["quantity"],
                 trade["amount"], trade["commission"], trade["stamp_duty"],
                 trade["trade_time"]))
        except Exception as e:
            logger.debug(f"trade持久化跳过: {e}")
    def connect(self) -> bool:
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    @property
    def connected(self) -> bool:
        raise NotImplementedError

    @property
    def account_id(self) -> str:
        raise NotImplementedError

    def place_order(self, symbol, name, side, quantity, price_type, price=None):
        """
        下单，返回 order_id。
        side: "buy" | "sell"
        price_type: "market" | "limit"
        """
        raise NotImplementedError

    def cancel_order(self, order_id) -> bool:
        raise NotImplementedError

    def get_order(self, order_id):
        raise NotImplementedError

    def get_orders(self, status=None):
        raise NotImplementedError

    def get_trades(self, symbol=None):
        raise NotImplementedError

    def get_positions(self):
        raise NotImplementedError

    def get_account(self):
        raise NotImplementedError

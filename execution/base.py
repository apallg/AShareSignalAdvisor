"""
交易执行抽象接口，所有 Broker 实现必须遵循此接口
"""


class BaseBroker:
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

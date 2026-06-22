"""
LiveStrategy — 轻量级实盘策略基类，不依赖 backtrader。
接收已附带技术指标的 DataFrame，返回交易信号。
"""


class LiveStrategy:
    name = ""
    description = ""
    params = {}  # {name: default}

    def __init__(self, **kwargs):
        for k, v in self.params.items():
            setattr(self, k, kwargs.get(k, v))
        self.position = 0  # 当前持仓股数
        self.entry_price = 0

    def check_signal(self, df):
        """
        df: 带全部技术指标的 DataFrame (最新行在末尾)
        返回: dict {action: "buy"|"sell"|"hold", size_ratio: float, reason: str}
        """
        raise NotImplementedError

    def on_fill(self, action, price, quantity):
        """成交后更新内部持仓状态"""
        if action == "buy":
            old_value = self.position * self.entry_price
            self.position += quantity
            self.entry_price = (old_value + price * quantity) / self.position if self.position > 0 else price
        elif action == "sell":
            self.position = max(0, self.position - quantity)
            if self.position == 0:
                self.entry_price = 0

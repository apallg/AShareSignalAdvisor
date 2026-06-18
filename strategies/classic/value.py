"""价值选股策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class ValueStrategy(BaseStrategy):
    params = (("rebalance_days",20),)
    def __init__(self):
        super().__init__()
        self.day_count = 0
    def next(self):
        self.day_count += 1
        if not self.position and self.day_count % self.p.rebalance_days == 0:
            if hasattr(self.data,"pe") and self.data.pe[0] and self.data.pe[0] < 15:
                if hasattr(self.data,"roe") and self.data.roe[0] and self.data.roe[0] > 10:
                    self.buy_signal(reason=f"价值{self.data.pe[0]:.0f}/{self.data.roe[0]:.0f}")
        if self.position and self.entry_price:
            pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
            if pct <= self.p.stop_loss:
                self.sell_signal(reason=f"止损({pct:.1f}%)")

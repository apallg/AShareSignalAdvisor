"""趋势突破策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class BreakoutStrategy(BaseStrategy):
    params = (("period",20),)
    def __init__(self):
        super().__init__()
        self.high = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.low = bt.indicators.Lowest(self.data.low, period=self.p.period)
    def next(self):
        if not self.position:
            if self.data.close[0] > self.high[-1]:
                self.buy_signal(reason=f"突破{self.p.period}日高")
        else:
            if self.data.close[0] < self.low[-1]:
                self.sell_signal(reason=f"跌破{self.p.period}日低")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")

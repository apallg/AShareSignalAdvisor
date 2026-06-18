"""海龟交易法则"""
import backtrader as bt
from strategies.base import BaseStrategy

class TurtleStrategy(BaseStrategy):
    params = (("entry_period",20),("exit_period",10),("atr_period",14),("atr_multiple",2))
    def __init__(self):
        super().__init__()
        self.entry_high = bt.indicators.Highest(self.data.high, period=self.p.entry_period)
        self.exit_low = bt.indicators.Lowest(self.data.low, period=self.p.exit_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
    def next(self):
        if not self.position:
            if self.data.close[0] >= self.entry_high[-1]:
                self.buy_signal(size_ratio=0.3, reason=f"突破{self.p.entry_period}日高")
        else:
            if self.data.close[0] <= self.exit_low[-1]:
                self.sell_signal(reason=f"跌破{self.p.exit_period}日低")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                atr_pct = self.atr[0] / self.data.close[0] * 100 if self.data.close[0] > 0 else 0
                if pct <= -2 * atr_pct:
                    self.sell_signal(reason=f"ATR止损({pct:.1f}%)")
                elif pct >= 2 * self.p.atr_multiple * atr_pct:
                    self.sell_signal(reason=f"止盈({pct:.1f}%)")

"""动量轮动策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    params = (("period",20),("lookback",63))
    def __init__(self):
        super().__init__()
        self.roc = bt.indicators.ROC(self.data.close, period=self.p.lookback)
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
    def next(self):
        roc = self.roc[0] or 0
        above = self.data.close[0] > self.sma[0]
        if not self.position:
            if roc > 0 and above:
                self.buy_signal(reason=f"动量{roc:.1f}%")
        else:
            if roc < -5 or not above:
                self.sell_signal(reason=f"动量弱{roc:.1f}%")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")

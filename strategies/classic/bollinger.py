"""布林带反转策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class BollingerStrategy(BaseStrategy):
    params = (("period",20),("std",2.0))
    def __init__(self):
        super().__init__()
        self.bb = bt.indicators.BollingerBands(self.data.close, period=self.p.period, devfactor=self.p.std)
    def next(self):
        if not self.position:
            if self.data.close[0] <= self.bb.lines.bot[0]:
                self.buy_signal(reason=f"下轨({self.p.period},{self.p.std})")
        else:
            if self.data.close[0] >= self.bb.lines.top[0]:
                self.sell_signal(reason=f"上轨({self.p.period},{self.p.std})")
            elif self.data.close[0] >= self.bb.lines.mid[0]:
                self.sell_signal(reason="回归中轨")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")

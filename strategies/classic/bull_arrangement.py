"""均线多头排列策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class BullArrangementStrategy(BaseStrategy):
    params = (("short",5),("mid",20),("long",60))
    def __init__(self):
        super().__init__()
        self.s = bt.indicators.SMA(self.data.close, period=self.p.short)
        self.m = bt.indicators.SMA(self.data.close, period=self.p.mid)
        self.l = bt.indicators.SMA(self.data.close, period=self.p.long)
    def next(self):
        bull = self.s[0] > self.m[0] > self.l[0]
        bear = self.s[0] < self.m[0] < self.l[0]
        if not self.position and bull:
            self.buy_signal(reason=f"多头({self.p.short},{self.p.mid},{self.p.long})")
        elif self.position and bear:
            self.sell_signal(reason=f"空头({self.p.short},{self.p.mid},{self.p.long})")
        elif self.position and self.entry_price:
            pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
            if pct <= self.p.stop_loss:
                self.sell_signal(reason=f"止损({pct:.1f}%)")

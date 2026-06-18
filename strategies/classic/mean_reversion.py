"""均值回归策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class MeanReversionStrategy(BaseStrategy):
    params = (("period",20),("entry_z",2.0),("exit_z",0.5))
    def __init__(self):
        super().__init__()
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
        self.std = bt.indicators.StandardDeviation(self.data.close, period=self.p.period)
    def next(self):
        if self.std[0] == 0: return
        z = (self.data.close[0] - self.sma[0]) / self.std[0]
        if not self.position:
            if z <= -self.p.entry_z:
                self.buy_signal(reason=f"下偏{abs(z):.1f}sigma")
        else:
            if abs(z) <= self.p.exit_z:
                self.sell_signal(reason="回归平仓")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")

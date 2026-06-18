"""低波风格策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class LowVolStrategy(BaseStrategy):
    params = (("period",20),("vol_threshold",0.02))
    def __init__(self):
        super().__init__()
        self.std = bt.indicators.StandardDeviation(self.data.close, period=self.p.period)
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
    def next(self):
        vol = self.std[0] / self.sma[0] if self.sma[0] > 0 else 999
        if not self.position:
            if vol < self.p.vol_threshold:
                self.buy_signal(reason=f"低波{vol:.4f}")
        else:
            if vol > self.p.vol_threshold * 2:
                self.sell_signal(reason=f"波幅{vol:.4f}")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")

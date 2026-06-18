"""双均线金叉死叉策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class GoldenCrossStrategy(BaseStrategy):
    params = (("fast",5),("slow",20))
    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.ma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)
    def next(self):
        if self.crossover[0] == 1:
            self.buy_signal(reason=f"金叉({self.p.fast},{self.p.slow})")
        elif self.crossover[0] == -1:
            self.sell_signal(reason=f"死叉({self.p.fast},{self.p.slow})")
        if self.position and self.entry_price:
            pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
            if pct <= self.p.stop_loss:
                self.sell_signal(reason=f"止损({pct:.1f}%)")
            elif pct >= self.p.take_profit:
                self.sell_signal(reason=f"止盈({pct:.1f}%)")

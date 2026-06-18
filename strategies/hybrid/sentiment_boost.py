"""情绪增强策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class SentimentBoostStrategy(BaseStrategy):
    params = (("fast",5),("slow",20))
    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.ma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)
    def next(self):
        sent = self.data.sentiment[0] if hasattr(self.data,"sentiment") and self.data.sentiment[0] else 0
        boost = max(0.3, min(1.5, 1.0 + sent * 0.5))
        if self.crossover[0] == 1:
            self.buy_signal(size_ratio=boost, reason=f"金叉+情绪乘数{boost:.1f}")
        elif self.crossover[0] == -1:
            self.sell_signal(reason="死叉")
        if self.position and self.entry_price:
            pct = (self.data.close[0]-self.entry_price)/self.entry_price*100
            if pct <= self.p.stop_loss: self.sell_signal(reason=f"止损({pct:.1f}%)")

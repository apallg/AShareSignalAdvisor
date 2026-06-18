"""AI 评分过滤策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class AIFilteredStrategy(BaseStrategy):
    params = (("fast",5),("slow",20),("ai_threshold",6))
    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.ma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)
    def next(self):
        ai = self.data.ai_factor[0] if hasattr(self.data,"ai_factor") and self.data.ai_factor[0] else 0
        if self.crossover[0] == 1:
            if ai >= self.p.ai_threshold:
                self.buy_signal(reason=f"金叉+AI({ai:.1f})")
        elif self.crossover[0] == -1:
            self.sell_signal(reason="死叉")
        if self.position and self.entry_price:
            pct = (self.data.close[0]-self.entry_price)/self.entry_price*100
            if pct <= self.p.stop_loss: self.sell_signal(reason=f"止损({pct:.1f}%)")

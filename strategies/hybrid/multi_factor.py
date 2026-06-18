"""多因子综合策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class MultiFactorStrategy(BaseStrategy):
    params = (("tech_weight",0.4),("ai_weight",0.3),("sentiment_weight",0.3),("threshold",0.6))
    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.sma50 = bt.indicators.SMA(self.data.close, period=50)
    def next(self):
        score = 0.0
        if self.data.close[0] > self.sma50[0]:
            score += self.p.tech_weight * 0.5
        if hasattr(self.data,"ai_factor") and self.data.ai_factor[0]:
            score += self.p.ai_weight * (self.data.ai_factor[0]/10)
        if hasattr(self.data,"sentiment") and self.data.sentiment[0]:
            s = max(-1, min(1, self.data.sentiment[0]))
            score += self.p.sentiment_weight * ((s+1)/2)
        if not self.position and score >= self.p.threshold:
            self.buy_signal(reason=f"综合分{score:.2f}")
        elif self.position and score < self.p.threshold * 0.5:
            self.sell_signal(reason=f"综合分降至{score:.2f}")
        elif self.position and self.entry_price:
            pct = (self.data.close[0]-self.entry_price)/self.entry_price*100
            if pct <= self.p.stop_loss: self.sell_signal(reason=f"止损({pct:.1f}%)")

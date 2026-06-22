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


# ---- 实盘版本 ----
import numpy as np
from execution.live.base import LiveStrategy


class LiveMultiFactor(LiveStrategy):
    name = "多因子综合"
    description = "技术面+AI评分+情绪多因子加权评分，超阈值买入"
    params = {"tech_weight": 0.4, "ai_weight": 0.3, "sentiment_weight": 0.3, "threshold": 0.6, "stop_loss": -8}

    def check_signal(self, df):
        if len(df) < 52:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"]
        price = float(close.values[-1])
        sma50 = float(close.rolling(50).mean().values[-1])

        score = 0.0
        if price > sma50:
            score += self.tech_weight * 0.5

        if "ai_factor" in df.columns and not np.isnan(df["ai_factor"].values[-1]):
            score += self.ai_weight * (float(df["ai_factor"].values[-1]) / 10)

        if "sentiment" in df.columns and not np.isnan(df["sentiment"].values[-1]):
            s = max(-1, min(1, float(df["sentiment"].values[-1])))
            score += self.sentiment_weight * ((s + 1) / 2)

        if self.position == 0:
            if score >= self.threshold:
                return {"action": "buy", "size_ratio": 0.8, "reason": f"综合分{score:.2f}买入"}
        else:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl_pct:.1f}%)"}
            if score < self.threshold * 0.5:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"综合分降至{score:.2f}"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

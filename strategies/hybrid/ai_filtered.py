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


# ---- 实盘版本 ----
import numpy as np
from execution.live.base import LiveStrategy


class LiveAIFiltered(LiveStrategy):
    name = "AI过滤增强"
    description = "金叉信号经AI评分过滤后买入，死叉卖出"
    params = {"fast": 5, "slow": 20, "ai_threshold": 6, "stop_loss": -8}

    def check_signal(self, df):
        if len(df) < self.slow + 2:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"]
        price = float(close.values[-1])
        fast_ma = close.rolling(self.fast).mean().values
        slow_ma = close.rolling(self.slow).mean().values
        curr_fast, prev_fast = fast_ma[-1], fast_ma[-2]
        curr_slow, prev_slow = slow_ma[-1], slow_ma[-2]
        ai = float(df["ai_factor"].values[-1]) if "ai_factor" in df.columns and not np.isnan(df["ai_factor"].values[-1]) else 0

        if self.position == 0:
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                if ai >= self.ai_threshold:
                    return {"action": "buy", "size_ratio": 0.8, "reason": f"金叉+AI({ai:.1f})"}
        else:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl_pct:.1f}%)"}
            if prev_fast >= prev_slow and curr_fast < curr_slow:
                return {"action": "sell", "size_ratio": 1.0, "reason": "死叉卖出"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

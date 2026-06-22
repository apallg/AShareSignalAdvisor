"""海龟交易法则"""
import backtrader as bt
from strategies.base import BaseStrategy

class TurtleStrategy(BaseStrategy):
    params = (("entry_period",20),("exit_period",10),("atr_period",14),("atr_multiple",2))
    def __init__(self):
        super().__init__()
        self.entry_high = bt.indicators.Highest(self.data.high, period=self.p.entry_period)
        self.exit_low = bt.indicators.Lowest(self.data.low, period=self.p.exit_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
    def next(self):
        if not self.position:
            if self.data.close[0] >= self.entry_high[-1]:
                self.buy_signal(size_ratio=0.3, reason=f"突破{self.p.entry_period}日高")
        else:
            if self.data.close[0] <= self.exit_low[-1]:
                self.sell_signal(reason=f"跌破{self.p.exit_period}日低")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                atr_pct = self.atr[0] / self.data.close[0] * 100 if self.data.close[0] > 0 else 0
                if pct <= -2 * atr_pct:
                    self.sell_signal(reason=f"ATR止损({pct:.1f}%)")
                elif pct >= 2 * self.p.atr_multiple * atr_pct:
                    self.sell_signal(reason=f"止盈({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy
import pandas as pd


class LiveTurtle(LiveStrategy):
    name = "海龟交易法则"
    description = "突破N日高点买入，跌破N日低点或ATR止损卖出"
    params = {"entry_period": 20, "exit_period": 10, "atr_period": 14, "atr_multiple": 2}

    def check_signal(self, df):
        min_len = max(self.entry_period, self.exit_period, self.atr_period) + 2
        if len(df) < min_len:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        high = df["high"]
        low = df["low"]
        close = df["close"]
        price = float(close.values[-1])

        entry_high = float(high.rolling(self.entry_period).max().values[-2])
        exit_low = float(low.rolling(self.exit_period).min().values[-2])

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(self.atr_period).mean().values[-1])

        if self.position == 0:
            if price >= entry_high:
                return {"action": "buy", "size_ratio": 0.3, "reason": f"突破{self.entry_period}日高"}
        else:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            atr_pct = atr / price * 100
            if price <= exit_low:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"跌破{self.exit_period}日低"}
            if pnl_pct <= -2 * atr_pct:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"ATR止损({pnl_pct:.1f}%)"}
            if pnl_pct >= 2 * self.atr_multiple * atr_pct:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止盈({pnl_pct:.1f}%)"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

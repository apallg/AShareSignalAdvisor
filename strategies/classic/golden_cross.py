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


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveGoldenCross(LiveStrategy):
    name = "双均线金叉死叉"
    description = "短期均线上穿长期均线买入，下穿卖出"
    params = {"fast": 5, "slow": 20, "stop_loss": -8, "take_profit": 20}

    def check_signal(self, df):
        if len(df) < self.slow + 1:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"].values
        fast_ma = df["close"].rolling(self.fast).mean().values
        slow_ma = df["close"].rolling(self.slow).mean().values
        curr_fast, prev_fast = fast_ma[-1], fast_ma[-2]
        curr_slow, prev_slow = slow_ma[-1], slow_ma[-2]
        price = close[-1]
        if self.position == 0:
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                return {"action": "buy", "size_ratio": 1.0, "reason": f"金叉(MA{self.fast}↑MA{self.slow})"}
        else:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl_pct:.1f}%)"}
            if pnl_pct >= self.take_profit:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止盈({pnl_pct:.1f}%)"}
            if prev_fast >= prev_slow and curr_fast < curr_slow:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"死叉(MA{self.fast}↓MA{self.slow})"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

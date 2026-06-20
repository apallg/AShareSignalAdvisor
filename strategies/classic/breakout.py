"""趋势突破策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class BreakoutStrategy(BaseStrategy):
    params = (("period",20),)
    def __init__(self):
        super().__init__()
        self.high = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.low = bt.indicators.Lowest(self.data.low, period=self.p.period)
    def next(self):
        if not self.position:
            if self.data.close[0] > self.high[-1]:
                self.buy_signal(reason=f"突破{self.p.period}日高")
        else:
            if self.data.close[0] < self.low[-1]:
                self.sell_signal(reason=f"跌破{self.p.period}日低")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveBreakout(LiveStrategy):
    name = "趋势突破"
    description = "突破N日最高价买入，跌破N日最低价卖出"
    params = {"period": 20}

    def check_signal(self, df):
        if len(df) < self.period + 1:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"].values
        high = df["high"]
        low = df["low"]
        price = close[-1]
        n_day_high = high.rolling(self.period).max().shift(1).values[-1]
        n_day_low = low.rolling(self.period).min().shift(1).values[-1]
        if self.position == 0:
            if price > n_day_high:
                return {"action": "buy", "size_ratio": 1.0, "reason": f"突破{self.period}日高点买入"}
        else:
            if price < n_day_low:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"跌破{self.period}日低点卖出"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

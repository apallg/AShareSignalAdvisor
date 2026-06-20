"""均线多头排列策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class BullArrangementStrategy(BaseStrategy):
    params = (("short",5),("mid",20),("long",60))
    def __init__(self):
        super().__init__()
        self.s = bt.indicators.SMA(self.data.close, period=self.p.short)
        self.m = bt.indicators.SMA(self.data.close, period=self.p.mid)
        self.l = bt.indicators.SMA(self.data.close, period=self.p.long)
    def next(self):
        bull = self.s[0] > self.m[0] > self.l[0]
        bear = self.s[0] < self.m[0] < self.l[0]
        if not self.position and bull:
            self.buy_signal(reason=f"多头({self.p.short},{self.p.mid},{self.p.long})")
        elif self.position and bear:
            self.sell_signal(reason=f"空头({self.p.short},{self.p.mid},{self.p.long})")
        elif self.position and self.entry_price:
            pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
            if pct <= self.p.stop_loss:
                self.sell_signal(reason=f"止损({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveBullArrangement(LiveStrategy):
    name = "均线多头排列"
    description = "短中长三条均线多头排列时买入，空头或止损时卖出"
    params = {"short": 5, "mid": 20, "long": 60, "stop_loss": -10}

    def check_signal(self, df):
        min_len = self.long + 2
        if len(df) < min_len:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"]
        price = float(close.values[-1])
        s = float(close.rolling(self.short).mean().values[-1])
        m = float(close.rolling(self.mid).mean().values[-1])
        l = float(close.rolling(self.long).mean().values[-1])
        bull = s > m > l
        bear = s < m < l

        if self.position == 0:
            if bull:
                return {"action": "buy", "size_ratio": 0.8, "reason": f"多头排列(MA{self.short}>{self.mid}>{self.long})"}
        else:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl_pct:.1f}%)"}
            if bear:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"空头排列(MA{self.short}<{self.mid}<{self.long})"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

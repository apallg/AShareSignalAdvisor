"""布林带反转策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class BollingerStrategy(BaseStrategy):
    params = (("period",20),("std",2.0))
    def __init__(self):
        super().__init__()
        self.bb = bt.indicators.BollingerBands(self.data.close, period=self.p.period, devfactor=self.p.std)
    def next(self):
        if not self.position:
            if self.data.close[0] <= self.bb.lines.bot[0]:
                self.buy_signal(reason=f"下轨({self.p.period},{self.p.std})")
        else:
            if self.data.close[0] >= self.bb.lines.top[0]:
                self.sell_signal(reason=f"上轨({self.p.period},{self.p.std})")
            elif self.data.close[0] >= self.bb.lines.mid[0]:
                self.sell_signal(reason="回归中轨")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveBollinger(LiveStrategy):
    name = "布林带反转"
    description = "触及下轨买入，回归中轨或触及上轨卖出"
    params = {"period": 20, "std": 2.0}

    def check_signal(self, df):
        if len(df) < self.period + 1:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"]
        mid = close.rolling(self.period).mean()
        std = close.rolling(self.period).std()
        upper = mid + self.std * std
        lower = mid - self.std * std
        price = close.values[-1]
        if self.position == 0:
            if price <= lower.values[-1]:
                return {"action": "buy", "size_ratio": 1.0, "reason": "触及布林下轨买入"}
        else:
            if price >= upper.values[-1]:
                return {"action": "sell", "size_ratio": 1.0, "reason": "触及布林上轨卖出"}
            if price >= mid.values[-1]:
                prev_price = close.values[-2]
                if prev_price < mid.values[-2]:
                    return {"action": "sell", "size_ratio": 1.0, "reason": "回归布林中轨卖出"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

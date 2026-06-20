"""动量轮动策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    params = (("period",20),("lookback",63))
    def __init__(self):
        super().__init__()
        self.roc = bt.indicators.ROC(self.data.close, period=self.p.lookback)
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
    def next(self):
        roc = self.roc[0] or 0
        above = self.data.close[0] > self.sma[0]
        if not self.position:
            if roc > 0 and above:
                self.buy_signal(reason=f"动量{roc:.1f}%")
        else:
            if roc < -5 or not above:
                self.sell_signal(reason=f"动量弱{roc:.1f}%")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveMomentum(LiveStrategy):
    name = "动量轮动"
    description = "价格动能向上时买入，动能转弱卖出"
    params = {"momentum_days": 20, "ma_period": 60}

    def check_signal(self, df):
        min_len = max(self.momentum_days, self.ma_period) + 2
        if len(df) < min_len:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"].values
        price = close[-1]
        roc = (close[-1] / close[-self.momentum_days] - 1) * 100
        prev_roc = (close[-2] / close[-self.momentum_days - 1] - 1) * 100
        sma = df["close"].rolling(self.ma_period).mean().values[-1]
        if self.position == 0:
            if roc > 0 and price > sma:
                return {"action": "buy", "size_ratio": 0.8, "reason": f"动量转正({roc:.1f}%)买入"}
        else:
            if roc < 0 or price < sma:
                return {"action": "sell", "size_ratio": 1.0, "reason": "动量转弱卖出"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

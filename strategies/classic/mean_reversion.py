"""均值回归策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class MeanReversionStrategy(BaseStrategy):
    params = (("period",20),("entry_z",2.0),("exit_z",0.5))
    def __init__(self):
        super().__init__()
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
        self.std = bt.indicators.StandardDeviation(self.data.close, period=self.p.period)
    def next(self):
        if self.std[0] == 0: return
        z = (self.data.close[0] - self.sma[0]) / self.std[0]
        if not self.position:
            if z <= -self.p.entry_z:
                self.buy_signal(reason=f"下偏{abs(z):.1f}sigma")
        else:
            if abs(z) <= self.p.exit_z:
                self.sell_signal(reason="回归平仓")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveMeanReversion(LiveStrategy):
    name = "均值回归"
    description = "价格偏离均线过大时反向交易"
    params = {"period": 20, "entry_z": 2.0, "exit_z": 0.5}

    def check_signal(self, df):
        if len(df) < self.period + 1:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"]
        ma = close.rolling(self.period).mean()
        std = close.rolling(self.period).std()
        z_score = (close - ma) / std
        price = close.values[-1]
        curr_z = z_score.values[-1]
        if self.position == 0:
            if curr_z <= -self.entry_z:
                return {"action": "buy", "size_ratio": 1.0, "reason": f"Z分数{curr_z:.1f}超卖买入"}
        else:
            if abs(curr_z) <= self.exit_z:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"Z分数{curr_z:.1f}回归卖出"}
            pnl = (price - self.entry_price) / self.entry_price * 100
            if pnl <= -8:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl:.1f}%)"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

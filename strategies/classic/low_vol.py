"""低波风格策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class LowVolStrategy(BaseStrategy):
    params = (("period",20),("vol_threshold",0.02))
    def __init__(self):
        super().__init__()
        self.std = bt.indicators.StandardDeviation(self.data.close, period=self.p.period)
        self.sma = bt.indicators.SMA(self.data.close, period=self.p.period)
    def next(self):
        vol = self.std[0] / self.sma[0] if self.sma[0] > 0 else 999
        if not self.position:
            if vol < self.p.vol_threshold:
                self.buy_signal(reason=f"低波{vol:.4f}")
        else:
            if vol > self.p.vol_threshold * 2:
                self.sell_signal(reason=f"波幅{vol:.4f}")
            elif self.entry_price:
                pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
                if pct <= self.p.stop_loss:
                    self.sell_signal(reason=f"止损({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveLowVol(LiveStrategy):
    name = "低波风格"
    description = "波动率低时买入，波动率升高或止损时卖出"
    params = {"period": 20, "vol_threshold": 0.02, "stop_loss": -8}

    def check_signal(self, df):
        if len(df) < self.period + 2:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        close = df["close"]
        price = float(close.values[-1])
        rolling_std = close.rolling(self.period).std()
        rolling_sma = close.rolling(self.period).mean()
        vol = float(rolling_std.values[-1] / rolling_sma.values[-1]) if rolling_sma.values[-1] > 0 else 999

        if self.position == 0:
            if vol < self.vol_threshold:
                return {"action": "buy", "size_ratio": 0.8, "reason": f"低波{vol:.4f}"}
        else:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl_pct:.1f}%)"}
            if vol > self.vol_threshold * 2:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"波幅升高{vol:.4f}"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

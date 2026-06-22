"""价值选股策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class ValueStrategy(BaseStrategy):
    params = (("rebalance_days",20),)
    def __init__(self):
        super().__init__()
        self.day_count = 0
    def next(self):
        self.day_count += 1
        if not self.position and self.day_count % self.p.rebalance_days == 0:
            if hasattr(self.data,"pe") and self.data.pe[0] and self.data.pe[0] < 15:
                if hasattr(self.data,"roe") and self.data.roe[0] and self.data.roe[0] > 10:
                    self.buy_signal(reason=f"价值{self.data.pe[0]:.0f}/{self.data.roe[0]:.0f}")
        if self.position and self.entry_price:
            pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
            if pct <= self.p.stop_loss:
                self.sell_signal(reason=f"止损({pct:.1f}%)")


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy
import pandas as pd


class LiveValue(LiveStrategy):
    name = "价值选股"
    description = "定期调仓，低PE高ROE时买入"
    params = {"rebalance_days": 20, "stop_loss": -10, "take_profit": 30}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._day_count = 0

    def check_signal(self, df):
        self._day_count += 1
        if len(df) < 2:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        price = float(df["close"].values[-1])

        if self.position == 0 and self._day_count % self.rebalance_days == 0:
            pe = float(df["pe"].values[-1]) if "pe" in df.columns and pd.notna(df["pe"].values[-1]) else 999
            roe = float(df["roe"].values[-1]) if "roe" in df.columns and pd.notna(df["roe"].values[-1]) else 0
            if pe < 15 and roe > 10:
                return {"action": "buy", "size_ratio": 0.5, "reason": f"价值PE{pe:.0f}/ROE{roe:.0f}"}

        if self.position > 0 and self.entry_price > 0:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl_pct:.1f}%)"}
            if pnl_pct >= self.take_profit:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止盈({pnl_pct:.1f}%)"}
        return {"action": "hold", "size_ratio": 0, "reason": ""}

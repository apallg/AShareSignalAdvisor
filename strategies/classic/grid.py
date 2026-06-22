"""网格交易策略"""
import backtrader as bt
from strategies.base import BaseStrategy

class GridStrategy(BaseStrategy):
    params = (("grids",10),("spacing",2.0))
    def __init__(self):
        super().__init__()
        self.levels = []
        self.last_price = None
    def next(self):
        price = self.data.close[0]
        if not self.last_price:
            self.last_price = price
            gap = price * self.p.spacing / 100
            self.levels = []
            for i in range(-self.p.grids//2, self.p.grids//2+1):
                self.levels.append({"type":"buy" if i<0 else "sell","price":price+i*gap,"filled":False})
            return
        for lv in self.levels:
            if lv["type"]=="buy" and price<=lv["price"] and not lv["filled"]:
                self.buy_signal(size_ratio=0.8/self.p.grids, reason=f"网格{lv['price']:.2f}")
                lv["filled"] = True
            elif lv["type"]=="sell" and price>=lv["price"] and not lv["filled"]:
                if self.position:
                    self.sell_signal(reason=f"网格{lv['price']:.2f}")
                    lv["filled"] = True
        self.last_price = price


# ---- 实盘版本 ----
from execution.live.base import LiveStrategy


class LiveGrid(LiveStrategy):
    name = "网格交易"
    description = "价格波动自动在预设网格位置买卖"
    params = {"grids": 10, "spacing": 2.0, "stop_loss": -10, "take_profit": 15}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._levels = []
        self._base_price = None

    def check_signal(self, df):
        if len(df) < 2:
            return {"action": "hold", "size_ratio": 0, "reason": ""}
        price = float(df["close"].values[-1])

        if self._base_price is None:
            self._base_price = price
            gap = price * self.spacing / 100
            half = self.grids // 2
            for i in range(-half, half + 1):
                if i != 0:
                    lvl_price = price + i * gap
                    self._levels.append({"price": lvl_price, "type": "buy" if i < 0 else "sell", "filled": False})

        if self.position > 0 and self.entry_price > 0:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止损({pnl_pct:.1f}%)"}
            if pnl_pct >= self.take_profit:
                return {"action": "sell", "size_ratio": 1.0, "reason": f"止盈({pnl_pct:.1f}%)"}

        for lv in self._levels:
            if lv["type"] == "buy" and price <= lv["price"] and not lv["filled"]:
                lv["filled"] = True
                return {"action": "buy", "size_ratio": 0.8 / self.grids, "reason": f"网格买入{lv['price']:.2f}"}
            if lv["type"] == "sell" and price >= lv["price"] and not lv["filled"]:
                if self.position > 0:
                    lv["filled"] = True
                    return {"action": "sell", "size_ratio": 1.0, "reason": f"网格卖出{lv['price']:.2f}"}

        return {"action": "hold", "size_ratio": 0, "reason": ""}

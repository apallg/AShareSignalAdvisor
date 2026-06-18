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

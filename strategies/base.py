"""策略统一基类"""
import backtrader as bt


class BaseStrategy(bt.Strategy):
    """
    所有策略的统一基类
    封装 buy_signal / sell_signal / 仓位管理 / 止损止盈
    """
    
    params = (
        ('stop_loss', -8),
        ('take_profit', 20),
    )
    
    def __init__(self):
        self.trade_log = []
        self.equity_curve = []
        self.entry_price = None
        self.entry_date = None
        self.entry_size = 0
        
        if hasattr(self.data, 'close') and self.data.close:
            self.sma5 = bt.indicators.SMA(self.data.close, period=5)
            self.sma20 = bt.indicators.SMA(self.data.close, period=20)
    
    def next(self):
        raise NotImplementedError("子类必须实现 next 方法")
    
    def buy_signal(self, size_ratio=1.0, reason=""):
        if self.position:
            return
        cash = self.broker.getcash()
        price = self.data.close[0]
        size = int(cash * size_ratio / price) if price > 0 else 0
        if size <= 0:
            return
        self.buy(size=size)
        self.entry_price = price
        self.entry_date = self.data.datetime.date(0)
        self.entry_size = size
        self.trade_log.append({
            'date': str(self.data.datetime.date(0)),
            'action': 'buy',
            'price': round(price, 2),
            'shares': size,
            'reason': reason,
        })
    
    def sell_signal(self, reason=""):
        if not self.position:
            return
        price = self.data.close[0]
        pnl = (price - self.entry_price) * self.position.size if self.entry_price else 0
        self.close()
        self.trade_log.append({
            'date': str(self.data.datetime.date(0)),
            'action': 'sell',
            'price': round(price, 2),
            'shares': self.position.size,
            'pnl': round(pnl, 2),
            'reason': reason,
        })
        self.entry_price = None
    
    def notify_trade(self, trade):
        if trade.isclosed and self.trade_log:
            self.trade_log[-1]['pnl'] = round(trade.pnl, 2)
    
    def stop(self):
        value = round(self.broker.getvalue(), 2)
        try:
            d = str(self.data.datetime.date(0))
        except Exception:
            d = ""
        self.equity_curve.append({'date': d, 'value': value})

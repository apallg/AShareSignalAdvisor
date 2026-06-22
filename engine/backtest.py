"""Cerebro 封装——回测运行器"""
import backtrader as bt
from .data_feed import QuantDataFeed
from .analyzer import calculate_metrics


class BacktestEngine:
    """回测引擎封装"""
    
    def __init__(self, cash=1000000, commission=0.0003):
        self.cash = cash
        self.commission = commission
    
    def run(self, strategy_cls, params, data_feed, 
            strategy_id, stock_code, start_date, end_date):
        """执行回测"""
        cerebro = bt.Cerebro(stdstats=True)
        cerebro.adddata(data_feed)
        cerebro.addstrategy(strategy_cls, **params)
        cerebro.broker.setcash(self.cash)
        cerebro.broker.setcommission(commission=self.commission)
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        results = cerebro.run()
        strat = results[0]
        
        return calculate_metrics(
            strat, cerebro, strategy_id, stock_code, start_date, end_date
        )
    
    def get_value(self):
        return self.cash

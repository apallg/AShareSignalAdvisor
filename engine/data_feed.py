"""DataFetcher -> backtrader PandasData 适配器"""
import backtrader as bt

class QuantDataFeed(bt.feeds.PandasData):
    """
    量化数据源，包含技术指标、AI因子、情绪因子等额外列
    因子一次计算，所有策略复用
    """
    lines = (
        'ma5', 'ma10', 'ma20', 'ma60',
        'macd', 'macd_signal', 'macd_diff',
        'rsi',
        'kdj_k', 'kdj_d', 'kdj_j',
        'boll_upper', 'boll_mid', 'boll_lower',
        'ai_factor',
        'sentiment',
        'pe', 'pb', 'roe',
        'amount', 'turnover',
    )
    params = (
        ('datetime', None),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', None),
        ('ma5', 'ma5'),
        ('ma10', 'ma10'),
        ('ma20', 'ma20'),
        ('ma60', 'ma60'),
        ('macd', 'macd'),
        ('macd_signal', 'macd_signal'),
        ('macd_diff', 'macd_diff'),
        ('rsi', 'rsi'),
        ('kdj_k', 'kdj_k'),
        ('kdj_d', 'kdj_d'),
        ('kdj_j', 'kdj_j'),
        ('boll_upper', 'boll_upper'),
        ('boll_mid', 'boll_mid'),
        ('boll_lower', 'boll_lower'),
        ('ai_factor', 'ai_factor'),
        ('sentiment', 'sentiment'),
        ('pe', 'pe'),
        ('pb', 'pb'),
        ('roe', 'roe'),
        ('amount', 'amount'),
        ('turnover', 'turnover'),
    )

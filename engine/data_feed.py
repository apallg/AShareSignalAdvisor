"""DataFetcher -> backtrader PandasData 适配器"""
import pandas as pd
import backtrader as bt

class QuantDataFeed(bt.feeds.PandasData):
    """
    量化数据源，包含技术指标、AI因子、情绪因子等额外列
    缺失的可选列自动补 0，避免回测因列不完整而崩溃
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
        ('ma5', 'MA5'),
        ('ma10', 'MA10'),
        ('ma20', 'MA20'),
        ('ma60', 'MA60'),
        ('macd', 'MACD'),
        ('macd_signal', 'MACD_signal'),
        ('macd_diff', 'MACD_diff'),
        ('rsi', 'RSI14'),
        ('kdj_k', 'KDJ_K'),
        ('kdj_d', 'KDJ_D'),
        ('kdj_j', 'KDJ_J'),
        ('boll_upper', 'BB_upper'),
        ('boll_mid', 'BB_middle'),
        ('boll_lower', 'BB_lower'),
        ('ai_factor', 'ai_factor'),
        ('sentiment', 'sentiment'),
        ('pe', 'pe'),
        ('pb', 'pb'),
        ('roe', 'roe'),
        ('amount', 'amount'),
        ('turnover', 'turnover'),
    )

    def __init__(self, **kwargs):
        # 自动补全缺失的可选列，避免 backtrader 因列不存在而崩溃
        expected = {
            'MA5', 'MA10', 'MA20', 'MA60',
            'MACD', 'MACD_signal', 'MACD_diff',
            'RSI14', 'KDJ_K', 'KDJ_D', 'KDJ_J',
            'BB_upper', 'BB_middle', 'BB_lower',
            'ai_factor', 'sentiment',
            'pe', 'pb', 'roe',
            'amount', 'turnover',
        }
        df = kwargs.get('dataname')
        if df is not None and hasattr(df, 'columns'):
            for col in expected:
                if col not in df.columns:
                    df[col] = 0
        super().__init__(**kwargs)

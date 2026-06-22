import backtrader as bt
from strategies.base import BaseStrategy
from strategies.registry import register
import numpy as np
import pandas as pd


class SectorLeaderStrategy(BaseStrategy):
    """
    板块龙头追击策略
    当板块指数连续上涨达到指定天数时，全仓买入对应的龙头股票；
    当板块不再满足连续上涨条件时，卖出持仓。
    """
    params = (
        ('continuous_up_days', 1),       # 要求连续上涨的天数（>=1）
        ('min_pct_change', 0.0),         # 每日最小涨幅（百分比，如0.0表示上涨即可）
        ('sector_data_idx', 1),          # 板块数据在datas列表中的索引（0为主标的数据，1为板块数据）
    )

    def __init__(self):
        # 获取板块数据
        self.sector = self.datas[self.p.sector_data_idx]

        # 板块日涨幅（百分比）
        sector_pct = (self.sector.close / self.sector.close(-1) - 1.0) * 100.0

        # 判断每日涨幅是否超过最小要求，返回0或1
        is_up = sector_pct > self.p.min_pct_change

        # 求和得到最近N天满足条件的个数，当等于continuous_up_days时表示连续上涨
        self.up_streak = bt.ind.Sum(is_up, period=self.p.continuous_up_days)

    def next(self):
        if self.position:
            # 已持仓：如果板块不再连续上涨，则卖出
            if self.up_streak[0] < self.p.continuous_up_days:
                self.sell_signal(reason="板块不再满足连续上涨条件")
        else:
            # 空仓：如果板块连续上涨达到要求，则全仓买入
            if self.up_streak[0] >= self.p.continuous_up_days:
                self.buy_signal(size_ratio=1.0,
                                reason=f"板块连续上涨{self.p.continuous_up_days}天")


# ========== 实盘版本 ==========
class LiveSectorLeaderStrategy:
    """
    实盘版本：使用pandas/numpy实现相同逻辑
    """
    params = {
        'continuous_up_days': 1,
        'min_pct_change': 0.0,
    }

    def __init__(self):
        self.name = "LiveSectorLeaderStrategy"

    def check_signal(self, df: pd.DataFrame) -> dict:
        """
        df: 板块数据的DataFrame，必须包含'close'列，按时间正序排列
        返回: {"action": "buy"|"sell"|"hold", "size_ratio": 0~1.0, "reason": "..."}
        """
        # 数据不足时保持
        min_len = self.params['continuous_up_days'] + 1
        if df is None or len(df) < min_len:
            return {"action": "hold", "size_ratio": 0.0, "reason": "数据不足"}

        # 取最近 continuous_up_days + 1 个收盘价
        closes = df['close'].values[-min_len:]

        # 计算日涨跌幅
        pct_changes = np.diff(closes) / closes[:-1] * 100.0

        # 检查最近 continuous_up_days 天是否每日涨幅 > min_pct_change
        recent = pct_changes[-self.params['continuous_up_days']:]
        if len(recent) == self.params['continuous_up_days'] and np.all(recent > self.params['min_pct_change']):
            # 条件成立 -> 买入信号（外部将根据持仓状态决定是否执行）
            return {
                "action": "buy",
                "size_ratio": 1.0,
                "reason": f"板块连续上涨{self.params['continuous_up_days']}天"
            }
        else:
            # 条件不成立 -> 卖出信号（外部将根据持仓状态决定是否执行）
            return {
                "action": "sell",
                "size_ratio": 0.0,
                "reason": "板块不满足连续上涨条件"
            }


# 注册策略
register(SectorLeaderStrategy,
         name="板块龙头追击策略",
         desc="监测板块指数连续上涨时买入龙头股")

register(LiveSectorLeaderStrategy,
         name="Live板块龙头追击策略",
         desc="实盘版板块龙头追击(需外部提供板块数据)")
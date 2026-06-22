import numpy as np
import pandas as pd
from backtrader import indicator
from strategies.base import BaseStrategy
from execution.live.base import LiveStrategy


class SectorProbStrategy(BaseStrategy):
    """
    同板块其他股票上涨条件下目标股票上涨概率策略
    """
    params = (
        ('lookback', 20),            # 回看窗口长度（bar数）
        ('buy_prob', 0.7),           # 买入概率阈值
        ('sell_prob', 0.5),          # 卖出概率阈值
        ('check_interval', 30),      # 检查间隔（bar数，对应30分钟）
        ('others_gain_threshold', 0.5),  # 其他股票上涨占比阈值，用于定义“其他股票涨”
    )

    def __init__(self):
        # 目标股票为第一个数据，其他股票为后续数据
        self.target = self.datas[0]
        self.others = self.datas[1:]

        # 为每个股票计算是否上涨 (close > close(-1))
        self.target_up = self.target.close > self.target.close(-1)
        self.others_up = [d.close > d.close(-1) for d in self.others]

        # 用于记录每个bar的状态（避免重复计算）
        self.target_up_hist = []      # 目标上涨标志历史
        self.others_up_hist = []      # 其他股票上涨比例历史

        # 上次检查的bar索引
        self.last_check_idx = -1

    def next(self):
        # 当前bar索引
        cur_idx = len(self) - 1

        # 收集当前bar的上涨标志
        t_up = self.target_up[0]
        o_up_list = [up[0] for up in self.others_up]
        o_ratio = sum(o_up_list) / len(o_up_list) if len(o_up_list) > 0 else 1.0

        self.target_up_hist.append(t_up)
        self.others_up_hist.append(o_ratio)

        # 检查是否需要执行策略（每隔check_interval个bar）
        if (cur_idx - self.last_check_idx) < self.params.check_interval:
            return
        self.last_check_idx = cur_idx

        # 确保有足够的历史数据
        if cur_idx < self.params.lookback:
            return

        # 取最近lookback个bar的数据
        window_target = self.target_up_hist[-self.params.lookback:]
        window_others = self.others_up_hist[-self.params.lookback:]

        # 构建条件：其他股票上涨（占比超过阈值）
        cond_others = [r >= self.params.others_gain_threshold for r in window_others]

        # 筛选目标股票表现
        cond_others_arr = np.array(cond_others)
        target_arr = np.array(window_target)

        # 计算条件概率
        cond_true = cond_others_arr.sum()
        if cond_true == 0:
            prob = 0.0
        else:
            prob = (target_arr[cond_others_arr].sum()) / cond_true

        # 交易逻辑
        if prob > self.params.buy_prob:
            if self.position.size == 0:
                self.buy_signal(size_ratio=1.0, reason=f"条件概率{prob:.2f}>买入阈值{self.params.buy_prob}")
        elif prob < self.params.sell_prob:
            if self.position.size > 0:
                self.sell_signal(reason=f"条件概率{prob:.2f}<卖出阈值{self.params.sell_prob}")





class LiveSectorProbStrategy(LiveStrategy):
    """
    实盘版本：同板块条件概率策略
    """
    params = {
        'lookback': 20,
        'buy_prob': 0.7,
        'sell_prob': 0.5,
        'check_interval': 30,
        'others_gain_threshold': 0.5,
        'target_col': 'close',
        'sector_cols': []   # 其他股票close列名列表
    }

    def __init__(self, params=None):
        super().__init__(params)
        self.target_col = self.params['target_col']
        self.sector_cols = self.params['sector_cols']
        self.last_check_idx = -1
        # 用于缓存历史数据（避免每次全量计算）
        self._cache = {}

    def check_signal(self, df):
        # df应包含日期索引，以及target_col和sector_cols列
        cur_len = len(df)
        if self.last_check_idx < 0:
            self.last_check_idx = 0

        # 检查间隔
        if (cur_len - 1 - self.last_check_idx) < self.params['check_interval']:
            return {'action': 'hold', 'size_ratio': 0, 'reason': '未到检查时间'}
        self.last_check_idx = cur_len - 1

        # 需足够数据
        if cur_len < self.params['lookback'] + 1:
            return {'action': 'hold', 'size_ratio': 0, 'reason': '数据不足'}

        # 取最近lookback个bar
        lookback = self.params['lookback']
        recent = df.iloc[-lookback:]

        # 计算每个bar目标是否上涨
        target_returns = recent[self.target_col].pct_change().fillna(0)
        target_up = (target_returns > 0).values

        # 计算每个bar其他股票是否上涨（每个股票各自判断）
        others_up_list = []
        for col in self.sector_cols:
            ret = recent[col].pct_change().fillna(0)
            others_up_list.append((ret > 0).values)
        others_up_arr = np.array(others_up_list).T  # shape (lookback, n_stocks)
        # 其他股票上涨比例
        others_ratio = np.mean(others_up_arr, axis=1)

        # 条件：其他股票上涨比例 >= 阈值
        cond_others = others_ratio >= self.params['others_gain_threshold']

        total_cond = cond_others.sum()
        if total_cond == 0:
            prob = 0.0
        else:
            prob = np.sum(target_up[cond_others]) / total_cond

        # 判断买卖
        if prob > self.params['buy_prob']:
            return {
                'action': 'buy',
                'size_ratio': 1.0,
                'reason': f"条件概率{prob:.2f}>买入阈值{self.params['buy_prob']}"
            }
        elif prob < self.params['sell_prob']:
            return {
                'action': 'sell',
                'size_ratio': 1.0,
                'reason': f"条件概率{prob:.2f}<卖出阈值{self.params['sell_prob']}"
            }
        else:
            return {'action': 'hold', 'size_ratio': 0, 'reason': f"概率{prob:.2f}在阈值之间"}
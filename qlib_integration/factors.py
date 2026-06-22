"""
qlib 因子计算封装 — Alpha158, Alpha360, 自定义表达式
"""
import logging
import pandas as pd

from qlib_integration.config import init_qlib

logger = logging.getLogger(__name__)


class FactorComputer:
    def __init__(self):
        init_qlib()

    def get_alpha158(self, instruments="csi300", start_time=None, end_time=None):
        """返回 Alpha158 因子 DataFrame（158 列特征 + 1 列标签）"""
        from qlib.utils import init_instance_by_config
        from qlib.data.dataset import DatasetH

        handler_config = {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "instruments": instruments,
                "start_time": start_time,
                "end_time": end_time,
                "freq": "day",
                "fit_start_time": start_time,
                "fit_end_time": end_time,
            },
        }
        handler = init_instance_by_config(handler_config)
        dataset = DatasetH(handler=handler, segments={"all": (start_time, end_time)})
        return dataset.prepare("all")

    def get_alpha360(self, instruments="csi300", start_time=None, end_time=None):
        """返回 Alpha360 因子 DataFrame（360 列特征）"""
        from qlib.utils import init_instance_by_config
        from qlib.data.dataset import DatasetH

        handler_config = {
            "class": "Alpha360",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "instruments": instruments,
                "start_time": start_time,
                "end_time": end_time,
                "freq": "day",
                "fit_start_time": start_time,
                "fit_end_time": end_time,
            },
        }
        handler = init_instance_by_config(handler_config)
        dataset = DatasetH(handler=handler, segments={"all": (start_time, end_time)})
        return dataset.prepare("all")

    def compute_expressions(self, expressions, instruments="csi300", start_time=None, end_time=None):
        """计算自定义 qlib 表达式因子"""
        from qlib.utils import init_instance_by_config
        from qlib.data.dataset.loader import QlibDataLoader

        names = [f"factor_{i}" for i in range(len(expressions))]
        loader = QlibDataLoader(
            config={"feature": (expressions, names)},
            freq="day",
        )
        config = {
            "class": "DataHandlerLP",
            "module_path": "qlib.data.dataset.handler",
            "kwargs": {
                "instruments": instruments,
                "start_time": start_time,
                "end_time": end_time,
                "data_loader": loader,
            },
        }
        from qlib.data.dataset import DatasetH
        handler = init_instance_by_config(config)
        dataset = DatasetH(handler=handler, segments={"all": (start_time, end_time)})
        return dataset.prepare("all")

    def get_data_handler(self, instruments="csi300", start_time=None, end_time=None, handler_class="Alpha158"):
        """获取已初始化的 DataHandler，用于 DatasetH 灵活构造"""
        from qlib.utils import init_instance_by_config

        handler_config = {
            "class": handler_class,
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "instruments": instruments,
                "start_time": start_time,
                "end_time": end_time,
                "freq": "day",
                "fit_start_time": start_time,
                "fit_end_time": end_time,
            },
        }
        return init_instance_by_config(handler_config)


# 常用 qlib 表达式示例
BUILTIN_EXPRESSIONS = {
    "ret_1d": "Ref($close, -1) / $close - 1",
    "ret_5d": "Ref($close, -5) / $close - 1",
    "ret_20d": "Ref($close, -20) / $close - 1",
    "volatility_20d": "Std($close, 20) / Mean($close, 20)",
    "ma_deviation": "$close / Mean($close, 20) - 1",
    "volume_ratio": "$volume / Mean($volume, 20)",
    "price_momentum": "($close - Ref($close, 20)) / Ref($close, 20)",
    "high_low_ratio": "$high / $low - 1",
    "turnover": "$volume / Mean($volume, 5)",
    "rsi_like": "Mean(Gt($close, Ref($close, -1)), 14) * 100",
}

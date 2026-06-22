"""
实时数据源抽象基类
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseRealtimeSource(ABC):
    """实时行情数据源基类"""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取实时行情
        symbols: ["000001", "600519", ...]
        return: {"000001": {"price": 12.5, "pct_chg": 0.5, ...}, ...}
        """
        ...

    @abstractmethod
    def get_market_indices(self, index_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取指数行情"""
        ...

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """将 600519 转为 sh600519 / sz000001 格式"""
        if symbol.startswith(("sh", "sz", "SH", "SZ", "Sh", "Sz")):
            return symbol.lower()
        if symbol.startswith(("6", "5")):
            return f"sh{symbol}"
        elif symbol.startswith(("0", "3", "2")):
            return f"sz{symbol}"
        else:
            return symbol

    @staticmethod
    def clean_symbol(normalized: str) -> str:
        """将 sh600519 转回 600519"""
        return normalized.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")

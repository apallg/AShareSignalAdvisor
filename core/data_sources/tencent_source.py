"""
腾讯财经实时行情数据源 - qt.gtimg.cn，速度快，境外访问稳定
"""
from typing import List, Dict, Any, Optional
import requests
from core.data_sources.base import BaseRealtimeSource


class TencentSource(BaseRealtimeSource):
    """腾讯财经实时行情"""

    QUOTE_URL = "http://qt.gtimg.cn/q={symbols}"

    def name(self) -> str:
        return "腾讯财经 (实时)"

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}
        normalized = [self.normalize_symbol(s) for s in symbols]
        url = self.QUOTE_URL.format(symbols=",".join(normalized))
        try:
            resp = requests.get(url, timeout=5)
            resp.encoding = "gbk"
            return self._parse_response(resp.text)
        except Exception:
            return {}

    def get_market_indices(self, index_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        return self.get_quotes(index_codes)

    def _parse_response(self, text: str) -> Dict[str, Dict[str, Any]]:
        result = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if "~" not in line:
                continue
            try:
                fields = line.split("~")
                if len(fields) < 40:
                    continue
                symbol = self.clean_symbol(fields[2].strip())
                result[symbol] = {
                    "name": fields[1].strip(),
                    "open": self._f(fields[5]),
                    "prev_close": self._f(fields[4]),
                    "price": self._f(fields[3]),
                    "high": self._f(fields[33]),
                    "low": self._f(fields[34]),
                    "volume": self._f(fields[6]),
                    "amount": self._f(fields[37]),
                    "bid": self._f(fields[9]),
                    "ask": self._f(fields[10]),
                    "date": fields[30] if len(fields) > 30 else "",
                    "time": fields[31] if len(fields) > 31 else "",
                }
                price = result[symbol]["price"]
                prev = result[symbol]["prev_close"]
                if price and prev and prev != 0:
                    result[symbol]["pct_chg"] = round((price - prev) / prev * 100, 2)
                    result[symbol]["change"] = round(price - prev, 2)
                else:
                    result[symbol]["pct_chg"] = 0
                    result[symbol]["change"] = 0
            except Exception:
                continue
        return result

    @staticmethod
    def _f(val) -> Optional[float]:
        try:
            return float(val) if val else None
        except (ValueError, TypeError):
            return None

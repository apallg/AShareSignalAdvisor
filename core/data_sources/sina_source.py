"""
新浪财经实时行情数据源
毫秒级响应，同花顺等平台常用的实时行情接口
"""
from typing import List, Dict, Any, Optional
import requests
import re
from core.data_sources.base import BaseRealtimeSource


class SinaSource(BaseRealtimeSource):
    """新浪财经实时行情"""

    QUOTE_URL = "http://hq.sinajs.cn/list={symbols}"

    def name(self) -> str:
        return "新浪财经 (实时)"

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}
        normalized = [self.normalize_symbol(s) for s in symbols]
        url = self.QUOTE_URL.format(symbols=",".join(normalized))
        headers = {"Referer": "https://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=5, proxies={"http": None, "https": None})
        resp.encoding = "gbk"
        return self._parse_response(resp.text)

    def get_market_indices(self, index_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        return self.get_quotes(index_codes)

    def _parse_response(self, text: str) -> Dict[str, Dict[str, Any]]:
        result = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or "hq_str_" not in line:
                continue
            match = re.search(r'hq_str_(\w+)="', line)
            if not match:
                continue
            raw_symbol = match.group(1)
            symbol = self.clean_symbol(raw_symbol)
            data_match = re.search(r'"(.+)"', line)
            if not data_match:
                continue
            fields = data_match.group(1).split(",")
            if len(fields) < 32:
                continue
            result[symbol] = {
                "name": fields[0],
                "open": self._f(fields[1]),
                "prev_close": self._f(fields[2]),
                "price": self._f(fields[3]),
                "high": self._f(fields[4]),
                "low": self._f(fields[5]),
                "bid": self._f(fields[6]),
                "ask": self._f(fields[7]),
                "volume": float(fields[8]) if fields[8] else 0,
                "amount": float(fields[9]) if fields[9] else 0,
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
        return result

    @staticmethod
    def _f(val) -> Optional[float]:
        try:
            return float(val) if val else None
        except (ValueError, TypeError):
            return None

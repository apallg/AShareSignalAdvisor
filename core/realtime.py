"""
实时行情引擎 - 集成所有数据源，提供统一实时接口
"""
from typing import Dict, Any, List, Optional, Callable
from core.data_sources import get_source, get_active_source
from utils.cache_manager import CacheManager
import config


class RealtimeEngine:
    """实时行情引擎"""

    def __init__(self, cache: Optional[CacheManager] = None):
        self.cache = cache or CacheManager()

    @property
    def source_name(self) -> str:
        return get_active_source()

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        source = get_source(self.source_name)
        return source.get_quotes(symbols)

    def get_realtime_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        result = self.get_quotes([symbol])
        return result.get(symbol)

    def get_indices(self) -> Dict[str, Dict[str, Any]]:
        index_codes = ["sh000001", "sz399001", "sz399006", "sh000688"]
        return self.get_quotes(index_codes)

    def get_sina_sectors(self) -> Dict[str, float]:
        """获取新浪板块涨跌排行（通过新浪板块接口）"""
        import requests
        import re
        cache_key = "sina_sectors"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        try:
            url = "http://vip.stock.finance.sina.com.cn/q/go.php/vIndustryRank/kind/sshy/p/1/num/50/sort/changepercent/"
            resp = requests.get(url, timeout=10)
            resp.encoding = "gbk"
            result = {}
            pattern = re.findall(r'<a[^>]*>(\w+)</a>.*?<td[^>]*>(-?\d+\.\d+)%</td>', resp.text, re.DOTALL)
            for name, pct in pattern[:20]:
                try:
                    result[name] = float(pct)
                except ValueError:
                    pass
            self.cache.set(cache_key, result, expire=300)
            return result
        except Exception:
            return {}

    # ─── 涨跌榜 ──────────────────────────────

    def get_top_gainers(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取涨幅榜 TOP N（使用新浪排名API）"""
        return self._fetch_ranking(sort="changepercent", asc=0, num=top_n)

    def get_top_losers(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取跌幅榜 TOP N（使用新浪排名API）"""
        return self._fetch_ranking(sort="changepercent", asc=1, num=top_n)

    def get_volume_ranking(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取成交量排行"""
        return self._fetch_ranking(sort="volume", asc=0, num=top_n)

    def _fetch_ranking(self, sort: str = "changepercent", asc: int = 0, num: int = 20) -> List[Dict[str, Any]]:
        """从新浪财经获取排行数据"""
        import requests, json
        cache_key = f"ranking:{sort}:{asc}:{num}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
            params = {
                "page": 1, "num": num,
                "sort": sort, "asc": str(asc),
                "node": "hs_a", "_s_r_a": "init",
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.encoding = "gbk"
            data = json.loads(resp.text)
            result = []
            for item in data:
                result.append({
                    "code": item.get("code", ""),
                    "name": item.get("name", ""),
                    "price": float(item.get("trade", 0)),
                    "pct_chg": float(item.get("changepercent", 0)),
                    "change": float(item.get("pricechange", 0)),
                    "volume": float(item.get("volume", 0)),
                    "amount": float(item.get("amount", 0)),
                    "turnover": float(item.get("turnoverratio", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "open": float(item.get("open", 0)),
                })
            self.cache.set(cache_key, result, expire=120)
            return result
        except Exception:
            return self._fallback_ranking(sort, asc, num)

    def _fallback_ranking(self, sort: str = "changepercent", asc: int = 0, num: int = 20) -> List[Dict[str, Any]]:
        """备用方案：通过 akshare 获取涨跌榜"""
        try:
            from core.data_fetcher import DataFetcher
            fetcher = DataFetcher()
            if asc == 0 and sort == "changepercent":
                df = fetcher.get_top_gainers(num)
            elif asc == 1 and sort == "changepercent":
                df = fetcher.get_top_losers(num)
            else:
                return []
            if df is None or df.empty:
                return []
            result = []
            for _, row in df.iterrows():
                result.append({
                    "code": row.get("代码", ""),
                    "name": row.get("名称", ""),
                    "price": float(row.get("最新价", 0)),
                    "pct_chg": float(row.get("涨跌幅", 0)),
                })
            return result
        except Exception:
            return []

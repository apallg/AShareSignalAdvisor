"""
板块选股器 - 按行业板块筛选股票，按成交量排序
"""
import logging
from typing import Optional
import pandas as pd
import akshare as ak
from core.data_fetcher import _retry
from utils.cache_manager import CacheManager
import config

logger = logging.getLogger(__name__)

_SIGNAL_THRESHOLD = 3       # 支撑/压力距离阈值（%）
_STRONG_SIGNAL_THRESHOLD = 2  # 强信号阈值（%）


class SectorScanner:
    """板块扫描器"""

    def __init__(self, cache: Optional[CacheManager] = None):
        self.cache = cache or CacheManager()

    def get_all_sectors(self) -> pd.DataFrame:
        """获取所有行业板块列表"""
        cache_key = "sectors_list_v2"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        # 优先同花顺 (不走东财域名，不受代理影响)
        try:
            df = _retry(lambda: ak.stock_board_industry_name_ths(), ma=2, dl=3)
            if df is not None and not df.empty:
                col = "name" if "name" in df.columns else df.columns[0]
                df = df.rename(columns={col: "板块名称"})
                self.cache.set(cache_key, df, expire=86400)
                return df
        except Exception:
            pass
        # 备选：东财
        try:
            df = _retry(lambda: ak.stock_board_industry_name_em(), ma=3, dl=3)
            self.cache.set(cache_key, df, expire=86400)
            return df
        except Exception:
            pass
        # 最后备选：硬编码常见板块
        common = ["电力行业", "半导体", "白酒", "医药生物", "汽车整车",
                  "银行", "证券", "房地产", "国防军工", "计算机应用",
                  "通信设备", "新能源汽车", "光伏设备", "医疗器械",
                  "食品饮料", "煤炭开采", "有色金属", "建筑装饰",
                  "石油石化", "机械设备", "基础化工", "传媒",
                  "电子", "家电", "纺织服装", "商贸零售",
                  "交通运输", "农林牧渔", "环保", "综合"]
        fallback = pd.DataFrame({"板块名称": common})
        self.cache.set(cache_key, fallback, expire=300)
        return fallback

    def get_sector_stocks(self, sector_name: str) -> pd.DataFrame:
        """获取某个行业板块的所有成分股，按成交量降序排列"""
        cache_key = f"sector_stocks_v4:{sector_name}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        df = None
        # 1. 尝试东财行业成分股
        try:
            df = _retry(
                lambda: ak.stock_board_industry_cons_em(symbol=sector_name),
                ma=2, dl=2,
            )
        except Exception:
            pass

        # 2. 东财失败 → miniQMT 板块匹配
        if df is None or df.empty:
            try:
                from xtquant import xtdata
                all_sectors = xtdata.get_sector_list()
                # 匹配：先找 SW2 行业板块中名称包含关键词的
                matches = [s for s in all_sectors
                          if s.startswith("SW2") and sector_name in s and "加权" not in s]
                if not matches:
                    # 模糊匹配：尝试去掉最后一个字
                    short = sector_name[:-1] if len(sector_name) > 1 else sector_name
                    matches = [s for s in all_sectors
                              if s.startswith("SW2") and short in s and "加权" not in s]
                if matches:
                    sector_key = matches[0]
                    codes = xtdata.get_stock_list_in_sector(sector_key)
                    if codes:
                        clean_codes = [c.split(".")[0] for c in codes]
                        df = pd.DataFrame({
                            "代码": clean_codes,
                            "名称": [""] * len(clean_codes),
                            "最新价": [0.0] * len(clean_codes),
                            "涨跌幅": [0.0] * len(clean_codes),
                            "成交量": [0] * len(clean_codes),
                        })
                        # 通过 get_instrument_detail 获取名称和昨收价
                        try:
                            names = []
                            prices = []
                            for c in codes:
                                try:
                                    detail = xtdata.get_instrument_detail(c)
                                    if detail:
                                        names.append(str(detail.get("InstrumentName", "")))
                                        prices.append(float(detail.get("PreClose", 0)))
                                    else:
                                        names.append("")
                                        prices.append(0.0)
                                except Exception:
                                    names.append("")
                                    prices.append(0.0)
                            df["名称"] = names
                            df["最新价"] = prices
                        except Exception:
                            pass
                        logger.info(f"miniQMT 板块匹配: {sector_name} → {sector_key} ({len(df)}只)")
            except Exception as e:
                logger.debug(f"miniQMT 板块匹配失败: {e}")

        if df is None or df.empty:
            return pd.DataFrame()

        # 统一列名
        col_map = {
            "代码": "code", "名称": "name", "最新价": "price",
            "涨跌幅": "pct_chg", "涨跌额": "change", "成交量": "volume",
            "成交额": "amount", "换手率": "turnover",
            "市盈率-动态": "pe", "市净率": "pb",
            "振幅": "amplitude", "最高": "high", "最低": "low",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # 按成交量降序排序
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
            df = df.sort_values("volume", ascending=False).reset_index(drop=True)

        # 添加排名
        df = df.reset_index(drop=True)
        df.index = df.index + 1
        df.index.name = "rank"
        df = df.reset_index()

        self.cache.set(cache_key, df, expire=300)  # 5分钟缓存
        return df

    def scan_support_resistance(self, sector_name: str, max_stocks: int = 80) -> list:
        """批量扫描板块成分股的支撑位/压力位，返回接近关键位置的股票"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from core.data_fetcher import DataFetcher
        from core.analyzer import Analyzer

        stocks_df = self.get_sector_stocks(sector_name)
        if stocks_df is None or stocks_df.empty:
            return []

        code_col = "code" if "code" in stocks_df.columns else "代码"
        name_col = "name" if "name" in stocks_df.columns else "名称"
        codes = stocks_df[code_col].head(max_stocks).tolist()

        def _analyze_one(code):
            try:
                fetcher = DataFetcher()
                df = fetcher.get_stock_daily(code)
                if df is None or df.empty or len(df) < 20:
                    return None
                df = Analyzer.add_indicators(df)
                latest = df.iloc[-1]
                recent = df.tail(20)

                price = float(latest["close"])
                if price <= 0:
                    return None

                bb_lower = float(latest.get("BB_lower", 0))
                bb_upper = float(latest.get("BB_upper", 0))
                ma20 = float(latest.get("MA20", 0))
                ma60 = float(latest.get("MA60", 0))
                low20 = float(recent["low"].min())
                high20 = float(recent["high"].max())

                # 支撑位列表 (只取低于当前价的)
                supports = []
                if bb_lower > 0 and bb_lower < price:
                    supports.append(("布林下轨", bb_lower))
                if ma60 > 0 and ma60 < price:
                    supports.append(("MA60均线", ma60))
                if low20 < price:
                    supports.append(("20日最低", low20))
                if ma20 > 0 and ma20 < price:
                    supports.append(("MA20均线", ma20))

                # 压力位列表 (只取高于当前价的)
                resistances = []
                if bb_upper > 0 and bb_upper > price:
                    resistances.append(("布林上轨", bb_upper))
                if ma20 > 0 and ma20 > price:
                    resistances.append(("MA20均线", ma20))
                if high20 > price:
                    resistances.append(("20日最高", high20))
                if ma60 > 0 and ma60 > price:
                    resistances.append(("MA60均线", ma60))

                nearest_support = min(supports, key=lambda x: price - x[1]) if supports else None
                nearest_resistance = min(resistances, key=lambda x: x[1] - price) if resistances else None

                dist_support = round((price - nearest_support[1]) / price * 100, 2) if nearest_support else None
                dist_resistance = round((nearest_resistance[1] - price) / price * 100, 2) if nearest_resistance else None

                # 信号判定
                signal = ""
                signal_type = ""
                if dist_support is not None and dist_support <= _SIGNAL_THRESHOLD:
                    if nearest_support[0] == "布林下轨" and dist_support <= _STRONG_SIGNAL_THRESHOLD:
                        signal = "强支撑买入"
                        signal_type = "strong_buy"
                    else:
                        signal = "接近支撑"
                        signal_type = "near_support"
                elif dist_resistance is not None and dist_resistance <= _SIGNAL_THRESHOLD:
                    if nearest_resistance[0] == "布林上轨" and dist_resistance <= _STRONG_SIGNAL_THRESHOLD:
                        signal = "强压力卖出"
                        signal_type = "strong_sell"
                    else:
                        signal = "接近压力"
                        signal_type = "near_resistance"

                return {
                    "code": str(code),
                    "name": "",
                    "price": round(price, 2),
                    "support_name": nearest_support[0] if nearest_support else "",
                    "support_price": round(nearest_support[1], 2) if nearest_support else 0,
                    "dist_support": dist_support if dist_support is not None else 999,
                    "resistance_name": nearest_resistance[0] if nearest_resistance else "",
                    "resistance_price": round(nearest_resistance[1], 2) if nearest_resistance else 0,
                    "dist_resistance": dist_resistance if dist_resistance is not None else 999,
                    "signal": signal,
                    "signal_type": signal_type,
                    "pct_chg": float(latest.get("pct_chg", 0)),
                }
            except Exception:
                return None

        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_analyze_one, c): c for c in codes}
            for fut in as_completed(futures):
                r = fut.result()
                if r:
                    # 补股票名称
                    name_row = stocks_df[stocks_df[code_col] == r["code"]]
                    if not name_row.empty:
                        r["name"] = str(name_row.iloc[0].get(name_col, ""))
                    results.append(r)

        # 排序：有信号的优先，离支撑/压力越近越靠前
        signal_priority = {"strong_buy": 0, "near_support": 1, "strong_sell": 2, "near_resistance": 3, "": 4}
        results.sort(key=lambda x: (
            signal_priority.get(x["signal_type"], 4),
            min(x["dist_support"], x["dist_resistance"])
        ))
        return results

    @staticmethod
    def format_sector_context(sector_name: str, df: pd.DataFrame, top_n: int = 10) -> str:
        """生成供 LLM 分析的板块上下文"""
        top = df.head(top_n)
        lines = [
            f"板块名称: {sector_name}",
            f"成分股总数: {len(df)}",
            "",
            f"=== 成交量前 {top_n} 的个股 ===",
            "",
        ]
        for _, row in top.iterrows():
            lines.append(
                f"{row.get('rank', '?')}. {row.get('name', '')}({row.get('code', '')}) "
                f"最新价:{row.get('price', 'N/A')} "
                f"涨跌:{row.get('pct_chg', 'N/A')}% "
                f"成交量:{row.get('volume', 'N/A')} "
                f"换手率:{row.get('turnover', 'N/A')}%"
            )

        return "\n".join(lines)

    @staticmethod
    def format_sector_summary(sector_name: str, df: pd.DataFrame) -> str:
        """生成板块统计摘要"""
        total = len(df)
        up_count = len(df[df.get("pct_chg", 0).astype(float) > 0]) if "pct_chg" in df.columns else 0
        down_count = total - up_count
        avg_pct = df["pct_chg"].astype(float).mean() if "pct_chg" in df.columns else 0
        total_vol = df["volume"].sum() if "volume" in df.columns else 0

        return (
            f"【{sector_name}】{total}只成分股，"
            f"上涨{up_count}只，下跌{down_count}只，"
            f"平均涨跌幅{avg_pct:.2f}%，"
            f"板块总成交量{total_vol:.0f}万手"
        )

"""
板块选股器 - 按行业板块筛选股票，按成交量排序
"""
from typing import Optional
import pandas as pd
import akshare as ak
from core.data_fetcher import _retry
from utils.cache_manager import CacheManager
import config


class SectorScanner:
    """板块扫描器"""

    def __init__(self, cache: Optional[CacheManager] = None):
        self.cache = cache or CacheManager()

    def get_all_sectors(self) -> pd.DataFrame:
        """获取所有行业板块列表"""
        cache_key = "sectors_list"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            df = _retry(lambda: ak.stock_board_industry_name_em(), ma=3, dl=3)
            self.cache.set(cache_key, df, expire=86400)  # 缓存 24 小时
            return df
        except Exception:
            # 备选：返回常见板块列表
            common = ["电力行业", "半导体", "白酒", "医药生物", "汽车整车",
                      "银行", "证券", "房地产", "国防军工", "计算机应用",
                      "通信设备", "新能源汽车", "光伏设备", "医疗器械",
                      "食品饮料", "煤炭开采", "有色金属", "建筑装饰",
                      "石油石化", "机械设备", "基础化工", "传媒",
                      "电子", "家电", "纺织服装", "商贸零售",
                      "交通运输", "农林牧渔", "环保", "综合"]
            import pandas as pd
            fallback = pd.DataFrame({"板块名称": common})
            self.cache.set(cache_key, fallback, expire=300)  # 备选缓存 5 分钟
            return fallback

    def get_sector_stocks(self, sector_name: str) -> pd.DataFrame:
        """获取某个行业板块的所有成分股，按成交量降序排列"""
        cache_key = f"sector_stocks:{sector_name}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        df = _retry(
            lambda: ak.stock_board_industry_cons_em(symbol=sector_name),
            ma=3, dl=3,
        )
        if df.empty:
            return df

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

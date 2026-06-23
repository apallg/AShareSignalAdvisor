"""
板块热力图模块

按行业聚合分析全市场股票的密集区状态，
生成板块级别的支撑/压力分布热力图数据。
"""
import logging
from typing import Dict, List, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

import config
from core.data_fetcher import DataFetcher
from core.density_analyzer import find_dense_zones, classify_zones, calc_risk_reward

logger = logging.getLogger(__name__)


def scan_sector_heatmap(
    stock_count: int = 200,
    window: int = 40,
    n_zones: int = 3,
    price_threshold: float = 2.0,
) -> List[Dict]:
    """
    扫描板块热力图数据

    对每个行业，统计：
    - 处于支撑区附近的股票占比
    - 处于压力区附近的股票占比
    - 盈亏比中位数
    - 平均密集区强度
    - 多空状态判定

    参数:
        stock_count:     扫描股票数量
        window:          分析窗口(交易日)
        n_zones:         密集区数量
        price_threshold: 接近区域的距离阈值（%）

    返回:
        按行业聚合的数据列表
    """
    # 获取板块列表和股票→行业映射
    try:
        from core.stock_scanner import SectorScanner
        scanner = SectorScanner()
        sectors_df = scanner.get_all_sectors()
        sector_names = sectors_df.iloc[:, 0].tolist() if sectors_df is not None else []
    except Exception:
        sector_names = []

    if not sector_names:
        return []

    code_to_industry: Dict[str, str] = {}
    for sector_name in sector_names[:30]:
        try:
            stocks_df = scanner.get_sector_stocks(sector_name)
            if stocks_df is None or stocks_df.empty:
                continue
            code_col = "code" if "code" in stocks_df.columns else "代码"
            for code in stocks_df[code_col].head(30).tolist():
                if code not in code_to_industry:
                    code_to_industry[str(code)] = sector_name
        except Exception:
            pass

    codes = list(code_to_industry.keys())[:stock_count]
    if not codes:
        return []

    # 初始化行业统计（线程安全：每个worker返回独立结果，主线程聚合）
    industry_data = defaultdict(lambda: {
        "total": 0, "near_support": 0, "near_resistance": 0,
        "rr_list": [], "avg_strength": [], "scanned": 0,
    })

    def _analyze_one(code):
        try:
            fetcher = DataFetcher()
            df = fetcher.get_stock_daily(code)
            if df is None or df.empty or len(df) < window + 5:
                return None

            ind = code_to_industry.get(code, "其他")
            current_price = float(df["close"].iloc[-1])
            zones = find_dense_zones(df, window=window, n_zones=n_zones)
            classify_zones(zones, current_price)

            supports = [z for z in zones if z.zone_type == "support"]
            resistances = [z for z in zones if z.zone_type == "resistance"]

            min_support_dist = min((abs(z.distance_pct) for z in supports), default=99)
            min_resistance_dist = min((abs(z.distance_pct) for z in resistances), default=99)
            near_support = min_support_dist <= price_threshold
            near_resistance = min_resistance_dist <= price_threshold

            rr = 0
            if supports and resistances:
                nearest_s = min(supports, key=lambda z: abs(z.distance_pct))
                nearest_r = min(resistances, key=lambda z: abs(z.distance_pct))
                rr = abs(nearest_r.distance_pct) / max(abs(nearest_s.distance_pct), 0.1)

            avg_strength = np.mean([z.strength for z in zones]) if zones else 0

            return {
                "industry": ind,
                "near_support": near_support,
                "near_resistance": near_resistance,
                "rr": rr,
                "avg_strength": avg_strength,
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_analyze_one, c): c for c in codes}
        for fut in as_completed(futures):
            r = fut.result()
            if r is None:
                continue
            ind = r["industry"]
            industry_data[ind]["total"] += 1
            industry_data[ind]["scanned"] += 1
            if r["near_support"]:
                industry_data[ind]["near_support"] += 1
            if r["near_resistance"]:
                industry_data[ind]["near_resistance"] += 1
            industry_data[ind]["rr_list"].append(r["rr"])
            industry_data[ind]["avg_strength"].append(r["avg_strength"])

    # 汇总
    result = []
    for ind, d in sorted(industry_data.items()):
        scanned = d["scanned"]
        if scanned == 0:
            continue

        support_pct = round(d["near_support"] / scanned * 100, 1)
        resistance_pct = round(d["near_resistance"] / scanned * 100, 1)
        neutral_pct = round(100 - support_pct - resistance_pct, 1)
        avg_rr = round(np.mean(d["rr_list"]), 2) if d["rr_list"] else 0
        avg_strength = round(np.mean(d["avg_strength"]), 2) if d["avg_strength"] else 0

        if support_pct > resistance_pct + 10:
            status = "偏多"
        elif resistance_pct > support_pct + 10:
            status = "偏空"
        else:
            status = "均衡"

        result.append({
            "industry": ind,
            "scanned": scanned,
            "support_pct": support_pct,
            "resistance_pct": resistance_pct,
            "neutral_pct": neutral_pct,
            "avg_rr": avg_rr,
            "avg_strength": avg_strength,
            "status": status,
        })

    return result

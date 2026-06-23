"""
从多数据源采集沪深300日线数据，写入 MySQL daily_quotes
优先 BaoStock（完整历史），次选 Tencent IFZQ（快），再次 akshare
用法: python scripts/collect_daily_data.py [--pool csi300|csi500|all] [--start YYYYMMDD] [--end YYYYMMDD]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import time
import random
import pandas as pd
import logging
logging.basicConfig(level=logging.WARNING)

from core.database import DailyQuotesRepo


def fetch_baostock(symbol, start_date, end_date):
    """通过 BaoStock 获取日K线 —— 完整历史数据"""
    import baostock as bs

    if symbol.startswith(("6", "5")):
        bs_code = f"sh.{symbol}"
    else:
        bs_code = f"sz.{symbol}"

    # BaoStock 需要 YYYY-MM-DD 格式
    _sd = start_date if "-" in start_date else f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
    _ed = end_date if "-" in end_date else f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"

    bs.login()
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=_sd, end_date=_ed,
            frequency="d", adjustflag="2",
        )
        if rs is None or rs.error_code != "0":
            return None

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return None

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
        return df
    finally:
        bs.logout()


def fetch_tencent(symbol, start_date, end_date):
    """通过 Tencent IFZQ HTTP 获取日线（快，但仅~640天历史）"""
    import requests

    mkt = "sh" if symbol.startswith(("6", "5")) else "sz"
    url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={mkt}{symbol},day,,,640,qfq"

    resp = requests.get(url, timeout=10, proxies={"http": None, "https": None})
    data = resp.json()
    if data.get("code") != 0:
        return None

    code_key = f"{mkt}{symbol}"
    day_data = data.get("data", {}).get(code_key, {})
    klines = day_data.get("qfqday") or day_data.get("day")
    if not klines:
        return None

    # Tencent 一次返回全部 ~640 天数据，全部保存
    rows = []
    for k in klines:
        try:
            d_str = str(k[0]).replace("-", "")  # "2026-06-22" → "20260622"
            rows.append({
                "date": d_str, "open": float(k[1]), "close": float(k[2]),
                "high": float(k[3]), "low": float(k[4]), "volume": float(k[5]),
            })
        except (IndexError, ValueError):
            continue
    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df["amount"] = df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
    return df


def get_index_stocks(symbol, name):
    for attempt in range(3):
        try:
            import akshare as ak
            df = ak.index_stock_cons(symbol=symbol)
            if "品种代码" in df.columns:
                codes = df["品种代码"].tolist()
            elif "code" in df.columns:
                codes = df["code"].tolist()
            else:
                codes = df.iloc[:, 0].tolist()
            print(f"  {name}: {len(codes)} 只")
            return codes
        except Exception as e:
            print(f"  {name} 第{attempt+1}次失败: {type(e).__name__}")
            time.sleep(3)
    return []


def collect_stocks(codes, start_date, end_date):
    success = 0
    fail = 0
    total = len(codes)

    for i, code in enumerate(codes):
        ok = False
        df = None

        # 1. 先试 Tencent（快、最新、无需注册）
        try:
            df = fetch_tencent(code, start_date, end_date)
            if df is not None and not df.empty:
                src = "Tencent"
                ok = True
        except Exception:
            pass

        # 2. 再试 BaoStock（完整历史，需要注册）
        if not ok:
            try:
                df = fetch_baostock(code, start_date, end_date)
                if df is not None and not df.empty:
                    src = "BaoStock"
                    ok = True
            except Exception:
                pass

        if ok and df is not None and not df.empty:
            try:
                DailyQuotesRepo.save_batch(code, df)
                if (i + 1) % 20 == 0:
                    print(f"  [{i+1}/{total}] {code} -> {len(df)} 条 ({src})")
                success += 1
                ok = True  # already True
            except Exception as e:
                print(f"  [{i+1}/{total}] {code} 保存失败: {type(e).__name__}")
                fail += 1
        else:
            print(f"  [{i+1}/{total}] {code} 无数据")
            fail += 1

        time.sleep(0.1)

    print(f"\n完成: 成功 {success}, 失败 {fail}")
    return success, fail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="csi300", choices=["csi300", "csi500", "all"])
    parser.add_argument("--start", default="20150101")
    parser.add_argument("--end", default="20250622")
    args = parser.parse_args()

    print(f"=== 获取成分股 ===")
    codes = []
    if args.pool in ("csi300", "all"):
        codes.extend(get_index_stocks("000300", "沪深300"))
    if args.pool in ("csi500", "all"):
        codes.extend(get_index_stocks("000905", "中证500"))
    codes = list(set(codes))

    if not codes:
        print("无法获取成分股列表")
        sys.exit(1)

    print(f"目标: {len(codes)} 只, 范围 {args.start}~{args.end}")
    print()
    collect_stocks(codes, args.start, args.end)


if __name__ == "__main__":
    main()

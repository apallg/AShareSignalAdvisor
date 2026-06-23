"""
服务器极速数据采集脚本

腾讯 IFZQ HTTP → MySQL → qlib 同步 (默认, 32 线程并发, ~3 分钟)
BaoStock → MySQL → qlib 同步 (串行, 数据完整, ~50 分钟)
混合模式 (推荐): 腾讯先拿近2年 → BaoStock 补全历史

用法:
  python scripts/fast_collect.py                     # 腾讯源, 32线程
  python scripts/fast_collect.py --source hybrid      # 混合模式(推荐): 腾讯+补全历史
  python scripts/fast_collect.py --source hybrid --pool csi300
  python scripts/fast_collect.py --source baostock    # BaoStock 纯慢速完整采集
  python scripts/fast_collect.py --workers 64         # 腾讯源, 64线程
  python scripts/fast_collect.py --no-sync            # 只采不同步qlib
"""
import argparse
import logging
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fast_collect")


def get_all_codes(pool="all"):
    """获取股票代码列表"""
    codes = []
    if pool in ("all", "csi_all"):
        try:
            import baostock as bs
            bs.login()
            rs = bs.query_all_stock(day="2026-06-23")
            while (rs.error_code == "0") and rs.next():
                row = rs.get_row_data()
                if len(row) >= 1:
                    raw = row[0]
                    if "." in raw:
                        raw = raw.split(".")[1]
                    if raw.isdigit() and len(raw) == 6:
                        codes.append(raw)
            bs.logout()
        except Exception:
            pass
    if pool in ("csi300", "csi_all"):
        try:
            import akshare as ak
            df = ak.index_stock_cons(symbol="000300")
            c = "品种代码" if "品种代码" in df.columns else df.columns[0]
            codes.extend(df[c].tolist())
        except Exception:
            pass
    if pool in ("csi500", "csi_all"):
        try:
            import akshare as ak
            df = ak.index_stock_cons(symbol="000905")
            c = "品种代码" if "品种代码" in df.columns else df.columns[0]
            codes.extend(df[c].tolist())
        except Exception:
            pass
    if not codes:
        try:
            import akshare as ak
            codes = ak.stock_info_a_code_name()["code"].tolist()
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            raise
    return list(set(codes))


# ═══════════════════ 腾讯 IFZQ ═══════════════════

def fetch_one_tencent(code, timeout=5):
    """从腾讯 IFZQ 获取一只股票的日线（前复权，~640天）"""
    mkt = "sh" if code.startswith(("6", "5")) else "sz"
    url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={mkt}{code},day,,,640,qfq"
    try:
        resp = requests.get(url, timeout=timeout, proxies={"http": None, "https": None})
        data = resp.json()
        if data.get("code") != 0:
            return None
        day_data = data.get("data", {}).get(f"{mkt}{code}", {})
        klines = day_data.get("qfqday") or day_data.get("day")
        if not klines:
            return None
        rows = []
        for k in klines:
            try:
                rows.append({
                    "date": str(k[0]).replace("-", ""),
                    "open": float(k[1]),
                    "close": float(k[2]),
                    "high": float(k[3]),
                    "low": float(k[4]),
                    "volume": float(k[5]),
                })
            except (IndexError, ValueError):
                continue
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df["amount"] = df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
        return (code, df)
    except Exception:
        return None


def save_batch(code, df):
    """单条写入 MySQL（线程安全）"""
    from core.database import DailyQuotesRepo
    DailyQuotesRepo.save_batch(code, df)


# ═══════════════════ BaoStock ═══════════════════

def fetch_one_baostock(bs, code):
    """从 BaoStock 获取一只股票的完整日线数据"""
    mkt = "sh" if code.startswith(("6", "5")) else "sz"
    full_code = f"{mkt}.{code}"
    try:
        rs = bs.query_history_k_data_plus(
            full_code,
            "date,open,high,low,close,volume,amount,turn,pctChg",
            start_date="2012-01-01",
            end_date="2026-06-23",
            frequency="d",
            adjustflag="2",
        )
        if rs.error_code != "0":
            return None
        rows = []
        while rs.next():
            row = rs.get_row_data()
            try:
                if row[0] == "":
                    continue
                rows.append({
                    "date": row[0].replace("-", ""),
                    "open": float(row[1]) if row[1] else 0,
                    "high": float(row[2]) if row[2] else 0,
                    "low": float(row[3]) if row[3] else 0,
                    "close": float(row[4]) if row[4] else 0,
                    "volume": float(row[5]) if row[5] else 0,
                    "amount": float(row[6]) if row[6] else 0,
                    "turnover": float(row[7]) if row[7] else 0,
                    "pct_chg": float(row[8]) if row[8] else 0,
                })
            except (IndexError, ValueError):
                continue
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df["amplitude"] = 0
        return (code, df)
    except Exception:
        return None


def fetch_one_baostock_range(bs, code, start_date, end_date):
    """从 BaoStock 获取指定日期范围的日线数据"""
    mkt = "sh" if code.startswith(("6", "5")) else "sz"
    full_code = f"{mkt}.{code}"
    try:
        rs = bs.query_history_k_data_plus(
            full_code,
            "date,open,high,low,close,volume,amount,turn,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",
        )
        if rs.error_code != "0":
            return None
        rows = []
        while rs.next():
            row = rs.get_row_data()
            try:
                if row[0] == "":
                    continue
                rows.append({
                    "date": row[0].replace("-", ""),
                    "open": float(row[1]) if row[1] else 0,
                    "high": float(row[2]) if row[2] else 0,
                    "low": float(row[3]) if row[3] else 0,
                    "close": float(row[4]) if row[4] else 0,
                    "volume": float(row[5]) if row[5] else 0,
                    "amount": float(row[6]) if row[6] else 0,
                    "turnover": float(row[7]) if row[7] else 0,
                    "pct_chg": float(row[8]) if row[8] else 0,
                })
            except (IndexError, ValueError):
                continue
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df["amplitude"] = 0
        return (code, df)
    except Exception:
        return None


# ═══════════════════ 主流程 ═══════════════════

def run_tencent(codes, args):
    """腾讯 IFZQ 并行采集"""
    lock = threading.Lock()
    success = fail = saved = 0
    total = len(codes)

    logger.info(f"开始采集 ({args.workers} 线程)...")
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one_tencent, c, args.timeout): c for c in codes}
        for i, fut in enumerate(as_completed(futures)):
            result = fut.result()
            if result is not None:
                code, df = result
                try:
                    save_batch(code, df)
                    with lock:
                        saved += 1
                        success += 1
                except Exception:
                    with lock:
                        fail += 1
            else:
                with lock:
                    fail += 1

            done = i + 1
            if done % 500 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                with lock:
                    sc, fl, sv = success, fail, saved
                logger.info(f"进度: {done}/{total} ({rate:.0f}只/s), 成功 {sc}, 失败 {fl}, 已写入 {sv}")

    elapsed = time.time() - t0
    logger.info(f"采集完成: {elapsed:.1f}s, 成功 {success}, 失败 {fail}")
    return saved


def run_baostock(codes, args):
    """BaoStock 串行采集"""
    import baostock as bs
    bs.login()
    total = len(codes)
    success = fail = saved = 0

    logger.info(f"开始采集 (串行, 间隔 {args.delay}s)...")
    t0 = time.time()

    for i, code in enumerate(codes):
        try:
            result = fetch_one_baostock(bs, code)
            if result is not None:
                code, df = result
                try:
                    save_batch(code, df)
                    saved += 1
                    success += 1
                except Exception:
                    fail += 1
            else:
                fail += 1
        except Exception:
            fail += 1

        done = i + 1
        if done % 100 == 0 or done == total:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else 0
            logger.info(
                f"进度: {done}/{total} ({rate:.1f}只/s), "
                f"成功 {success}, 失败 {fail}, 已写入 {saved}, "
                f"预计剩余 {remaining:.0f}s"
            )

        if args.delay > 0:
            time.sleep(args.delay)

    bs.logout()
    elapsed = time.time() - t0
    logger.info(f"采集完成: {elapsed:.1f}s, 成功 {success}, 失败 {fail}")
    return saved


def run_hybrid(codes, args):
    """混合模式: 腾讯快速填充 → BaoStock 覆盖残缺数据 + 补全历史"""
    import baostock as bs
    from core.database import Database

    # Phase 1: 腾讯并行 (~3 分钟) — 快速拿到各股票数据骨架
    logger.info("=" * 50)
    logger.info("Phase 1/3: 腾讯 IFZQ 并行采集 (~3 min)")
    logger.info("=" * 50)
    saved = run_tencent(codes, args)

    # Phase 2: 收集需要补全的股票
    logger.info("=" * 50)
    logger.info("Phase 2/3: 分析数据完整性")
    cur = Database.get_connection().cursor()

    # 找到 amount=0 的股票（腾讯数据残缺）及其日期范围
    cur.execute(
        "SELECT code, MIN(trade_date) as zero_start, MAX(trade_date) as zero_end, "
        "COUNT(*) as zero_cnt FROM daily_quotes "
        "WHERE amount = 0 OR amount IS NULL GROUP BY code"
    )
    zero_amount = {r["code"]: (str(r["zero_start"])[:10], str(r["zero_end"])[:10], r["zero_cnt"])
                   for r in cur.fetchall()}

    # 找到数据量不足的股票（可能只有腾讯数据，缺历史）
    cur.execute(
        "SELECT code, MIN(trade_date) as earliest, COUNT(*) as cnt "
        "FROM daily_quotes GROUP BY code"
    )
    db_stats = {r["code"]: (str(r["earliest"])[:10], r["cnt"]) for r in cur.fetchall()}

    full_backfill = []   # 全量 2012-2026 (没有 BaoStock 数据的股票)
    partial_backfill = []  # 只覆盖腾讯残缺段

    for code in codes:
        if code not in db_stats:
            full_backfill.append(code)
            continue

        earliest, cnt = db_stats[code]
        has_amount_zero = code in zero_amount

        if cnt >= 2000 and not has_amount_zero:
            continue  # 数据完整，跳过

        if not has_amount_zero:
            # 只有少量数据但不是 amount=0（罕见，可能是纯 BaoStock 只采了部分）
            if earliest > "2012-01-02":
                end_date = (pd.to_datetime(earliest) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                full_backfill.append((code, "2012-01-01", end_date))
            else:
                full_backfill.append(code)
            continue

        zero_start, zero_end, zero_cnt = zero_amount[code]

        if cnt < 200:
            # 几乎只有腾讯数据，全量 BaoStock
            full_backfill.append(code)
        else:
            # 有混合数据：BaoStock 覆盖腾讯的残缺段
            # 从 amount=0 的开始前推几天做缓冲区
            buf_start = (pd.to_datetime(zero_start) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            partial_backfill.append((code, buf_start, zero_end))

    total_tasks = len(full_backfill) + len(partial_backfill)
    if total_tasks == 0:
        logger.info("数据已完整，无需补全")
        return saved

    logger.info(
        f"需补全 {total_tasks} 只: "
        f"全量 {len(full_backfill)} 只, "
        f"覆盖残缺段 {len(partial_backfill)} 只"
    )

    # Phase 3: BaoStock 补全
    logger.info("=" * 50)
    logger.info("Phase 3/3: BaoStock 补全 (覆盖 amount=0 + 补历史)")
    logger.info("=" * 50)

    bs.login()
    success = fail = 0
    t0 = time.time()
    all_tasks = []

    for code in full_backfill:
        if isinstance(code, tuple):
            all_tasks.append(code)
        else:
            all_tasks.append((code, "2012-01-01", "2026-06-23"))
    all_tasks.extend(partial_backfill)

    for i, (code, start, end) in enumerate(all_tasks):
        try:
            result = fetch_one_baostock_range(bs, code, start, end)
            if result is not None:
                _, df = result
                try:
                    save_batch(code, df)
                    success += 1
                    saved += 1
                except Exception:
                    fail += 1
            else:
                fail += 1
        except Exception:
            fail += 1

        done = i + 1
        if done % 100 == 0 or done == total_tasks:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total_tasks - done) / rate if rate > 0 else 0
            logger.info(
                f"补全进度: {done}/{total_tasks} ({rate:.1f}只/s), "
                f"成功 {success}, 失败 {fail}, 预计剩余 {remaining:.0f}s"
            )

        if args.delay > 0:
            time.sleep(args.delay)

    bs.logout()
    elapsed = time.time() - t0
    logger.info(f"补全完成: {elapsed:.1f}s, 成功 {success}, 失败 {fail}")
    return saved


def main():
    parser = argparse.ArgumentParser(description="服务器极速数据采集")
    parser.add_argument("--source", default="tencent", choices=["tencent", "baostock", "hybrid"],
                        help="tencent(快,~640天) / baostock(完整) / hybrid(推荐:腾讯+补历史)")
    parser.add_argument("--workers", type=int, default=32, help="并发线程数 (仅 tencent)")
    parser.add_argument("--pool", default="all", choices=["all", "csi300", "csi500"])
    parser.add_argument("--timeout", type=int, default=5, help="HTTP 超时 (仅 tencent)")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="BaoStock 请求间隔秒数 (默认 0.1)")
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--retry-missing", action="store_true", help="只补采<100条的股票")
    args = parser.parse_args()

    codes = get_all_codes(args.pool)
    total = len(codes)
    logger.info(f"数据源: {args.source}, 股票池: {args.pool}, 共 {total} 只")

    if args.retry_missing:
        from core.database import Database
        cur = Database.get_connection().cursor()
        cur.execute("SELECT code FROM daily_quotes GROUP BY code HAVING COUNT(*) < 100")
        missing = {r["code"] for r in cur.fetchall()}
        codes = [c for c in codes if c in missing]
        logger.info(f"补采模式: {len(codes)} 只缺数据股票")

    if args.source == "hybrid":
        saved = run_hybrid(codes, args)
    elif args.source == "baostock":
        saved = run_baostock(codes, args)
    else:
        saved = run_tencent(codes, args)

    if not args.no_sync and saved > 0:
        logger.info("增量同步到 qlib...")
        import config
        from qlib_integration.bridge import QlibDataBridge
        bridge = QlibDataBridge(config.QLIB_DATA_DIR)
        result = bridge.sync_incremental()
        logger.info(f"qlib 同步完成: {result}")


if __name__ == "__main__":
    main()

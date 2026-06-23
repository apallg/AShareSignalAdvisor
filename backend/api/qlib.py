"""
qlib 集成 API — 数据同步、因子计算、模型训练、回测
"""
import uuid
import threading
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# 并发保护
_sync_lock = threading.Lock()
_train_jobs = {}
_train_lock = threading.Lock()
_collect_job_id = None  # 当前正在运行的采集任务 ID


# ── Pydantic Models ──

class SyncRequest(BaseModel):
    full_resync: bool = False


class TrainRequest(BaseModel):
    model_name: str = "lightgbm"
    factor_set: str = "Alpha158"
    instruments: str = "csi300"
    train_start: str = "2018-01-01"
    train_end: str = "2021-12-31"
    valid_start: str = "2022-01-01"
    valid_end: str = "2022-12-31"
    test_start: str = "2023-01-01"
    test_end: str = "2024-12-31"
    model_params: dict = {}
    auto_backtest: bool = True
    topk: int = 50
    n_drop: int = 5


class PredictRequest(BaseModel):
    experiment_id: str = ""
    run_id: str = ""
    instruments: str = "csi300"
    start_time: str = "2024-01-01"
    end_time: str = "2025-01-01"
    topk: int = 30


class BacktestRequest(BaseModel):
    predictions_file: str = ""
    topk: int = 50
    n_drop: int = 5
    start_time: str = "2023-01-01"
    end_time: str = "2024-12-31"


class CollectRequest(BaseModel):
    pool: str = "all"       # csi300, csi500, csi_all, all
    retry_missing: bool = False  # 补采数据库中 < 100 条记录的股票（仅 Tencent）
    force_tencent: bool = False  # 跳过 BaoStock，直接 Tencent


# ── Helpers ──

def _get_qlib_data_dir():
    import config
    return config.QLIB_DATA_DIR


# ── Endpoints ──

@router.post("/data/sync")
def sync_data(req: SyncRequest, background_tasks: BackgroundTasks):
    """触发 MySQL → qlib 二进制格式数据同步"""
    from qlib_integration.bridge import QlibDataBridge

    if not _sync_lock.acquire(blocking=False):
        return {"data": {"status": "syncing", "message": "同步正在进行中，请稍后"}}

    job_id = str(uuid.uuid4())[:8]

    if req.full_resync:
        # 全量同步：后台执行，返回 job_id 供轮询
        def _do_full_sync():
            try:
                bridge = QlibDataBridge(_get_qlib_data_dir())
                result = bridge.sync_all()
                _train_jobs[job_id] = {"status": "done", "result": result}
            except Exception as e:
                logger.exception("全量同步失败")
                _train_jobs[job_id] = {"status": "error", "error": str(e)}
            finally:
                _sync_lock.release()

        _train_jobs[job_id] = {"status": "running"}
        background_tasks.add_task(_do_full_sync)
        return {"data": {"job_id": job_id, "status": "started", "message": "全量同步已启动，请轮询状态"}}
    else:
        # 增量同步：同步执行，直接返回结果
        try:
            bridge = QlibDataBridge(_get_qlib_data_dir())
            result = bridge.sync_incremental()
            _train_jobs[job_id] = {"status": "done", "result": result}
            return {"data": {"job_id": job_id, "status": "done", "result": result}}
        except Exception as e:
            logger.exception("增量同步失败")
            _train_jobs[job_id] = {"status": "error", "error": str(e)}
            return {"data": {"job_id": job_id, "status": "error", "error": str(e)}}
        finally:
            _sync_lock.release()


@router.post("/data/collect")
def collect_data(req: CollectRequest, background_tasks: BackgroundTasks):
    """采集最新行情数据到 MySQL，然后增量同步到 qlib"""
    global _collect_job_id
    import datetime

    # 防止重复启动
    if _collect_job_id and _collect_job_id in _train_jobs:
        job = _train_jobs[_collect_job_id]
        if job.get("status") in ("running", "collect_done"):
            return {"data": {"job_id": _collect_job_id, "status": "running", "message": f"采集已在运行中 ({_collect_job_id}): {job.get('message', '')}"}}

    today = datetime.date.today()
    end_date = today.strftime("%Y%m%d")
    start_date = "20150101"

    # ── retry_missing: 从数据库查缺数据的股票，仅 Tencent ──
    if req.retry_missing:
        try:
            from core.database import Database
            cur = Database.get_connection().cursor()
            cur.execute("SELECT code, COUNT(*) as cnt FROM daily_quotes GROUP BY code HAVING cnt < 100")
            rows = cur.fetchall()
            codes = [r["code"] for r in rows]
        except Exception as e:
            return {"data": {"status": "error", "message": f"查询缺失股票失败: {e}"}}

        if not codes:
            return {"data": {"status": "done", "message": "没有缺数据的股票"}}

        job_id = str(uuid.uuid4())[:8]
        _collect_job_id = job_id
        _train_jobs[job_id] = {"status": "running", "message": f"补采 {len(codes)} 只缺失股票 (仅Tencent)"}

        def _do_retry():
            global _collect_job_id
            try:
                import time, random, pandas as pd, requests as req_lib
                from concurrent.futures import ThreadPoolExecutor, as_completed
                from core.database import DailyQuotesRepo

                total = len(codes)
                success = 0
                fail = 0
                lock = threading.Lock()
                workers = min(8, total)

                def _fetch_one(code):
                    mkt = "sh" if code.startswith(("6", "5")) else "sz"
                    try:
                        url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={mkt}{code},day,,,640,qfq"
                        resp = req_lib.get(url, timeout=10)
                        data = resp.json()
                        if data.get("code") == 0:
                            day_data = data.get("data", {}).get(f"{mkt}{code}", {})
                            klines = day_data.get("qfqday") or day_data.get("day")
                            if klines:
                                rows_list = []
                                for k in klines:
                                    try:
                                        d = str(k[0]).replace("-", "")
                                        rows_list.append({
                                            "date": d, "open": float(k[1]), "close": float(k[2]),
                                            "high": float(k[3]), "low": float(k[4]), "volume": float(k[5]),
                                        })
                                    except (IndexError, ValueError):
                                        continue
                                if rows_list:
                                    df = pd.DataFrame(rows_list)
                                    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
                                    df["amount"] = df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
                                    DailyQuotesRepo.save_batch(code, df)
                                    return (code, True)
                        return (code, False)
                    except Exception:
                        return (code, False)

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_fetch_one, c): c for c in codes}
                    done = 0
                    for f in as_completed(futures):
                        done += 1
                        code, ok = f.result()
                        if ok:
                            with lock:
                                success += 1
                        else:
                            with lock:
                                fail += 1
                        if done % 100 == 0:
                            with lock:
                                sc, fl = success, fail
                            _train_jobs[job_id] = {"status": "running", "message": f"补采进度: {done}/{total}, 成功 {sc}, 失败 {fl} ({workers}线程 Tencent)"}

                _train_jobs[job_id] = {"status": "collect_done", "message": f"补采完成: 成功 {success}, 失败 {fail}"}
                if success > 0:
                    from qlib_integration.bridge import QlibDataBridge
                    import config as app_config
                    bridge = QlibDataBridge(app_config.QLIB_DATA_DIR)
                    sync_result = bridge.sync_incremental()
                    _train_jobs[job_id] = {
                        "status": "done",
                        "message": f"补采+同步完成: {sync_result.get('new_dates',0)} 新交易日, {sync_result.get('new_stocks',0)} 新股票",
                        "collect": {"total": total, "success": success, "fail": fail},
                        "sync": sync_result,
                    }
            except Exception as e:
                logger.exception("补采失败")
                _train_jobs[job_id] = {"status": "error", "error": str(e)}
            finally:
                if _collect_job_id == job_id:
                    _collect_job_id = None

        background_tasks.add_task(_do_retry)
        return {"data": {"job_id": job_id, "status": "started", "message": f"开始补采 {len(codes)} 只缺失股票 (仅Tencent)"}}

    # ── 正常采集 ──
    codes = []
    if req.pool == "all":
        try:
            import baostock as bs
            bs.login()
            rs = bs.query_all_stock()
            while rs.next():
                row_data = rs.get_row_data()
                if len(row_data) >= 1:
                    raw = row_data[0]
                    if "." in raw:
                        raw = raw.split(".")[1]
                    if raw.isdigit() and len(raw) == 6:
                        codes.append(raw)
            bs.logout()
        except Exception:
            pass
        if not codes:
            try:
                import akshare as ak
                df = ak.stock_info_a_code_name()
                codes = df["code"].tolist()
            except Exception as e:
                logger.warning(f"获取全部A股列表失败: {e}")

    if req.pool in ("csi300", "csi_all") or (req.pool == "all" and not codes):
        try:
            import akshare as ak
            df = ak.index_stock_cons(symbol="000300")
            if "品种代码" in df.columns:
                codes.extend(df["品种代码"].tolist())
            elif "code" in df.columns:
                codes.extend(df["code"].tolist())
            else:
                codes.extend(df.iloc[:, 0].tolist())
        except Exception as e:
            logger.warning(f"获取沪深300成分股失败: {e}")
    if req.pool in ("csi500", "csi_all"):
        try:
            import akshare as ak
            df = ak.index_stock_cons(symbol="000905")
            if "品种代码" in df.columns:
                codes.extend(df["品种代码"].tolist())
            elif "code" in df.columns:
                codes.extend(df["code"].tolist())
            else:
                codes.extend(df.iloc[:, 0].tolist())
        except Exception as e:
            logger.warning(f"获取中证500成分股失败: {e}")

    if not codes:
        return {"data": {"status": "error", "message": "无法获取成分股列表"}}

    codes = list(set(codes))

    # ── 查已有足量数据的股票，Tencent 降级时跳过（防止覆盖 BaoStock 数据）──
    rich_codes = set()
    try:
        from core.database import Database
        cur = Database.get_connection().cursor()
        cur.execute("SELECT code, COUNT(*) as cnt FROM daily_quotes GROUP BY code HAVING cnt >= 500")
        rich_codes = {r["code"] for r in cur.fetchall()}
        cur.close()
    except Exception:
        pass

    job_id = str(uuid.uuid4())[:8]
    _collect_job_id = job_id
    use_bs = not req.force_tencent
    src_label = "BaoStock+Tencent" if use_bs else f"Tencent(跳过{len(rich_codes)}只已有数据)"
    _train_jobs[job_id] = {"status": "running", "message": f"开始采集 {len(codes)} 只股票, {start_date}~{end_date} ({src_label})"}

    BATCH_SIZE = 120
    BATCH_PAUSE = 40
    STOCK_DELAY = 0.15

    def _do_collect():
        global _collect_job_id
        try:
            import time, random, pandas as pd, requests as req_lib
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
            from core.database import DailyQuotesRepo

            success = fail = 0
            total = len(codes)
            baostock_ok = False
            bs_timeouts = 0
            lock = threading.Lock()

            if use_bs:
                try:
                    import baostock as bs
                    lg = bs.login()
                    if lg.error_code == "0":
                        rs = bs.query_history_k_data_plus(
                            "sh.600519", "date", start_date="2025-01-01", end_date="2025-01-02",
                            frequency="d", adjustflag="2"
                        )
                        baostock_ok = (rs is not None and rs.error_code == "0")
                        if baostock_ok:
                            _train_jobs[job_id]["message"] = f"BaoStock 已就绪，开始采集 {total} 只"
                except Exception:
                    pass

            # ── 并行 Tencent 模式 ──
            if not baostock_ok:
                # 跳过已有足量数据的股票，防止 Tencent 覆盖 BaoStock
                tcodes = [c for c in codes if c not in rich_codes]
                if len(tcodes) < len(codes):
                    _train_jobs[job_id]["message"] = f"Tencent 降级: 跳过 {len(codes)-len(tcodes)} 只已有数据，采集 {len(tcodes)} 只"
                total = len(tcodes)
                workers = min(8, max(total, 1))
                _train_jobs[job_id]["message"] = _train_jobs[job_id].get("message", f"开始采集 {total} 只 ({workers}线程 Tencent)")

                def _fetch_tencent(code):
                    mkt = "sh" if code.startswith(("6", "5")) else "sz"
                    try:
                        url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={mkt}{code},day,,,640,qfq"
                        resp = req_lib.get(url, timeout=10)
                        data = resp.json()
                        if data.get("code") == 0:
                            day_data = data.get("data", {}).get(f"{mkt}{code}", {})
                            klines = day_data.get("qfqday") or day_data.get("day")
                            if klines:
                                rows_list = []
                                for k in klines:
                                    try:
                                        d = str(k[0]).replace("-", "")
                                        rows_list.append({
                                            "date": d, "open": float(k[1]), "close": float(k[2]),
                                            "high": float(k[3]), "low": float(k[4]), "volume": float(k[5]),
                                        })
                                    except (IndexError, ValueError):
                                        continue
                                if rows_list:
                                    df = pd.DataFrame(rows_list)
                                    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
                                    df["amount"] = df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
                                    DailyQuotesRepo.save_batch(code, df)
                                    return (code, True)
                        return (code, False)
                    except Exception:
                        return (code, False)

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_fetch_tencent, c): c for c in tcodes}
                    done = 0
                    for f in as_completed(futures):
                        done += 1
                        code, ok = f.result()
                        if ok:
                            with lock:
                                success += 1
                        else:
                            with lock:
                                fail += 1
                        if done % 100 == 0:
                            with lock:
                                sc, fl = success, fail
                            _train_jobs[job_id] = {"status": "running", "message": f"采集进度: {done}/{total}, 成功 {sc}, 失败 {fl} ({workers}线程 Tencent)"}

            # ── 串行 BaoStock + Tencent 降级模式 ──
            else:
                for i, code in enumerate(codes):
                    df = None
                    ok = False
                    mkt = "sh" if code.startswith(("6", "5")) else "sz"

                    if baostock_ok:
                        try:
                            def _bs_query():
                                import baostock as bs
                                rs = bs.query_history_k_data_plus(
                                    f"{mkt}.{code}", "date,open,high,low,close,volume,amount",
                                    start_date="2015-01-01", end_date=str(today),
                                    frequency="d", adjustflag="2",
                                )
                                if rs is not None and rs.error_code == "0":
                                    rows_list = []
                                    while rs.next():
                                        rows_list.append(rs.get_row_data())
                                    return (True, rows_list, None)
                                elif rs is not None and rs.error_code == "10001011":
                                    return (False, None, "ban")
                                return (False, None, rs.error_code if rs else "rs_none")
                            success_flag, rows_list, err = ThreadPoolExecutor(max_workers=1).submit(_bs_query).result(timeout=15)
                            if err == "ban":
                                baostock_ok = False
                                _train_jobs[job_id]["message"] = f"BaoStock IP 被限 (第 {i+1}/{total})，降级到 Tencent"
                            elif success_flag and rows_list:
                                df = pd.DataFrame(rows_list, columns=["date", "open", "high", "low", "close", "volume", "amount"])
                                for col in ["open", "high", "low", "close", "volume", "amount"]:
                                    df[col] = pd.to_numeric(df[col], errors="coerce")
                                df["date"] = pd.to_datetime(df["date"])
                                df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
                                ok = True
                        except FutureTimeoutError:
                            bs_timeouts += 1
                            if bs_timeouts >= 3:
                                baostock_ok = False
                        except Exception:
                            pass

                    if not ok:
                        try:
                            url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={mkt}{code},day,,,640,qfq"
                            resp = req_lib.get(url, timeout=10)
                            data = resp.json()
                            if data.get("code") == 0:
                                day_data = data.get("data", {}).get(f"{mkt}{code}", {})
                                klines = day_data.get("qfqday") or day_data.get("day")
                                if klines:
                                    rows_list = []
                                    for k in klines:
                                        try:
                                            d = str(k[0]).replace("-", "")
                                            rows_list.append({
                                                "date": d, "open": float(k[1]), "close": float(k[2]),
                                                "high": float(k[3]), "low": float(k[4]), "volume": float(k[5]),
                                            })
                                        except (IndexError, ValueError):
                                            continue
                                    if rows_list:
                                        df = pd.DataFrame(rows_list)
                                        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
                                        df["amount"] = df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
                                        ok = True
                        except Exception:
                            pass

                    if ok and df is not None and not df.empty:
                        try:
                            DailyQuotesRepo.save_batch(code, df)
                            success += 1
                        except Exception:
                            fail += 1
                    else:
                        fail += 1

                    if (i + 1) % 50 == 0:
                        _train_jobs[job_id] = {"status": "running", "message": f"采集进度: {i+1}/{total}, 成功 {success}, 失败 {fail} (BaoStock+Tencent)"}

                    if (i + 1) % BATCH_SIZE == 0 and (i + 1) < total:
                        pause = BATCH_PAUSE + random.randint(-5, 5)
                        _train_jobs[job_id]["message"] = f"采集进度: {i+1}/{total}, 成功 {success}, 失败 {fail} — 暂停 {pause}s 防封..."
                        time.sleep(pause)

                    time.sleep(STOCK_DELAY + random.uniform(0, 0.05))

                if baostock_ok:
                    try:
                        import baostock as bs
                        bs.logout()
                    except Exception:
                        pass

            _train_jobs[job_id] = {
                "status": "collect_done",
                "message": f"采集完成: 成功 {success}, 失败 {fail}",
                "total": total, "success": success, "fail": fail,
                "date_range": f"{start_date}~{end_date}",
            }

            if success > 0:
                from qlib_integration.bridge import QlibDataBridge
                import config as app_config
                bridge = QlibDataBridge(app_config.QLIB_DATA_DIR)
                sync_result = bridge.sync_incremental()
                new_stocks = sync_result.get("new_stocks", 0)
                recommend = ""
                if new_stocks > 100:
                    recommend = f"新增 {new_stocks} 只股票，建议运行「全量同步」以获取完整历史数据"
                elif sync_result.get("new_dates", 0) == 0 and new_stocks == 0:
                    recommend = "数据已是最新"

                _train_jobs[job_id] = {
                    "status": "done",
                    "message": f"采集+同步完成: {sync_result.get('new_dates', 0)} 个新交易日, {new_stocks} 只新股票",
                    "collect": {"total": total, "success": success, "fail": fail},
                    "sync": sync_result,
                    "recommend": recommend,
                    "date_range": f"{start_date}~{end_date}",
                }

        except Exception as e:
            logger.exception("数据采集失败")
            _train_jobs[job_id] = {"status": "error", "error": str(e)}
        finally:
            if _collect_job_id == job_id:
                _collect_job_id = None

    background_tasks.add_task(_do_collect)
    return {"data": {"job_id": job_id, "status": "started", "message": f"开始采集 {len(codes)} 只股票, {start_date}~{end_date}"}}


@router.get("/data/quality")
def data_quality():
    """检查每日数据完整性 — 按股票统计覆盖范围"""
    import datetime
    from core.database import Database

    conn = Database.get_connection()
    cursor = conn.cursor()

    # 总交易日数（参考）
    today = datetime.date.today()
    cursor.execute("SELECT COUNT(*) as cnt FROM daily_quotes WHERE code = '600519'")
    ref = cursor.fetchone()["cnt"]

    # 每只股票的日期范围和数据条数
    cursor.execute("""
        SELECT code, MIN(trade_date) as mind, MAX(trade_date) as maxd, COUNT(*) as cnt
        FROM daily_quotes GROUP BY code ORDER BY cnt DESC
    """)
    stocks = []
    zero_count = 0
    short_count = 0  # < 100 条
    good_count = 0   # >= 500 条
    total = 0

    for row in cursor.fetchall():
        code = row["code"]
        mind = row["mind"]
        maxd = row["maxd"]
        cnt = row["cnt"]
        total += 1

        if cnt == 0:
            zero_count += 1
            status = "empty"
        elif cnt < 100:
            short_count += 1
            status = "short"
        elif cnt >= 500:
            good_count += 1
            status = "good"
        else:
            status = "ok"

        stocks.append({
            "code": code,
            "first_date": str(mind) if mind else None,
            "last_date": str(maxd) if maxd else None,
            "records": cnt,
            "status": status,
        })

    cursor.close()

    # 统计未覆盖的股票（用 ThreadPoolExecutor 防止 akshare 超时卡死）
    missing_codes = []
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        def _get_codes():
            import akshare as ak
            return ak.stock_info_a_code_name()["code"].tolist()
        all_codes = ThreadPoolExecutor(max_workers=1).submit(_get_codes).result(timeout=5)
        existing = {s["code"] for s in stocks}
        missing_codes = [c for c in all_codes if c not in existing]
    except (FutureTimeoutError, Exception):
        pass

    return {"data": {
        "total_stocks": total,
        "missing_stocks": len(missing_codes),
        "zero_records": zero_count,
        "short_records": short_count,
        "good_records": good_count,
        "stocks": stocks[:100],  # 前100只为概览
        "worst": [s for s in stocks if s["status"] in ("empty", "short")][:20],
        "missing_sample": missing_codes[:20],
    }}


@router.get("/data/sync/{job_id}")
def sync_status(job_id: str):
    """查询同步/采集任务状态"""
    job = _train_jobs.get(job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(404, "任务不存在")
    return {"data": job}


@router.get("/data/status")
def data_status():
    """获取 qlib 数据同步状态"""
    from qlib_integration.bridge import QlibDataBridge
    bridge = QlibDataBridge(_get_qlib_data_dir())
    return {"data": bridge.get_status()}


@router.get("/models")
def list_models():
    """列出可用的模型类型"""
    from qlib_integration.models import SUPPORTED_MODELS, DEFAULT_PARAMS
    models = []
    for name, (cls_name, module) in SUPPORTED_MODELS.items():
        models.append({
            "name": name,
            "class": cls_name,
            "module": module,
            "default_params": DEFAULT_PARAMS.get(name, {}),
        })
    return {"data": models}


@router.post("/models/train")
def train_model(req: TrainRequest, background_tasks: BackgroundTasks):
    """启动模型训练（异步）"""
    job_id = str(uuid.uuid4())[:8]

    def _do_train():
        try:
            from qlib_integration.models import QlibModelManager
            manager = QlibModelManager()
            result = manager.train(
                model_name=req.model_name,
                factor_set=req.factor_set,
                instruments=req.instruments,
                train_period=(req.train_start, req.train_end),
                valid_period=(req.valid_start, req.valid_end),
                test_period=(req.test_start, req.test_end),
                model_params=req.model_params,
            )
            backtest_result = None
            if req.auto_backtest and result.get("predictions") is not None and result.get("label") is not None:
                from qlib_integration.backtest import QlibBacktestRunner
                runner = QlibBacktestRunner()
                bt = runner.run_from_predictions(
                    predictions=result["predictions"],
                    label=result["label"],
                    topk=req.topk, n_drop=req.n_drop,
                    start_time=req.test_start, end_time=req.test_end,
                )
                backtest_result = bt

            _train_jobs[job_id] = {
                "status": "done",
                "result": {
                    "ic_mean": result.get("ic_mean"),
                    "icir": result.get("icir"),
                    "backtest": backtest_result,
                },
            }
        except Exception as e:
            logger.exception("模型训练失败")
            _train_jobs[job_id] = {"status": "error", "error": str(e)}

    _train_jobs[job_id] = {"status": "running"}
    background_tasks.add_task(_do_train)
    return {"data": {"job_id": job_id, "status": "started"}}


@router.get("/models/train/{job_id}")
def train_status(job_id: str):
    """查询训练任务状态"""
    job = _train_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return {"data": job}


@router.get("/trained-models")
def list_trained_models():
    """列出所有已训练的模型（扫描 MLflow 实验）"""
    import yaml
    from pathlib import Path
    import config as app_config

    mlruns_dir = Path(app_config.QLIB_MLFLOW_URI.replace("file:", "").replace("file:", ""))
    models = []

    for exp_dir in mlruns_dir.iterdir():
        if not exp_dir.is_dir() or exp_dir.name == "0":
            continue
        exp_id = exp_dir.name
        exp_meta = exp_dir / "meta.yaml"
        exp_name = exp_id
        if exp_meta.exists():
            try:
                with open(exp_meta) as f:
                    meta = yaml.safe_load(f)
                exp_name = meta.get("name", exp_id)
            except Exception:
                pass

        for run_dir in exp_dir.iterdir():
            if not run_dir.is_dir() or not (run_dir / "artifacts" / "params.pkl").exists():
                continue
            run_id = run_dir.name
            model_info = {
                "experiment_id": exp_id,
                "experiment_name": exp_name,
                "run_id": run_id,
                "model_class": "",
                "factor_set": "",
                "instruments": "",
                "train_period": "",
                "valid_period": "",
                "test_period": "",
                "ic": None,
                "icir": None,
                "has_predictions": (run_dir / "artifacts" / "pred.pkl").exists(),
                "has_label": (run_dir / "artifacts" / "label.pkl").exists(),
            }

            # 读取模型参数
            params_dir = run_dir / "params"
            if params_dir.exists():
                for pf in params_dir.iterdir():
                    try:
                        val = pf.read_text().strip()
                        if pf.name == "model.class":
                            model_info["model_class"] = val
                        elif pf.name == "dataset.kwargs.handler.class":
                            model_info["factor_set"] = val
                        elif pf.name == "dataset.kwargs.handler.kwargs.instruments":
                            model_info["instruments"] = val
                        elif pf.name == "dataset.kwargs.segments.train":
                            model_info["train_period"] = val
                        elif pf.name == "dataset.kwargs.segments.valid":
                            model_info["valid_period"] = val
                        elif pf.name == "dataset.kwargs.segments.test":
                            model_info["test_period"] = val
                    except Exception:
                        pass

            # 读取指标
            metrics_dir = run_dir / "metrics"
            if metrics_dir.exists():
                ic_file = metrics_dir / "IC"
                if ic_file.exists():
                    try:
                        parts = ic_file.read_text().strip().split()
                        if len(parts) >= 2:
                            model_info["ic"] = float(parts[1])
                    except Exception:
                        pass
                icir_file = metrics_dir / "ICIR"
                if icir_file.exists():
                    try:
                        parts = icir_file.read_text().strip().split()
                        if len(parts) >= 2:
                            model_info["icir"] = float(parts[1])
                    except Exception:
                        pass

            # 读取 meta.yaml 获取时间
            meta_file = run_dir / "meta.yaml"
            if meta_file.exists():
                try:
                    with open(meta_file) as f:
                        run_meta = yaml.safe_load(f)
                    model_info["start_time"] = run_meta.get("start_time")
                    model_info["user_id"] = run_meta.get("user_id")
                except Exception:
                    pass

            models.append(model_info)

    # 按 IC 降序排列
    models.sort(key=lambda m: m["ic"] or 0, reverse=True)
    return {"data": models}


@router.post("/models/predict")
def predict(req: PredictRequest):
    """加载已训练模型并生成预测"""
    import pickle
    from pathlib import Path
    import config as app_config

    if not req.experiment_id or not req.run_id:
        raise HTTPException(400, "必须指定 experiment_id 和 run_id")

    mlruns_dir = Path(app_config.QLIB_MLFLOW_URI.replace("file:", "").replace("file:", ""))
    model_path = mlruns_dir / req.experiment_id / req.run_id / "artifacts" / "params.pkl"

    if not model_path.exists():
        raise HTTPException(400, f"模型文件不存在: {model_path}")

    # 读取 run 配置获取 factor_set
    import yaml
    factor_set = "Alpha158"
    instruments = req.instruments
    params_dir = mlruns_dir / req.experiment_id / req.run_id / "params"
    if params_dir.exists():
        for pf in params_dir.iterdir():
            try:
                if pf.name == "dataset.kwargs.handler.class":
                    factor_set = pf.read_text().strip()
                elif pf.name == "dataset.kwargs.handler.kwargs.instruments":
                    instruments = pf.read_text().strip()
            except Exception:
                pass

    # 加载模型
    with open(model_path, "rb") as f:
        model = pickle.load(f)

    if model is None:
        raise HTTPException(400, "模型加载失败")

    # 构建 dataset 配置用于预测
    from qlib_integration.config import init_qlib
    init_qlib()

    from qlib_integration.models import QlibModelManager
    manager = QlibModelManager()

    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": {
                "class": factor_set,
                "module_path": "qlib.contrib.data.handler",
                "kwargs": {
                    "instruments": instruments,
                    "start_time": req.start_time,
                    "end_time": req.end_time,
                    "fit_start_time": req.start_time,
                    "fit_end_time": req.end_time,
                },
            },
            "segments": {"test": (req.start_time, req.end_time)},
        },
    }

    try:
        pred = manager.predict(model, dataset_config)
    except Exception as e:
        logger.exception("模型预测失败")
        raise HTTPException(500, f"预测失败: {str(e)}")

    # 转为可序列化格式，按日期分组取 top-k
    dates_summary = {}
    if hasattr(pred, "reset_index"):
        pred_df = pred.reset_index()
        # pred 是 Series with MultiIndex(datetime, instrument)
        # reset_index 后 columns: ['datetime', 'instrument', 0]
        if len(pred_df.columns) >= 3:
            pred_df.columns = ["datetime", "instrument", "score"]
        pred_df["datetime"] = pred_df["datetime"].astype(str).str[:10]
        pred_df = pred_df.sort_values("score", ascending=False)

        for dt, group in pred_df.groupby("datetime"):
            top = group.head(req.topk)
            dates_summary[dt] = [
                {"instrument": str(r["instrument"]), "score": float(r["score"])}
                for _, r in top.iterrows()
            ]

        records = pred_df.head(req.topk * 5).to_dict(orient="records")
    elif hasattr(pred, "to_dict"):
        records = [{"score": float(v)} for v in list(pred)]
    else:
        records = []

    return {
        "data": {
            "predictions": records,
            "count": len(records),
            "topk": req.topk,
            "by_date": dict(list(dates_summary.items())[:30]),
        }
    }


@router.post("/backtest/run")
def run_backtest(req: BacktestRequest):
    """运行 qlib 回测"""
    import pickle
    from pathlib import Path

    pred_path = Path(req.predictions_file)
    if not pred_path.exists():
        raise HTTPException(400, f"预测文件不存在: {req.predictions_file}")

    data = pickle.loads(pred_path.read_bytes())

    from qlib_integration.backtest import QlibBacktestRunner
    runner = QlibBacktestRunner()

    if isinstance(data, tuple) and len(data) == 2:
        predictions, label = data
    else:
        predictions = data
        label = None

    if label is None:
        raise HTTPException(400, "预测文件缺少标签数据，请保存为 (predictions, label) 元组")

    result = runner.run_from_predictions(
        predictions=predictions,
        label=label,
        topk=req.topk,
        n_drop=req.n_drop,
        start_time=req.start_time,
        end_time=req.end_time,
    )
    return {"data": result}


@router.get("/experiments")
def list_experiments():
    """列出 MLflow 实验"""
    from qlib_integration.config import init_qlib
    init_qlib()
    from qlib.workflow import R
    from qlib.workflow.expm import MLflowExpManager
    try:
        exp_manager = R.exp_manager
        experiments = exp_manager.client.search_experiments()
        return {"data": [{"id": e.experiment_id, "name": e.name} for e in experiments]}
    except Exception as e:
        return {"data": [], "error": str(e)}


@router.get("/experiments/{exp_id}")
def get_experiment(exp_id: str):
    """获取实验详情及所有 run"""
    import yaml
    from pathlib import Path
    import config as app_config

    mlruns_dir = Path(app_config.QLIB_MLFLOW_URI.replace("file:", "").replace("file:", ""))
    exp_dir = mlruns_dir / exp_id
    if not exp_dir.exists():
        return {"data": {"runs": [], "name": exp_id}}

    exp_meta_file = exp_dir / "meta.yaml"
    exp_name = exp_id
    if exp_meta_file.exists():
        try:
            with open(exp_meta_file) as f:
                exp_name = yaml.safe_load(f).get("name", exp_id)
        except Exception:
            pass

    runs = []
    for run_dir in exp_dir.iterdir():
        if not run_dir.is_dir() or run_dir.name == "meta.yaml":
            continue
        run_data = {"run_id": run_dir.name, "metrics": {}, "params": {}}

        metrics_dir = run_dir / "metrics"
        if metrics_dir.exists():
            for mf in metrics_dir.iterdir():
                try:
                    parts = mf.read_text().strip().split()
                    if len(parts) >= 2:
                        run_data["metrics"][mf.name] = float(parts[1])
                except Exception:
                    pass

        params_dir = run_dir / "params"
        if params_dir.exists():
            for pf in params_dir.iterdir():
                try:
                    run_data["params"][pf.name] = pf.read_text().strip()
                except Exception:
                    pass

        if (run_dir / "artifacts" / "params.pkl").exists():
            run_data["has_model"] = True
        if (run_dir / "artifacts" / "pred.pkl").exists():
            run_data["has_predictions"] = True

        runs.append(run_data)

    runs.sort(key=lambda r: r["metrics"].get("IC", 0), reverse=True)
    return {"data": {"name": exp_name, "runs": runs}}

"""实盘策略运行 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import config

router = APIRouter()


class StartRequest(BaseModel):
    strategy_key: str  # "golden_cross" | "bollinger" | "breakout" | "mean_reversion" | "momentum"
    symbol: str  # 股票代码
    params: dict = {}
    interval_sec: int = 60  # 轮询间隔


class FusionConfigRequest(BaseModel):
    enabled: bool = True
    mode: str = "filter"         # "filter" | "override"
    min_confidence: float = 0.6
    weights: dict = {}


def get_live_runner():
    from execution.live.runner import get_runner
    return get_runner()


@router.get("/strategies")
def list_strategies():
    runner = get_live_runner()
    return {"data": runner.list_strategies()}


@router.post("/start")
def start_runner(req: StartRequest):
    from execution.live.strategies import LIVE_STRATEGIES
    if req.strategy_key not in LIVE_STRATEGIES:
        raise HTTPException(400, f"未知策略: {req.strategy_key}")
    if not req.symbol.strip():
        raise HTTPException(400, "股票代码不能为空")

    # 确保 broker 可用
    from backend.api.trading import get_broker
    broker = get_broker()

    runner = get_live_runner()
    try:
        runner_id = runner.start(
            strategy_key=req.strategy_key,
            symbol=req.symbol.strip(),
            broker=broker,
            params=req.params,
            interval_sec=max(10, req.interval_sec),
        )
        return {"data": {"runner_id": runner_id, "status": "started"}}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/stop/{runner_id:path}")
def stop_runner(runner_id: str):
    runner = get_live_runner()
    ok = runner.stop(runner_id)
    if not ok:
        raise HTTPException(404, "运行器不存在或已停止")
    return {"status": "ok"}


@router.get("/status")
def list_status():
    runner = get_live_runner()
    return {"data": runner.get_status()}


@router.get("/status/{runner_id:path}")
def get_status(runner_id: str):
    runner = get_live_runner()
    s = runner.get_status(runner_id)
    if not s:
        raise HTTPException(404, "运行器不存在")
    return {"data": s}


@router.get("/signals")
def list_signals(limit: int = 50):
    runner = get_live_runner()
    return {"data": runner.get_signals(limit)}


@router.get("/trading-time")
def get_trading_time_status():
    from core.trading_time import (
        is_trading_day, is_trading_time, is_force_close_window,
        get_trading_session, time_until_close,
    )
    from datetime import datetime
    now = datetime.now()
    return {"data": {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "is_trading_day": is_trading_day(now),
        "is_trading_time": is_trading_time(now),
        "session": get_trading_session(now),
        "is_force_close_window": is_force_close_window(now),
        "seconds_until_close": time_until_close(now),
    }}


@router.get("/signal-fusion/config")
def get_fusion_config():
    return {"data": {
        "enabled": config.SIGNAL_FUSION_ENABLED,
        "mode": config.SIGNAL_FUSION_MODE,
        "min_confidence": config.SIGNAL_FUSION_MIN_CONFIDENCE,
        "weights": {
            "MACD": config.SIGNAL_FUSION_WEIGHT_MACD,
            "RSI": config.SIGNAL_FUSION_WEIGHT_RSI,
            "MA": config.SIGNAL_FUSION_WEIGHT_MA,
            "KDJ": config.SIGNAL_FUSION_WEIGHT_KDJ,
            "BB": config.SIGNAL_FUSION_WEIGHT_BB,
            "VOLUME": config.SIGNAL_FUSION_WEIGHT_VOLUME,
        },
    }}


@router.put("/signal-fusion/config")
def update_fusion_config(req: FusionConfigRequest):
    if req.mode not in ("filter", "override"):
        raise HTTPException(400, "mode 必须为 filter 或 override")
    if not (0 < req.min_confidence <= 1.0):
        raise HTTPException(400, "min_confidence 必须在 (0, 1] 范围内")

    config.SIGNAL_FUSION_ENABLED = req.enabled
    config.SIGNAL_FUSION_MODE = req.mode
    config.SIGNAL_FUSION_MIN_CONFIDENCE = req.min_confidence
    for key, val in (req.weights or {}).items():
        setattr(config, f"SIGNAL_FUSION_WEIGHT_{key.upper()}", val)

    for r in get_live_runner().get_status():
        r["signal_fusion_enabled"] = req.enabled
        r["fusion_mode"] = req.mode
        r["fusion_min_confidence"] = req.min_confidence
        if req.weights:
            r.setdefault("fusion_weights", {}).update(req.weights)

    return {"status": "ok"}


@router.get("/signal-fusion/{symbol}")
def get_fusion_signal(symbol: str):
    from core.data_fetcher import DataFetcher
    from core.analyzer import Analyzer
    from core.signal_fusion import SignalFusion
    from datetime import datetime

    fetcher = DataFetcher()
    end_date = datetime.now().strftime("%Y-%m-%d")
    df = fetcher.get_stock_daily(symbol.strip(), "2024-01-01", end_date)
    if df is None or df.empty:
        raise HTTPException(404, f"未找到 {symbol} 的行情数据")

    df = Analyzer.add_indicators(df)
    fusion = SignalFusion()
    result = fusion.evaluate(df)

    return {"data": {
        "symbol": symbol.strip(),
        "score": result.score,
        "action": result.action,
        "confidence": result.confidence,
        "indicator_votes": result.indicator_votes,
        "reasons": result.reasons,
        "latest_indicators": Analyzer.latest_indicators(df),
    }}


class ForceCloseConfigRequest(BaseModel):
    enabled: bool = True


@router.get("/force-close/config")
def get_force_close_config():
    return {"data": {
        "enabled": config.FORCE_CLOSE_ENABLED,
        "time": config.FORCE_CLOSE_TIME,
        "reason": config.FORCE_CLOSE_REASON,
    }}


@router.put("/force-close/config")
def update_force_close_config(req: ForceCloseConfigRequest):
    config.FORCE_CLOSE_ENABLED = req.enabled
    for r in get_live_runner().get_status():
        r["force_close_enabled"] = req.enabled
    return {"status": "ok"}

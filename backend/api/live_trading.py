"""实盘策略运行 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class StartRequest(BaseModel):
    strategy_key: str  # "golden_cross" | "bollinger" | "breakout" | "mean_reversion" | "momentum"
    symbol: str  # 股票代码
    params: dict = {}
    interval_sec: int = 60  # 轮询间隔


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


@router.post("/stop/{runner_id}")
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


@router.get("/status/{runner_id}")
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

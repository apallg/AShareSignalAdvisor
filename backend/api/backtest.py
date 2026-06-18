"""回测 API"""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

router = APIRouter()


class BacktestRequest(BaseModel):
    strategy_name: str
    params: Dict[str, Any] = {}
    codes: List[str] = ["600519"]
    start_date: str = "20230101"
    end_date: str = "20241231"
    cash: float = 1000000
    commission: float = 0.0003


class OptimizeRequest(BaseModel):
    strategy_name: str
    codes: List[str] = ["600519"]
    start_date: str = "20230101"
    end_date: str = "20241231"
    param_grid: Dict[str, List[Any]] = {}


def _save_result(result: Dict):
    """持久化回测结果到 MySQL"""
    from core.database import Database
    if not Database.is_available():
        return
    try:
        Database.execute(
            "INSERT INTO backtest_results (id, strategy_name, stock_code, params, metrics, trades, equity_curve) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE metrics=VALUES(metrics), trades=VALUES(trades), equity_curve=VALUES(equity_curve)",
            (
                result.get("id", ""),
                result.get("strategy_name", ""),
                result.get("stock_code", ""),
                json.dumps(result.get("params", {}), ensure_ascii=False),
                json.dumps(result.get("metrics", {}), ensure_ascii=False),
                json.dumps(result.get("trades", []), ensure_ascii=False),
                json.dumps(result.get("equity_curve", []), ensure_ascii=False),
            ),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"回测结果持久化失败: {e}")


def _load_result(result_id: str) -> Optional[Dict]:
    """从 MySQL 加载回测结果"""
    from core.database import Database
    if not Database.is_available():
        return None
    try:
        row = Database.fetchone(
            "SELECT * FROM backtest_results WHERE id=%s", (result_id,)
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "strategy": row["strategy_name"],
            "stock": row["stock_code"],
            "params": json.loads(row["params"]) if isinstance(row["params"], str) else row["params"],
            "metrics": json.loads(row["metrics"]) if isinstance(row["metrics"], str) else row["metrics"],
            "trades": json.loads(row["trades"]) if isinstance(row["trades"], str) else row["trades"],
            "equity_curve": json.loads(row["equity_curve"]) if isinstance(row["equity_curve"], str) else row["equity_curve"],
            "created_at": str(row["created_at"]) if row.get("created_at") else "",
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"加载回测结果失败: {e}")
        return None


@router.get("/strategies")
def list_backtest_strategies():
    """获取所有可用策略列表"""
    from strategies.registry import list_strategies, auto_discover
    try:
        strategies = list_strategies()
        if not strategies:
            auto_discover()
            strategies = list_strategies()
        return {"data": strategies}
    except Exception as e:
        return {"data": {}, "error": str(e)}


@router.post("/run")
def run_backtest(req: BacktestRequest):
    """执行回测"""
    from strategies.registry import get_strategy
    from engine.backtest import BacktestEngine
    from engine.data_feed import QuantDataFeed
    from core.data_fetcher import DataFetcher
    from core.analyzer import Analyzer
    import pandas as pd
    
    strategy_info = get_strategy(req.strategy_name)
    if not strategy_info:
        raise HTTPException(404, f"策略 {req.strategy_name} 未找到")
    
    strategy_cls = strategy_info['class']
    results = []
    
    for code in req.codes:
        try:
            fetcher = DataFetcher()
            analyzer = Analyzer()
            
            df = fetcher.get_stock_daily(
                code, req.start_date, req.end_date)
            if df is None or df.empty:
                continue
            
            df = analyzer.add_indicators(df)
            df.columns = [c.lower().strip() for c in df.columns]
            
            if 'datetime' not in df.columns and 'date' in df.columns:
                df['datetime'] = pd.to_datetime(df['date'])
            df['openinterest'] = 0
            
            data_feed = QuantDataFeed(dataname=df)
            engine = BacktestEngine(cash=req.cash, commission=req.commission)

            result = engine.run(
                strategy_cls, req.params, data_feed,
                strategy_id=f"{req.strategy_name}_{code}",
                stock_code=code,
                start_date=req.start_date,
                end_date=req.end_date
            )
            # 记入运行时参数
            result['params'] = req.params
            # 持久化到 MySQL
            _save_result(result)
            results.append(result)
        except Exception as e:
            raise HTTPException(500, f"{code} 回测失败: {e}")
    
    return {"data": results}


@router.get("/result/{result_id}")
def get_backtest_result(result_id: str):
    """获取回测结果"""
    result = _load_result(result_id)
    if not result:
        raise HTTPException(404, f"回测结果 {result_id} 未找到")
    return {"data": result}


@router.post("/optimize")
def optimize_strategy(req: OptimizeRequest):
    """参数优化"""
    from strategies.registry import get_strategy
    from engine.backtest import BacktestEngine
    from engine.data_feed import QuantDataFeed
    from core.data_fetcher import DataFetcher
    from core.analyzer import Analyzer
    import itertools
    import pandas as pd
    
    strategy_info = get_strategy(req.strategy_name)
    if not strategy_info:
        raise HTTPException(404, f"策略 {req.strategy_name} 未找到")
    
    strategy_cls = strategy_info['class']
    param_names = list(req.param_grid.keys())
    param_values = list(req.param_grid.values())
    combinations = list(itertools.product(*param_values))
    
    results = []
    
    for combo in combinations:
        params = dict(zip(param_names, combo))
        try:
            fetcher = DataFetcher()
            analyzer = Analyzer()
            code = req.codes[0]
            
            df = fetcher.get_stock_daily(
                code, req.start_date, req.end_date)
            if df is None or df.empty:
                continue
            
            df = analyzer.add_indicators(df)
            df.columns = [c.lower().strip() for c in df.columns]
            
            if 'datetime' not in df.columns and 'date' in df.columns:
                df['datetime'] = pd.to_datetime(df['date'])
            df['openinterest'] = 0
            
            data_feed = QuantDataFeed(dataname=df)
            engine = BacktestEngine(cash=1000000, commission=0.0003)
            
            result = engine.run(
                strategy_cls, params, data_feed,
                strategy_id=f"opt_{code}",
                stock_code=code,
                start_date=req.start_date,
                end_date=req.end_date
            )
            result['params'] = params
            results.append(result)
        except Exception as e:
            results.append({
                'params': params,
                'error': str(e)
            })
    
    return {"data": results}


@router.get("/history")
def get_backtest_history(limit: int = 20):
    """历史回测记录"""
    from core.database import Database
    if not Database.is_available():
        return {"data": []}
    try:
        rows = Database.fetchall(
            "SELECT id, strategy_name, stock_code, metrics, created_at "
            "FROM backtest_results ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        results = []
        for row in rows:
            metrics = row.get("metrics")
            if isinstance(metrics, str):
                metrics = json.loads(metrics)
            results.append({
                "id": row["id"],
                "strategy": row["strategy_name"],
                "stock": row["stock_code"],
                "metrics": metrics or {},
                "created_at": str(row["created_at"]) if row.get("created_at") else "",
            })
        return {"data": results}
    except Exception:
        return {"data": []}

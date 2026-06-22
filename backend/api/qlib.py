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
    model_path: str = ""
    instruments: str = "csi300"
    start_time: str = None
    end_time: str = None


class BacktestRequest(BaseModel):
    predictions_file: str = ""
    topk: int = 50
    n_drop: int = 5
    start_time: str = "2023-01-01"
    end_time: str = "2024-12-31"


# ── Helpers ──

def _get_qlib_data_dir():
    import config
    return config.QLIB_DATA_DIR


# ── Endpoints ──

@router.post("/data/sync")
def sync_data(req: SyncRequest, background_tasks: BackgroundTasks):
    """触发 MySQL → qlib 二进制格式数据同步"""
    if not _sync_lock.acquire(blocking=False):
        return {"data": {"status": "syncing", "message": "同步正在进行中，请稍后"}}

    job_id = str(uuid.uuid4())[:8]

    def _do_sync():
        try:
            from qlib_integration.bridge import QlibDataBridge
            bridge = QlibDataBridge(_get_qlib_data_dir())
            if req.full_resync:
                result = bridge.sync_all()
            else:
                result = bridge.sync_all()  # TODO: incremental sync
            _train_jobs[job_id] = {"status": "done", "result": result}
        except Exception as e:
            logger.exception("数据同步失败")
            _train_jobs[job_id] = {"status": "error", "error": str(e)}
        finally:
            _sync_lock.release()

    background_tasks.add_task(_do_sync)
    return {"data": {"job_id": job_id, "status": "started"}}


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


@router.post("/models/predict")
def predict(req: PredictRequest):
    """生成预测信号"""
    from qlib_integration.models import QlibModelManager
    from qlib_integration.config import init_qlib
    init_qlib()

    from qlib.workflow import R
    model = R.load_object("params.pkl")
    if model is None:
        raise HTTPException(400, "没有已训练的模型，请先训练")

    manager = QlibModelManager()
    pred = manager.predict(model, {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": {
                "class": "Alpha158",
                "module_path": "qlib.contrib.data.handler",
                "kwargs": {
                    "instruments": req.instruments,
                    "start_time": req.start_time,
                    "end_time": req.end_time,
                    "fit_start_time": req.start_time,
                    "fit_end_time": req.end_time,
                },
            },
            "segments": {"test": (req.start_time, req.end_time)},
        },
    })

    # 转为可序列化格式
    if hasattr(pred, "reset_index"):
        pred_df = pred.reset_index()
        pred_df.columns = ["instrument", "datetime", "score"]
        records = pred_df.to_dict(orient="records")
    else:
        records = []
    return {"data": {"predictions": records, "count": len(records)}}


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
    """获取实验详情"""
    from qlib_integration.config import init_qlib
    init_qlib()
    from qlib.workflow import R
    try:
        runs = R.exp_manager.client.search_runs([exp_id])
        return {"data": [{"id": r.info.run_id, "metrics": r.data.metrics} for r in runs]}
    except Exception as e:
        return {"data": [], "error": str(e)}

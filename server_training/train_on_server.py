"""
4090 服务器模型训练脚本
按顺序训练 LightGBM → ALSTM → TRA，记录指标，选出最佳模型

用法:
  python train_on_server.py                    # 训练全部 3 个模型
  python train_on_server.py --models lightgbm   # 只训练 LightGBM
  python train_on_server.py --skip-sync          # 跳过数据采集步骤
"""
import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("training.log")],
)
logger = logging.getLogger("train")

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

import qlib
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, SigAnaRecord

import config as app_config

DATASET_CONFIG = {
    "class": "DatasetH",
    "module_path": "qlib.data.dataset",
    "kwargs": {
        "handler": {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "instruments": "all",
                "start_time": "2012-01-01",
                "end_time": "2026-06-23",
                "fit_start_time": "2012-01-01",
                "fit_end_time": "2024-12-31",
            },
        },
        "segments": {
            "train": ("2012-01-01", "2024-12-31"),
            "valid": ("2025-01-01", "2025-12-31"),
            "test": ("2026-01-01", "2026-06-23"),
        },
    },
}

MODELS = {
    "lightgbm": {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "learning_rate": 0.05,
            "max_depth": 10,
            "num_leaves": 256,
            "num_threads": 16,
            "min_child_samples": 20,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "early_stopping_rounds": 50,
            "verbose_eval": -1,
        },
    },
    "alstm": {
        "class": "ALSTM",
        "module_path": "qlib.contrib.model.pytorch_alstm",
        "kwargs": {
            "d_feat": 158,
            "hidden_size": 128,
            "num_layers": 2,
            "dropout": 0.0,
            "batch_size": 4096,
            "n_epochs": 200,
            "lr": 0.001,
            "early_stop": 20,
            "loss": "mse",
            "optimizer": "adam",
            "GPU": 0,
        },
    },
    "gru": {
        "class": "GRU",
        "module_path": "qlib.contrib.model.pytorch_gru",
        "kwargs": {
            "d_feat": 158,
            "hidden_size": 128,
            "num_layers": 2,
            "dropout": 0.0,
            "batch_size": 4096,
            "n_epochs": 200,
            "lr": 0.001,
            "early_stop": 20,
            "loss": "mse",
            "optimizer": "adam",
            "GPU": 0,
        },
    },
    "transformer": {
        "class": "TransformerModel",
        "module_path": "qlib.contrib.model.pytorch_transformer",
        "kwargs": {
            "d_feat": 158,
            "hidden_size": 128,
            "num_layers": 2,
            "nhead": 4,
            "dropout": 0.1,
            "batch_size": 2048,
            "n_epochs": 200,
            "lr": 0.001,
            "early_stop": 20,
            "GPU": 0,
        },
    },
    "tcn": {
        "class": "TCN",
        "module_path": "qlib.contrib.model.pytorch_tcn",
        "kwargs": {
            "d_feat": 158,
            "hidden_size": 128,
            "num_levels": 8,
            "kernel_size": 3,
            "dropout": 0.1,
            "batch_size": 4096,
            "n_epochs": 200,
            "lr": 0.001,
            "early_stop": 20,
            "GPU": 0,
        },
    },
    "tra": {
        "class": "TRAModel",
        "module_path": "qlib.contrib.model.pytorch_tra",
        "kwargs": {
            "model_config": {
                "input_size": 158,
                "hidden_size": 128,
                "num_layers": 2,
                "rnn_arch": "GRU",
                "use_attn": True,
            },
            "tra_config": {
                "num_states": 3,
                "hidden_size": 8,
                "src_info": "LR_TPE",
            },
            "model_type": "RNN",
            "lr": 0.001,
            "n_epochs": 300,
            "early_stop": 50,
            "batch_size": 4096,
            "GPU": 0,
        },
    },
    "xgboost": {
        "class": "XGBModel",
        "module_path": "qlib.contrib.model.xgboost",
        "kwargs": {
            "max_depth": 10,
            "learning_rate": 0.05,
            "n_estimators": 800,
            "nthread": 16,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "early_stopping_rounds": 50,
        },
    },
}


def init_qlib_env():
    qlib.init(
        provider_uri=app_config.QLIB_PROVIDER_URI,
        region=REG_CN,
        n_jobs=1,
        joblib_backend="threading",
        exp_manager={
            "class": "MLflowExpManager",
            "module_path": "qlib.workflow.expm",
            "kwargs": {
                "uri": app_config.QLIB_MLFLOW_URI,
                "default_exp_name": "server_training",
            },
        },
    )
    logger.info("Qlib 初始化完成")


def train_one_model(model_name, model_config, dataset_config):
    logger.info(f"{'='*60}")
    logger.info(f"开始训练: {model_name}")
    logger.info(f"{'='*60}")

    task_config = {"model": model_config, "dataset": dataset_config}
    result = {}

    with R.start(experiment_name="server_training"):
        R.log_params(**flatten_dict(task_config))

        model = init_instance_by_config(task_config["model"])
        dataset = init_instance_by_config(task_config["dataset"])

        t0 = time.time()
        model.fit(dataset)
        train_time = time.time() - t0

        R.save_objects(**{"params.pkl": model})

        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()

        sar = SigAnaRecord(recorder)
        sar.generate()

        ic = sar.load("ic.pkl")
        ric = sar.load("ric.pkl")

        ic_mean = float(ic.mean()) if ic is not None else None
        ic_std = float(ic.std()) if ic is not None else 0
        icir = ic_mean / ic_std if ic_std > 0 else None
        ric_mean = float(ric.mean()) if ric is not None else None

        result = {
            "model": model_name,
            "train_time": round(train_time, 1),
            "IC": round(ic_mean, 6) if ic_mean else None,
            "ICIR": round(icir, 6) if icir else None,
            "Rank_IC": round(ric_mean, 6) if ric_mean else None,
            "run_id": recorder.id,
        }

        logger.info(f"结果: {json.dumps(result, ensure_ascii=False)}")

    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return result


def run_data_collection():
    logger.info("=" * 50)
    logger.info("Phase 0: 数据采集 + Qlib 同步")
    logger.info("=" * 50)
    import subprocess
    subprocess.run([sys.executable, "scripts/fast_collect.py", "--source", "hybrid", "--workers", "64"])
    from qlib_integration.bridge import QlibDataBridge
    bridge = QlibDataBridge(app_config.QLIB_DATA_DIR)
    result = bridge.sync_all()
    logger.info(f"数据同步完成: {result}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+",
                        default=["lightgbm", "alstm", "tra"],
                        choices=list(MODELS.keys()))
    parser.add_argument("--skip-sync", action="store_true",
                        help="跳过数据采集步骤")
    args = parser.parse_args()

    if not args.skip_sync:
        run_data_collection()

    init_qlib_env()

    results = []
    for model_name in args.models:
        if model_name not in MODELS:
            logger.error(f"未知模型: {model_name}")
            continue
        try:
            r = train_one_model(model_name, MODELS[model_name], DATASET_CONFIG)
            results.append(r)
        except Exception as e:
            logger.error(f"{model_name} 训练失败: {e}", exc_info=True)

    logger.info(f"\n{'='*60}")
    logger.info("训练汇总")
    logger.info(f"{'='*60}")
    for r in sorted(results, key=lambda x: x.get("ICIR") or 0, reverse=True):
        logger.info(
            f"  {r['model']:12s}  IC={r['IC']}  ICIR={r['ICIR']}  "
            f"Rank_IC={r['Rank_IC']}  耗时={r['train_time']}s"
        )

    with open("training_results.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("结果已保存到 training_results.json")


if __name__ == "__main__":
    main()

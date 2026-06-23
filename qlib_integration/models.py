"""
qlib 模型训练/预测封装 — LightGBM, XGBoost, CatBoost, LSTM, GRU, Transformer 等
"""
import os
import logging
import pandas as pd

from qlib_integration.config import init_qlib

logger = logging.getLogger(__name__)

SUPPORTED_MODELS = {
    "lightgbm":   ("LGBModel",       "qlib.contrib.model.gbdt"),
    "xgboost":    ("XGBModel",       "qlib.contrib.model.xgboost"),
    "catboost":   ("CatBoostModel",  "qlib.contrib.model.catboost_model"),
    "linear":     ("LinearModel",    "qlib.contrib.model.linear"),
    "lstm":       ("LSTM",           "qlib.contrib.model.pytorch_lstm"),
    "gru":        ("GRU",            "qlib.contrib.model.pytorch_gru"),
    "lstm_ts":    ("LSTM_ts",        "qlib.contrib.model.pytorch_lstm_ts"),
    "gru_ts":     ("GRU_ts",         "qlib.contrib.model.pytorch_gru_ts"),
    "transformer":("Transformer",    "qlib.contrib.model.pytorch_transformer"),
    "tabnet":     ("TabNetModel",    "qlib.contrib.model.pytorch_tabnet"),
    "tcn":        ("TCN",            "qlib.contrib.model.pytorch_tcn"),
    "hist":       ("HIST",           "qlib.contrib.model.pytorch_hist"),
    "alstm":      ("ALSTM",          "qlib.contrib.model.pytorch_alstm"),
    "sfm":        ("SFM",            "qlib.contrib.model.pytorch_sfm"),
    "tcn_ts":     ("TCN_ts",         "qlib.contrib.model.pytorch_tcn_ts"),
}

DEFAULT_PARAMS = {
    "lightgbm": {
        "loss": "mse",
        "learning_rate": 0.03,
        "max_depth": 8,
        "num_leaves": 128,
        "num_threads": 4,
        "min_child_samples": 20,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "early_stopping_rounds": 50,
        "verbose_eval": -1,
    },
    "xgboost": {
        "max_depth": 8,
        "learning_rate": 0.03,
        "n_estimators": 800,
        "nthread": 4,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "early_stopping_rounds": 50,
    },
    "catboost": {
        "learning_rate": 0.03,
        "depth": 8,
        "iterations": 800,
        "thread_count": 4,
        "subsample": 0.8,
        "l2_leaf_reg": 3,
        "early_stopping_rounds": 50,
        "task_type": "CPU",
    },
    "lstm": {
        "n_epochs": 100,
        "batch_size": 2000,
        "lr": 0.001,
        "d_feat": 158,
        "hidden_size": 64,
        "num_layers": 2,
        "dropout": 0.0,
        "GPU": 0,
    },
    "gru": {
        "n_epochs": 100,
        "batch_size": 2000,
        "lr": 0.001,
        "d_feat": 158,
        "hidden_size": 64,
        "num_layers": 2,
        "dropout": 0.0,
        "GPU": 0,
    },
    "transformer": {
        "n_epochs": 100,
        "batch_size": 2000,
        "lr": 0.001,
        "d_feat": 158,
        "nhead": 2,
        "hidden_size": 64,
        "num_layers": 2,
        "dropout": 0.0,
        "GPU": 0,
    },
}


class QlibModelManager:
    def __init__(self):
        init_qlib()

    @classmethod
    def list_models(cls):
        return list(SUPPORTED_MODELS.keys())

    def _build_task_config(
        self, model_name, factor_set, instruments, train_period, valid_period, test_period, model_params=None
    ):
        """构造 qlib 任务配置字典"""
        from qlib_integration.config import init_qlib
        init_qlib()

        class_name, module_path = SUPPORTED_MODELS[model_name]
        params = {**DEFAULT_PARAMS.get(model_name, {}), **(model_params or {})}

        return {
            "model": {
                "class": class_name,
                "module_path": module_path,
                "kwargs": params,
            },
            "dataset": {
                "class": "DatasetH",
                "module_path": "qlib.data.dataset",
                "kwargs": {
                    "handler": {
                        "class": factor_set,
                        "module_path": "qlib.contrib.data.handler",
                        "kwargs": {
                            "instruments": instruments,
                            "start_time": train_period[0],
                            "end_time": test_period[1],
                            "fit_start_time": train_period[0],
                            "fit_end_time": train_period[1],
                        },
                    },
                    "segments": {
                        "train": train_period,
                        "valid": valid_period,
                        "test": test_period,
                    },
                },
            },
        }

    def train(
        self, model_name, factor_set, instruments,
        train_period, valid_period, test_period,
        model_params=None, experiment_name="a_share_quant",
    ):
        """
        训练模型并返回结果

        Parameters
        ----------
        model_name : str — SUPPORTED_MODELS 中的 key
        factor_set : str — "Alpha158" 或 "Alpha360"
        instruments : str — "csi300", "csi500", "all"
        train_period : tuple — ("2018-01-01", "2021-12-31")
        valid_period : tuple — ("2022-01-01", "2022-12-31")
        test_period : tuple — ("2023-01-01", "2024-12-31")
        model_params : dict — 覆盖默认参数
        experiment_name : str — MLflow 实验名称

        Returns
        -------
        dict with keys: model, predictions, ic, ric, metrics
        """
        from qlib.utils import init_instance_by_config, flatten_dict
        from qlib.workflow import R
        from qlib.workflow.record_temp import SignalRecord, SigAnaRecord

        task_config = self._build_task_config(
            model_name, factor_set, instruments,
            train_period, valid_period, test_period, model_params,
        )

        result = {}

        with R.start(experiment_name=experiment_name):
            R.log_params(**flatten_dict(task_config))

            model = init_instance_by_config(task_config["model"])
            dataset = init_instance_by_config(task_config["dataset"])

            model.fit(dataset)
            R.save_objects(**{"params.pkl": model})

            recorder = R.get_recorder()
            sr = SignalRecord(model, dataset, recorder)
            sr.generate()

            sar = SigAnaRecord(recorder)
            sar.generate()

            pred = sr.load("pred.pkl")
            label = sr.load("label.pkl")
            ic = sar.load("ic.pkl")
            ric = sar.load("ric.pkl")

            ic_mean = float(ic.mean()) if ic is not None else None
            ic_std = float(ic.std()) if ic is not None else 0
            icir = ic_mean / ic_std if ic_std > 0 else None

            result = {
                "model": model,
                "predictions": pred,
                "label": label,
                "ic": ic,
                "ric": ric,
                "ic_mean": ic_mean,
                "icir": icir,
            }

        return result

    def predict(self, model, dataset_config):
        """使用已训练模型生成预测"""
        from qlib.utils import init_instance_by_config

        dataset = init_instance_by_config(dataset_config)
        return model.predict(dataset)

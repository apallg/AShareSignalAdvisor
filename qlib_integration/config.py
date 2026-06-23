"""
qlib 初始化封装 — 懒加载，线程安全，环境变量预设
"""
import os
import threading

_initialized = False
_lock = threading.Lock()


def init_qlib():
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return

        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

        import qlib
        from qlib.constant import REG_CN
        import config as app_config

        qlib.init(
            provider_uri=app_config.QLIB_PROVIDER_URI,
            region=REG_CN,
            n_jobs=1,
            joblib_backend="threading",  # Windows pipe 限制，用线程代替进程
            exp_manager={
                "class": "MLflowExpManager",
                "module_path": "qlib.workflow.expm",
                "kwargs": {
                    "uri": app_config.QLIB_MLFLOW_URI,
                    "default_exp_name": app_config.QLIB_EXPERIMENT_NAME,
                },
            },
        )
        _initialized = True

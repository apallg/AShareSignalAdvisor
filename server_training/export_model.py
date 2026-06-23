"""
模型导出脚本
从 mlruns 中找到最佳模型，打包为可移植格式

用法:
  python export_model.py --run-id <run_id> --output ./export
  python export_model.py --best  # 自动选择 ICIR 最高的
"""
import os
import sys
import json
import pickle
import shutil
import argparse
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import config as app_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("export")


def find_best_run():
    mlruns_dir = Path(app_config.QLIB_MLFLOW_URI.replace("file:", "").replace("file:///", ""))
    if not mlruns_dir.exists():
        mlruns_dir = Path("mlruns")

    best_score = -999
    best_run_id = None
    best_exp_dir = None

    for exp_dir in mlruns_dir.iterdir():
        if not exp_dir.is_dir() or not (exp_dir / "meta.yaml").exists():
            continue
        for run_dir in exp_dir.iterdir():
            if not run_dir.is_dir():
                continue
            metrics_dir = run_dir / "metrics"
            if not metrics_dir.exists():
                continue
            for metric_file in metrics_dir.iterdir():
                name = metric_file.name.lower()
                if "icir" in name or ("ic." in name and "mean" in name):
                    try:
                        val = float(metric_file.read_text().strip().split()[1])
                        if val > best_score:
                            best_score = val
                            best_run_id = run_dir.name
                            best_exp_dir = exp_dir
                    except (ValueError, IndexError):
                        continue

    if best_run_id:
        logger.info(f"最佳模型: {best_run_id}, 指标值={best_score}")
    return best_run_id, best_score


def find_run_dir(run_id):
    mlruns_dir = Path(app_config.QLIB_MLFLOW_URI.replace("file:", "").replace("file:///", ""))
    if not mlruns_dir.exists():
        mlruns_dir = Path("mlruns")
    for exp_dir in mlruns_dir.iterdir():
        run_dir = exp_dir / run_id
        if run_dir.exists():
            return run_dir
    return None


def export_model(run_id, output_dir):
    run_dir = find_run_dir(run_id)
    if not run_dir:
        logger.error(f"找不到 run: {run_id}")
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_src = run_dir / "artifacts" / "params.pkl"
    if not model_src.exists():
        logger.error(f"找不到模型文件: {model_src}")
        return None

    shutil.copy2(model_src, output_dir / "params.pkl")
    logger.info(f"已复制模型: {model_src}")

    # 提取配置
    params_dir = run_dir / "params"
    config = {}
    if params_dir.exists():
        for param_file in params_dir.iterdir():
            config[param_file.name] = param_file.read_text().strip()

    # 读取指标
    metrics = {}
    metrics_dir = run_dir / "metrics"
    if metrics_dir.exists():
        for mf in metrics_dir.iterdir():
            try:
                parts = mf.read_text().strip().split()
                if len(parts) >= 2:
                    metrics[mf.name] = float(parts[1])
            except (ValueError, IndexError):
                pass

    model_info = {
        "export_time": datetime.now().isoformat(),
        "run_id": run_id,
        "model_class": config.get("model.class", "unknown"),
        "model_module": config.get("model.module_path", "unknown"),
        "factor_set": config.get("dataset.kwargs.handler.class", "Alpha158"),
        "instruments": config.get("dataset.kwargs.handler.kwargs.instruments", "all"),
        "train_start": config.get("dataset.kwargs.handler.kwargs.fit_start_time", "2012-01-01"),
        "train_end": config.get("dataset.kwargs.handler.kwargs.fit_end_time", "2024-12-31"),
        "hyperparams": {k: v for k, v in config.items() if k.startswith("model.kwargs.")},
        "metrics": metrics,
        "qlib_version": "0.9.7",
    }

    try:
        import torch
        model_info["torch_version"] = torch.__version__
    except ImportError:
        model_info["torch_version"] = None

    with open(output_dir / "model_config.json", "w", encoding="utf-8") as f:
        json.dump(model_info, f, ensure_ascii=False, indent=2)

    # model_card.md
    metrics_md = "\n".join(f"| {k} | {v} |" for k, v in metrics.items())
    model_card = f"""---
language: zh
tags:
- qlib
- stock-prediction
- a-share
- {model_info['model_class']}
---

# A股量化预测模型

- **模型**: {model_info['model_class']}
- **因子集**: {model_info['factor_set']}
- **股票池**: {model_info['instruments']}
- **训练周期**: {model_info['train_start']} ~ {model_info['train_end']}
- **训练平台**: GPU 服务器
- **导出时间**: {model_info['export_time']}

## 性能指标

| 指标 | 值 |
|------|-----|
{metrics_md}

## 使用方法

```python
import qlib
from qlib.constant import REG_CN
import pickle

qlib.init(provider_uri='data/qlib_data', region=REG_CN)

with open('params.pkl', 'rb') as f:
    model = pickle.load(f)
```
"""
    with open(output_dir / "model_card.md", "w", encoding="utf-8") as f:
        f.write(model_card)

    # requirements.txt
    reqs = [
        f"pyqlib=={model_info['qlib_version']}",
        "mlflow>=2.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "scipy>=1.7.0",
        "lightgbm",
        "xgboost",
        "scikit-learn",
    ]
    if model_info.get("torch_version"):
        reqs.append(f"torch=={model_info['torch_version']}")
    with open(output_dir / "requirements.txt", "w") as f:
        f.write("\n".join(reqs))

    # 打包
    archive_name = f"model_{run_id[:12]}"
    archive_path = output_dir.parent / archive_name
    shutil.make_archive(str(archive_path), "gztar", root_dir=str(output_dir))

    logger.info(f"导出完成: {output_dir}")
    logger.info(f"压缩包: {archive_path}.tar.gz")
    return output_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", help="MLflow run ID")
    parser.add_argument("--best", action="store_true", help="自动选择 ICIR 最高的模型")
    parser.add_argument("--output", default="./export/best_model")
    args = parser.parse_args()

    run_id = args.run_id
    if args.best:
        run_id, score = find_best_run()
        if not run_id:
            logger.error("未找到任何模型，请先运行训练")
            return
    elif not run_id:
        logger.error("请指定 --run-id 或 --best")
        return

    export_model(run_id, args.output)


if __name__ == "__main__":
    main()

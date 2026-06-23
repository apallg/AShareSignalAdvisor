"""
本地推理脚本
加载服务器训练的模型，对指定股票/全市场进行预测

用法:
  python inference.py --model ./model --codes 000001,600519 --start 2026-06-01 --end 2026-06-23
  python inference.py --model ./model --all --top 20
"""
import os
import sys
import json
import pickle
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

import qlib
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config

import config as app_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inference")


def load_model(model_dir):
    model_dir = Path(model_dir)
    config_path = model_dir / "model_config.json"
    model_path = model_dir / "params.pkl"

    if not config_path.exists():
        raise FileNotFoundError(f"找不到 model_config.json: {config_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"找不到 params.pkl: {model_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        model_config = json.load(f)

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    logger.info(f"模型已加载: {model_config['model_class']} ({model_config['model_module']})")
    return model, model_config


def predict(model, model_config, codes, start, end):
    from qlib_integration.config import init_qlib
    init_qlib()

    factor_set = model_config.get("factor_set", "Alpha158")

    if codes:
        qlib_codes = []
        for c in codes:
            mkt = "sh" if c.startswith(("6", "5")) else "sz"
            qlib_codes.append(f"{mkt}{c}")
        instruments = ",".join(qlib_codes)
    else:
        instruments = "all"

    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": {
                "class": factor_set,
                "module_path": "qlib.contrib.data.handler",
                "kwargs": {
                    "instruments": instruments,
                    "start_time": start,
                    "end_time": end,
                    "fit_start_time": start,
                    "fit_end_time": end,
                },
            },
            "segments": {"test": (start, end)},
        },
    }

    logger.info(f"预测 {len(codes) if codes else '全市场'} 只股票, {start} ~ {end}")
    dataset = init_instance_by_config(dataset_config)
    predictions = model.predict(dataset)

    # predictions is pd.Series with MultiIndex (datetime, instrument)
    df = predictions.reset_index()
    df.columns = ["datetime", "instrument", "score"]
    df = df.sort_values("score", ascending=False)

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="模型目录路径")
    parser.add_argument("--codes", help="股票代码，逗号分隔，如 '000001,600519'")
    parser.add_argument("--all", action="store_true", help="全市场预测")
    parser.add_argument("--top", type=int, default=20, help="输出 Top N")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-06-23")
    parser.add_argument("--output", help="输出 CSV 路径")
    args = parser.parse_args()

    model, model_config = load_model(args.model)

    codes = None
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    elif not args.all:
        parser.error("请指定 --codes 或 --all")

    df = predict(model, model_config, codes, args.start, args.end)

    print(f"\n{'='*60}")
    print(f"Top {args.top} 预测结果:")
    print(f"{'='*60}")
    print(df.head(args.top).to_string(index=False))

    if args.output:
        df.to_csv(args.output, index=False)
        logger.info(f"已保存到: {args.output}")

    return df


if __name__ == "__main__":
    main()

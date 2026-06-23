# 服务器模型训练与部署完整指南

> 目标：租用 4090 服务器 → 拉取全量 A 股数据 → 训练最优模型 → 上传 HuggingFace → 本地拉取预测

---

## 目录

- [1. 服务器环境搭建](#1-服务器环境搭建)
- [2. 数据采集](#2-数据采集)
- [3. 模型训练](#3-模型训练)
- [4. 模型评估与选优](#4-模型评估与选优)
- [5. 模型打包导出](#5-模型打包导出)
- [6. 上传 HuggingFace](#6-上传-huggingface)
- [7. 本地推理](#7-本地推理)
- [8. 常见问题](#8-常见问题)

---

## 1. 服务器环境搭建

### 1.1 基础环境

```bash
# SSH 登录后
sudo apt update && sudo apt upgrade -y

# CUDA 环境（4090 需要 CUDA 12.x）
# 推荐用 NVIDIA 官方脚本一键安装
wget https://developer.download.nvidia.com/compute/cuda/12.4.0/local_installers/cuda_12.4.0_550.54.14_linux.run
sudo sh cuda_12.4.0_550.54.14_linux.run

# 验证 CUDA
nvidia-smi
# 应显示: NVIDIA GeForce RTX 4090, 24GB VRAM

# 安装基础工具
sudo apt install -y git build-essential mysql-server-8.0

# 启动 MySQL
sudo systemctl start mysql
sudo systemctl enable mysql

# 设置 root 密码
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'qilin123'; FLUSH PRIVILEGES;"
```

### 1.2 Python 环境

```bash
# 安装 Python 3.11
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装 PyTorch（CUDA 12.4 版本）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 验证 PyTorch 能看到 GPU
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
# 输出: True / NVIDIA GeForce RTX 4090

# 安装 Qlib 和其他依赖
pip install pyqlib mlflow scikit-learn lightgbm xgboost catboost
pip install pandas numpy scipy requests pymysql cryptography python-dotenv
pip install akshare baostock

# 验证 Qlib 安装
python -c "import qlib; print(qlib.__version__)"
```

### 1.3 克隆项目

```bash
git clone https://github.com/你的账号/中国A股量化软件.git
cd 中国A股量化软件

# 创建 .env
cat > .env << 'EOF'
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=qilin123
MYSQL_DATABASE=qilin_stock
QLIB_ENABLED=true
EOF
```

### 1.4 初始化数据库

```bash
mysql -u root -pqilin123 < db/setup.sql
mysql -u root -pqilin123 -e "USE qilin_stock; SHOW TABLES;"
```

---

## 2. 数据采集

### 2.1 全量采集（首次）

```bash
# 混合模式：腾讯 3 分钟 + BaoStock 补全（约 50 分钟）
python scripts/fast_collect.py --source hybrid --workers 64

# 同步到 Qlib 二进制格式
python -c "
from qlib_integration.bridge import QlibDataBridge
import config
bridge = QlibDataBridge(config.QLIB_DATA_DIR)
result = bridge.sync_all()
print(result)
"
```

预计产出：
- `data/qlib_data/calendars/day.txt` — 交易日历
- `data/qlib_data/instruments/all.txt` — 股票列表
- `data/qlib_data/features/sh000001/` — 每只股票 7 个字段的 `.day.bin` 文件
- 约 5000 只股票，日期从 2012-01-01 到 2026-06-23

### 2.2 验证数据完整性

```bash
python -c "
from qlib_integration.bridge import QlibDataBridge
import config
status = QlibDataBridge(config.QLIB_DATA_DIR).get_status()
print(status)
# {'synced': True, 'dates': ~3500, 'stocks': ~5000, 'first_date': '...', 'last_date': '...'}
"

# 检查 amount 不为 0（确保不是腾讯残缺数据）
mysql -u root -pqilin123 -e "
  SELECT 'amount_zero' as check_type, COUNT(*) as cnt FROM qilin_stock.daily_quotes WHERE amount = 0;
  SELECT 'total_rows' as check_type, COUNT(*) FROM qilin_stock.daily_quotes;
"
# amount=0 应该只有近期 640 天 × 5000 只 ≈ 320 万条，其余应该有真实值
```

### 2.3 后续增量更新

```bash
# 日常只需跑腾讯源（3 分钟）
python scripts/fast_collect.py --source tencent --workers 64
# 会自动同步 qlib（除非加 --no-sync）
```

---

## 3. 模型训练

### 3.1 训练脚本

创建 `scripts/train_on_server.py`：

```python
"""
4090 服务器模型训练脚本
按顺序训练 LightGBM → ALSTM → TRA，记录指标，选出最佳模型

用法:
  python scripts/train_on_server.py                    # 训练全部 3 个模型
  python scripts/train_on_server.py --models lightgbm   # 只训练 LightGBM
  python scripts/train_on_server.py --skip-sync          # 跳过数据采集步骤
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

# 环境变量
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

# ─── 模型配置 ───────────────────────────────────────────

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
            "test":  ("2026-01-01", "2026-06-23"),
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
}


def init():
    """初始化 qlib"""
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
    """训练单个模型，返回指标"""
    logger.info(f"{'='*60}")
    logger.info(f"开始训练: {model_name}")
    logger.info(f"{'='*60}")

    task_config = {
        "model": model_config,
        "dataset": dataset_config,
    }

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

        # 提取指标
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

    # 清理 GPU 缓存
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["lightgbm", "alstm", "tra"],
                        choices=["lightgbm", "alstm", "tra", "xgboost", "gru", "transformer", "tcn"])
    parser.add_argument("--skip-sync", action="store_true")
    args = parser.parse_args()

    init()

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

    # 汇总
    logger.info(f"\n{'='*60}")
    logger.info("训练汇总")
    logger.info(f"{'='*60}")
    for r in sorted(results, key=lambda x: x.get("ICIR") or 0, reverse=True):
        logger.info(f"  {r['model']:12s}  IC={r['IC']}  ICIR={r['ICIR']}  "
                    f"Rank_IC={r['Rank_IC']}  耗时={r['train_time']}s")

    # 保存结果
    with open("training_results.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("结果已保存到 training_results.json")


if __name__ == "__main__":
    main()
```

### 3.2 运行训练

```bash
# 在服务器项目根目录执行
source venv/bin/activate

# 训练全部 3 个模型（推荐）
nohup python scripts/train_on_server.py > training_output.log 2>&1 &

# 监控进度
tail -f training_output.log

# 或者先快速验证 LightGBM
python scripts/train_on_server.py --models lightgbm
```

### 3.3 模型说明

| 模型 | 架构 | GPU 使用 | 预计耗时 | 适用场景 |
|------|------|---------|---------|---------|
| LightGBM | 梯度提升树 | CPU 多线程 | ~10 min | 稳健基线，不需要 GPU |
| ALSTM | LSTM + 注意力机制 | GPU ~2-3GB | ~30-60 min | Qlib 论文验证最佳，A 股效果好 |
| TRA | RNN + 时序路由适配器 | GPU ~5-8GB | ~1-2 h | NeurIPS 2022，多交易模式自适应 |

### 3.4 超参数调优（可选）

如果时间和 GPU 允许，可以对最佳模型做网格搜索：

```python
# 在 train_on_server.py 末尾追加
def grid_search_alstm():
    """ALSTM 超参数网格搜索"""
    hparams = {
        "hidden_size": [64, 128, 256],
        "num_layers": [1, 2, 3],
        "dropout": [0.0, 0.1, 0.2],
        "lr": [0.01, 0.001, 0.0001],
    }
    best_icir = -999
    best_config = None

    for hs in hparams["hidden_size"]:
        for nl in hparams["num_layers"]:
            for dr in hparams["dropout"]:
                for lr in hparams["lr"]:
                    config = MODELS["alstm"].copy()
                    config["kwargs"].update({
                        "hidden_size": hs, "num_layers": nl,
                        "dropout": dr, "lr": lr,
                    })
                    try:
                        r = train_one_model(f"alstm_h{hs}_l{nl}_d{dr}_lr{lr}",
                                           config, DATASET_CONFIG)
                        if r["ICIR"] and r["ICIR"] > best_icir:
                            best_icir = r["ICIR"]
                            best_config = config
                    except Exception:
                        continue

    logger.info(f"最佳 ALSTM: ICIR={best_icir}, config={best_config}")
```

---

## 4. 模型评估与选优

### 4.1 指标解读

打开 `training_results.json`：

```json
[
  {
    "model": "lightgbm",
    "train_time": 612.3,
    "IC": 0.034512,
    "ICIR": 0.452100,
    "Rank_IC": 0.041230,
    "run_id": "abc123def456"
  },
  ...
]
```

| 指标 | 含义 | 优秀 | 良好 | 一般 |
|------|------|------|------|------|
| IC | 预测值与真实收益的相关系数 | > 0.05 | 0.03-0.05 | < 0.03 |
| ICIR | IC 均值 / IC 标准差（稳定性） | > 0.5 | 0.3-0.5 | < 0.3 |
| Rank_IC | 排序相关系数（更稳健） | > 0.05 | 0.03-0.05 | < 0.03 |

选择 **ICIR 最高** 的模型作为最终模型。

### 4.2 回测验证（可选）

```python
# 在训练完成后运行回测
from qlib_integration.backtest import QlibBacktestRunner

runner = QlibBacktestRunner()
bt_result = runner.run(
    model=best_model,
    topk=50,
    n_drop=5,
    start="2026-01-01",
    end="2026-06-23",
)
print(bt_result)
```

---

## 5. 模型打包导出

创建 `scripts/export_model.py`：

```python
"""
模型导出脚本
从 mlruns 中找到最佳模型，打包为可移植格式

用法:
  python scripts/export_model.py --run-id <run_id> --output ./export
  python scripts/export_model.py --best  # 自动选择 ICIR 最高的
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
    """找到 mlruns 中 ICIR 最高的 run"""
    mlruns_dir = Path(app_config.QLIB_MLFLOW_URI.replace("file:", "").replace("file:///", ""))
    if not mlruns_dir.exists():
        # fallback
        mlruns_dir = Path("mlruns")

    best_icir = -999
    best_run_id = None

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
                if "ICIR" in metric_file.name or "icir" in metric_file.name:
                    val = float(metric_file.read_text().strip().split()[1])
                    if val > best_icir:
                        best_icir = val
                        best_run_id = run_dir.name
                elif "IC.mean" in metric_file.name or "ic.mean" in metric_file.name:
                    val = float(metric_file.read_text().strip().split()[1])
                    if val > best_icir:
                        best_icir = val
                        best_run_id = run_dir.name

    if best_run_id:
        logger.info(f"最佳模型: {best_run_id}, ICIR={best_icir}")
    return best_run_id, best_icir


def find_run_dir(run_id):
    """根据 run_id 查找完整路径"""
    mlruns_dir = Path(app_config.QLIB_MLFLOW_URI.replace("file:", "").replace("file:///", ""))
    if not mlruns_dir.exists():
        mlruns_dir = Path("mlruns")
    for exp_dir in mlruns_dir.iterdir():
        run_dir = exp_dir / run_id
        if run_dir.exists():
            return run_dir
    return None


def export_model(run_id, output_dir):
    """导出模型到指定目录"""
    run_dir = find_run_dir(run_id)
    if not run_dir:
        logger.error(f"找不到 run: {run_id}")
        return

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 复制 params.pkl
    model_src = run_dir / "artifacts" / "params.pkl"
    if model_src.exists():
        shutil.copy2(model_src, output_dir / "params.pkl")
        logger.info(f"已复制模型: {model_src}")
    else:
        logger.error(f"找不到模型文件: {model_src}")
        return

    # 2. 提取配置
    params_dir = run_dir / "params"
    config = {}
    for param_file in params_dir.iterdir():
        key = param_file.name
        value = param_file.read_text().strip()
        config[key] = value

    # 3. 收集关键信息
    model_info = {
        "export_time": datetime.now().isoformat(),
        "run_id": run_id,
        "model_class": config.get("model.class", "unknown"),
        "model_module": config.get("model.module_path", "unknown"),
        "factor_set": config.get("dataset.kwargs.handler.class", "Alpha158"),
        "instruments": config.get("dataset.kwargs.handler.kwargs.instruments", "all"),
        "train_period": [config.get("dataset.kwargs.segments.train", "")],
        "hyperparams": {k: v for k, v in config.items() if k.startswith("model.kwargs.")},
        "qlib_version": "0.9.7",
        "torch_version": __import__("torch").__version__ if config.get("model.module_path", "").startswith("qlib.contrib.model.pytorch") else None,
    }

    with open(output_dir / "model_config.json", "w", encoding="utf-8") as f:
        json.dump(model_info, f, ensure_ascii=False, indent=2)

    # 4. 生成 model_card.md
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
- **训练周期**: {model_info['train_period']}
- **训练平台**: 4090 GPU 服务器
- **导出时间**: {model_info['export_time']}
- **Qlib 版本**: {model_info['qlib_version']}

## 使用方法

```python
import qlib
from qlib.constant import REG_CN
import pickle

qlib.init(provider_uri='data/qlib_data', region=REG_CN)

with open('params.pkl', 'rb') as f:
    model = pickle.load(f)

# 需要构造 DatasetH 进行预测，参见 model_config.json
```

## 性能指标

| 指标 | 值 |
|------|-----|
| IC | - |
| ICIR | - |
| Rank IC | - |
"""
    with open(output_dir / "model_card.md", "w", encoding="utf-8") as f:
        f.write(model_card)

    # 5. 生成 requirements.txt
    reqs = f"""pyqlib=={model_info['qlib_version']}
mlflow>=2.0.0
pandas>=2.0.0
numpy>=1.24.0
scipy>=1.7.0
"""
    if model_info.get("torch_version"):
        reqs += f"torch=={model_info['torch_version']}\n"
    reqs += "lightgbm\nxgboost\n"
    with open(output_dir / "requirements.txt", "w") as f:
        f.write(reqs)

    # 6. 打包
    archive_name = f"model_{run_id[:12]}.tar.gz"
    shutil.make_archive(
        str(output_dir.parent / archive_name.replace(".tar.gz", "")),
        "gztar",
        root_dir=str(output_dir),
    )

    logger.info(f"导出完成: {output_dir}")
    logger.info(f"压缩包: {output_dir.parent / archive_name}")
    return output_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", help="MLflow run ID")
    parser.add_argument("--best", action="store_true", help="自动选择 ICIR 最高的模型")
    parser.add_argument("--output", default="./export/best_model")
    args = parser.parse_args()

    if args.best:
        run_id, icir = find_best_run()
        if not run_id:
            logger.error("未找到任何模型")
            return
    elif args.run_id:
        run_id = args.run_id
    else:
        logger.error("请指定 --run-id 或 --best")
        return

    export_model(run_id, args.output)


if __name__ == "__main__":
    main()
```

---

## 6. 上传 HuggingFace

### 6.1 准备

```bash
pip install huggingface_hub

# 登录（需要先在 huggingface.co 注册并创建 Access Token）
huggingface-cli login
# 粘贴你的 token
```

创建 `scripts/upload_model.py`：

```python
"""
上传模型到 HuggingFace Hub

用法:
  python scripts/upload_model.py --model-dir ./export/best_model --repo apallg/a-share-model
  python scripts/upload_model.py --best --repo apallg/a-share-model
"""
import argparse
import logging
from pathlib import Path
from huggingface_hub import HfApi, create_repo, upload_folder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("upload")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default="./export/best_model", help="模型目录")
    parser.add_argument("--repo", required=True, help="HuggingFace 仓库名，如 apallg/a-share-model")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        logger.error(f"目录不存在: {model_dir}")
        return

    # 创建仓库
    create_repo(args.repo, private=args.private, exist_ok=True)
    logger.info(f"仓库: https://huggingface.co/{args.repo}")

    # 上传
    upload_folder(
        folder_path=str(model_dir),
        repo_id=args.repo,
        commit_message=f"Upload model from 4090 server",
    )
    logger.info("上传完成!")


if __name__ == "__main__":
    main()
```

### 6.2 上传

```bash
# 导出最佳模型并上传
python scripts/export_model.py --best --output ./export/best_model
python scripts/upload_model.py --model-dir ./export/best_model --repo 你的账号/quant-china-a-share
```

---

## 7. 本地推理

### 7.1 下载模型

```bash
# 方式1: git clone
git lfs install
git clone https://huggingface.co/你的账号/quant-china-a-share

# 方式2: Python
python -c "from huggingface_hub import snapshot_download; snapshot_download('你的账号/quant-china-a-share', local_dir='./model')"
```

### 7.2 本地推理脚本

创建 `scripts/inference.py`：

```python
"""
本地推理脚本
加载服务器训练的模型，对指定股票/全市场进行预测

用法:
  python scripts/inference.py --model ./model --codes 000001,600519 --start 2026-06-01 --end 2026-06-23
  python scripts/inference.py --model ./model --all --top 20
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

import pandas as pd
import qlib
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config
from qlib.data import D

import config as app_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inference")


def load_model(model_dir):
    """加载导出的模型"""
    model_dir = Path(model_dir)
    config_path = model_dir / "model_config.json"
    model_path = model_dir / "params.pkl"

    with open(config_path, "r", encoding="utf-8") as f:
        model_config = json.load(f)

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    logger.info(f"模型已加载: {model_config['model_class']}")
    return model, model_config


def predict(model, model_config, codes, start, end):
    """对指定股票进行预测"""
    from qlib_integration.config import init_qlib
    init_qlib()

    factor_set = model_config["factor_set"]

    if codes:
        # 转换代码格式: 000001 → sz000001
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

    dataset = init_instance_by_config(dataset_config)
    predictions = model.predict(dataset)

    # predictions 是 pd.Series，index 是 (datetime, instrument)
    df = predictions.reset_index()
    df.columns = ["datetime", "instrument", "score"]
    df = df.sort_values("score", ascending=False)

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="模型目录")
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

    logger.info(f"预测 {len(codes) if codes else '全市场'} 只股票, "
                f"时间 {args.start} ~ {args.end}")

    df = predict(model, model_config, codes, args.start, args.end)

    # 输出 Top N
    print(f"\n{'='*60}")
    print(f"Top {args.top} 预测结果:")
    print(f"{'='*60}")
    print(df.head(args.top).to_string(index=False))

    if args.output:
        df.to_csv(args.output, index=False)
        logger.info(f"已保存: {args.output}")

    return df


if __name__ == "__main__":
    main()
```

### 7.3 运行推理

```bash
# 单只股票预测
python scripts/inference.py --model ./model --codes 000001 --start 2026-06-20 --end 2026-06-23

# 全市场 Top 20
python scripts/inference.py --model ./model --all --top 20 --output predictions.csv

# 指定多只股票
python scripts/inference.py --model ./model --codes "000001,600519,000858,601318"
```

---

## 8. 常见问题

### Q: 训练 OOM（显存不足）怎么办？

```python
# 减小 batch_size
"batch_size": 2048,  # 从 4096 降到 2048
# 减小 hidden_size
"hidden_size": 64,   # 从 128 降到 64
# 减少 num_layers
"num_layers": 1,     # 从 2 降到 1
```

### Q: 训练太慢？

```python
# 缩小股票池
"instruments": "csi300",  # 从 all 改为 csi300（300 只）
# 减少 epochs
"n_epochs": 100,
# 或只训练 LightGBM + ALSTM，跳过 TRA
```

### Q: 本地加载模型报错 "No module named 'qlib.contrib.model.xxx'"？

```bash
# 确保本地也装了 pyqlib
pip install pyqlib==0.9.7

# PyTorch 模型还需要 torch
pip install torch
```

### Q: 预测结果全是 NaN？

检查 `qlib_data` 目录结构是否正确：
```bash
ls data/qlib_data/calendars/day.txt
ls data/qlib_data/instruments/all.txt
ls data/qlib_data/features/sh600000/
```

### Q: LightGBM vs ALSTM vs TRA 怎么选？

- **稳健优先**：LightGBM（不依赖 GPU，最快，最稳定）
- **A 股历史验证最佳**：ALSTM（LSTM + 注意力，Qlib 官方推荐）
- **追求 SOTA**：TRA（2022 年最新，多交易模式自适应，但训练最慢）

---

## 完整流程图

```
服务器 (4090)
│
├── 1. 环境搭建 (30min)
│   ├── CUDA 12.4 + PyTorch
│   ├── MySQL 8.0
│   └── pip install pyqlib + 依赖
│
├── 2. 数据采集 (1h)
│   ├── fast_collect.py --source hybrid  →  MySQL
│   └── QlibDataBridge.sync_all()  →  data/qlib_data/
│
├── 3. 模型训练 (1-3h)
│   ├── LightGBM  (~10min)
│   ├── ALSTM     (~30-60min)
│   └── TRA       (~1-2h)
│
├── 4. 导出 (5min)
│   └── export_model.py --best  →  export/best_model/
│
└── 5. 上传 (5min)
    └── upload_model.py  →  HuggingFace Hub

═══════════════════════════════════════

本地
│
├── git clone https://huggingface.co/xxx/model
├── python scripts/inference.py --model ./model --all --top 20
└── 结果用于前端展示 / 回测 / 实盘信号
```

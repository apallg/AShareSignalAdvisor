# 服务器部署与模型训练流程

## 1. 服务器选型建议

| 用途 | 推荐配置 | 参考价格 |
|------|---------|---------|
| 纯数据采集 | 2C4G, 50G SSD | ~50元/月 |
| 模型训练 (LightGBM) | 4C8G, 100G SSD | ~100-200元/月 |
| 模型训练 (深度学习) | 8C16G + GPU, 200G SSD | ~500元+/月 |

优先选**国内机房**（阿里云/腾讯云/华为云），访问腾讯/新浪/BaoStock 接口更快。

---

## 2. 环境初始化

```bash
# SSH 登录后，先更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y git build-essential python3.11 python3.11-venv python3.11-dev

# 安装 MySQL 8.0
sudo apt install -y mysql-server-8.0
sudo systemctl start mysql
sudo systemctl enable mysql

# 设置 MySQL root 密码
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '你的密码'; FLUSH PRIVILEGES;"
```

---

## 3. 部署项目

```bash
# 克隆项目
git clone https://github.com/你的账号/中国A股量化软件.git
cd 中国A股量化软件

# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装依赖 (服务器上不需要 pywin32/easytrader/QMT 这些)
pip install pandas numpy scipy requests pymysql cryptography python-dotenv
pip install akshare baostock backtrader ta openpyxl matplotlib
pip install openai diskcache apscheduler pydantic-settings
pip install pyqlib mlflow scikit-learn lightgbm xgboost catboost

# 或者精简安装
grep -v "pywin32\|easytrader\|streamlit\|plotly" requirements.txt > requirements_server.txt
pip install -r requirements_server.txt
```

---

## 4. 配置环境变量

```bash
# 从模板创建 .env
cp .env.example .env

# 编辑 .env，只需要填这几项
vim .env
```

服务器上最小可用的 `.env`：

```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_MODEL=deepseek-chat

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的MySQL密码
MYSQL_DATABASE=qilin_stock

QLIB_ENABLED=true
```

---

## 5. 初始化数据库

```bash
# 创建库和表
mysql -u root -p < db/setup.sql

# 验证
mysql -u root -p -e "USE qilin_stock; SHOW TABLES;"
```

---

## 6. 采集全量数据

```bash
# 混合模式 (推荐): 腾讯3分钟拿近2年 + BaoStock补全2012至今的历史
python scripts/fast_collect.py --source hybrid --workers 64

# 如果只想快速测试
python scripts/fast_collect.py --pool csi300 --source hybrid
```

预计耗时：首次约 50-55 分钟（5000只全量），后续增量约 3 分钟。

---

## 7. 同步 qlib 并训练模型

```bash
# 如果采集时加了 --no-sync，手动同步
python -c "
from qlib_integration.bridge import QlibDataBridge
import config
bridge = QlibDataBridge(config.QLIB_DATA_DIR)
bridge.sync_all()
"
```

### 7.1 通过 API 训练

```bash
# 启动后端
OPENBLAS_NUM_THREADS=1 uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

# 调用训练接口
curl -X POST http://127.0.0.1:8000/api/qlib/models/train \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "lightgbm",
    "factor_set": "Alpha158",
    "stock_pool": "all",
    "train_start": "2012-01-01",
    "train_end": "2024-12-31",
    "valid_start": "2025-01-01",
    "valid_end": "2025-12-31",
    "test_start": "2026-01-01",
    "test_end": "2026-06-23"
  }'

# 查看训练进度
curl http://127.0.0.1:8000/api/qlib/models/train/<job_id>
```

### 7.2 或直接 Python 脚本训练

```bash
python -c "
import config
from qlib_integration.config import init_qlib
from qlib_integration.models import QlibModelManager

init_qlib()
mgr = QlibModelManager()
result = mgr.train(
    model_name='lightgbm',
    factor_set='Alpha158',
    stock_pool='all',
    train_start='2012-01-01',
    train_end='2024-12-31',
    valid_start='2025-01-01',
    valid_end='2025-12-31',
)
print(result)
"
```

---

## 8. 导出训练好的模型

```bash
# mlruns 目录包含所有实验数据，整个打包
tar -czf mlruns_backup.tar.gz mlruns/

# 模型文件在 mlruns/<experiment_id>/<run_id>/artifacts/
# 核心文件是 params.pkl (LightGBM 模型参数)
```

下载回本地：
```bash
# 在本地执行
scp user@服务器IP:~/中国A股量化软件/mlruns_backup.tar.gz .
```

---

## 9. 可选: Docker 一键部署

如果服务器配置高，可以直接 Docker 起全栈：

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER

# 启动
docker-compose up -d
```

但训练模型建议用裸 Python 而非 Docker，因为 Docker 里的 qlib 数据目录挂载和内存限制配置麻烦。

---

## 10. 常用运维命令

```bash
# 后台运行采集，断开 SSH 不中断
nohup python scripts/fast_collect.py --source hybrid > collect.log 2>&1 &

# 后台运行训练
nohup python train.py > train.log 2>&1 &

# 查看日志
tail -f collect.log

# 查看 MySQL 数据量
mysql -u root -p -e "SELECT COUNT(*) as total_rows, COUNT(DISTINCT code) as stocks FROM qilin_stock.daily_quotes;"

# 查看磁盘
df -h
```

---

## 完整流程一览

```
租服务器 → SSH登录 → 装MySQL/Python → clone项目 → 配.env
→ 建库表 → pip install → hybrid采集(50min) → qlib同步
→ 训练模型 → 导出mlruns → scp回本地
```

全程约 1-2 小时（含 50 分钟采集），之后增量维护只需跑一次 3 分钟的腾讯采集 + 同步。

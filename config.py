"""
A股量化软件 - 全局配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 项目路径
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = ROOT_DIR / "cache"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# LLM 提供商配置
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 通义千问
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-turbo")

# Coze 通知 (第二期，备用)
COZE_API_TOKEN = os.getenv("COZE_API_TOKEN", "")
COZE_BASE_URL = os.getenv("COZE_BASE_URL", "https://api.coze.cn")
COZE_BOT_ID = os.getenv("COZE_BOT_ID", "")
COZE_WORKFLOW_ID = os.getenv("COZE_WORKFLOW_ID", "")

# 企业微信机器人通知 (主用)
WECOM_BOT_KEY = os.getenv("WECOM_BOT_KEY", "")

# 缓存有效期 (秒)
CACHE_EXPIRE_DATA = 3600        # 行情数据 1 小时
CACHE_EXPIRE_LLM = 300          # LLM 响应 5 分钟
CACHE_EXPIRE_NAME = 86400       # 股票名称 24 小时
CACHE_EXPIRE_FINANCIAL = 86400  # 财务数据 24 小时

# 数据源配置
REALTIME_SOURCE = "新浪财经 (实时)"  # 实时行情数据源
AUTO_REFRESH_INTERVAL = 5           # 自动刷新间隔(秒)
DEFAULT_SOURCE = "akshare"           # 历史数据/详细数据来源

# MySQL 数据库配置
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "qilin_stock")
MYSQL_ENABLED = bool(MYSQL_PASSWORD and MYSQL_PASSWORD != "your_mysql_password_here")

# QMT / miniQMT 交易配置
BROKER_FAKE = "fake"
BROKER_QMT = "qmt"
BROKER_TYPE = os.getenv("BROKER_TYPE", BROKER_FAKE)
QMT_USERDATA_DIR = os.getenv("QMT_USERDATA_DIR", "D:\\迅投极速交易终端 睿智融科版\\userdata_mini")
QMT_ACCOUNT = os.getenv("QMT_ACCOUNT", "")
QMT_SESSION_ID = int(os.getenv("QMT_SESSION_ID", "123456"))

# 交易日定时扫描
SCAN_MORNING_TIME = os.getenv("SCAN_MORNING_TIME", "09:35")
SCAN_AFTERNOON_TIME = os.getenv("SCAN_AFTERNOON_TIME", "14:55")
SCAN_DEFAULT_THRESHOLD = int(os.getenv("SCAN_DEFAULT_THRESHOLD", "7"))

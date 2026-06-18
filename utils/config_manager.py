"""
配置管理器 - 读取 .env 和用户设置
"""
import json
from pathlib import Path
from typing import Any
import config

_SETTINGS_FILE = config.DATA_DIR / "settings.json"


def load_settings() -> dict:
    """加载用户设置"""
    if _SETTINGS_FILE.exists():
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    return {}


def save_settings(settings: dict):
    """保存用户设置"""
    _SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_api_key_status() -> dict:
    """检查各 API Key 配置状态"""
    return {
        "deepseek": bool(config.DEEPSEEK_API_KEY) and config.DEEPSEEK_API_KEY != "your_deepseek_api_key_here",
        "qwen": bool(config.QWEN_API_KEY) and config.QWEN_API_KEY != "your_qwen_api_key_here",
        "coze": bool(config.COZE_API_TOKEN) and config.COZE_API_TOKEN != "your_coze_api_token_here",
        "active_provider": config.LLM_PROVIDER,
    }

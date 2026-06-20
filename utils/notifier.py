"""Coze 通知模块 - 通过 Coze Workflow API 发送持仓风控告警"""
import json
import logging
from typing import Optional, Dict, Any
 
import config
 
logger = logging.getLogger(__name__)
 
 
class CozeNotifier:
    """Coze Workflow API 推送通知"""
 
    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None,
                 workflow_id: Optional[str] = None, bot_id: Optional[str] = None):
        self.token = token or config.COZE_API_TOKEN
        self.base_url = base_url or config.COZE_BASE_URL
        self.workflow_id = workflow_id or config.COZE_WORKFLOW_ID
        self.bot_id = bot_id or config.COZE_BOT_ID
 
    @property
    def enabled(self) -> bool:
        return bool(self.token and self.workflow_id)
 
    def send_alert(self, stock_name: str, stock_code: str,
                   risk_level: str, risk_score: int,
                   risk_detail: str, suggestion: str,
                   shares: int = 0, cost_price: float = 0) -> bool:
        """发送风控告警到 Coze Workflow"""
        if not self.enabled:
            logger.warning("Coze 未配置，跳过通知")
            return False
 
        import requests
        level_emoji = {"高风险": "🚨", "中风险": "⚠️", "低风险": "ℹ️"}
        emoji = level_emoji.get(risk_level, "🔔")
 
        cost_str = f"¥{cost_price:,.2f}" if cost_price else "未知"
        payload = {
            "workflow_id": self.workflow_id,
            "parameters": {
                "title": f"{emoji}【A股风险预警】",
                "stock_name": stock_name,
                "stock_code": stock_code,
                "shares": str(shares),
                "cost_price": cost_str,
                "risk_level": risk_level,
                "risk_score": str(risk_score),
                "risk_detail": risk_detail,
                "suggestion": suggestion,
                "time": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "bot_id": self.bot_id or "",
        }
 
        try:
            resp = requests.post(
                f"{self.base_url}/v1/workflow/run",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            result = resp.json()
            if resp.ok and result.get("code") == 0:
                logger.info(f"Coze 告警发送成功: {stock_name}({stock_code})")
                return True
            else:
                logger.error(f"Coze 返回错误: {result}")
                return False
        except Exception as e:
            logger.error(f"Coze 通知发送失败: {e}")
            return False
 
    def send_test(self) -> bool:
        """发送测试通知"""
        return self.send_alert(
            stock_name="测试股票", stock_code="000000",
            risk_level="低风险", risk_score=3,
            risk_detail="这是一条来自Apallg投研的测试通知",
            suggestion="如收到此消息，说明 Coze 通知通道已正常工作",
        )
 
 
# 全局单例
_notifier: Optional[CozeNotifier] = None
 
 
def get_notifier() -> CozeNotifier:
    global _notifier
    if _notifier is None:
        _notifier = CozeNotifier()
    return _notifier
 
 
def send_risk_alert(stock_name: str, stock_code: str,
                    risk_level: str, risk_score: int,
                    risk_detail: str, suggestion: str,
                    shares: int = 0, cost_price: float = 0) -> bool:
    """快捷发送风控告警"""
    return get_notifier().send_alert(
        stock_name, stock_code, risk_level, risk_score,
        risk_detail, suggestion, shares, cost_price,
    )

"""信号推送——交易信号生成 + Coze 通知"""
from datetime import datetime

class SignalNotifier:
    def __init__(self):
        self.signals = []
    
    def generate_signal(self, strategy, code, name, action, price, size_ratio, reason):
        signal = {
            "id": f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{code}",
            "strategy": strategy,
            "code": code,
            "name": name,
            "action": action,
            "price": price,
            "size_ratio": size_ratio,
            "reason": reason,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "executed": False,
        }
        self.signals.append(signal)
        return signal
    
    def get_today_signals(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return [s for s in self.signals if s["created_at"].startswith(today)]
    
    def send_coze_alert(self, signal):
        """通过 Coze 推送信号"""
        try:
            from utils.notifier import send_coze_alert
            msg = (f"【交易信号】{signal['action']} {signal['name']}({signal['code']})\n"
                   f"价格: {signal['price']}  仓位: {signal['size_ratio']*100:.0f}%\n"
                   f"策略: {signal['strategy']}\n理由: {signal['reason']}")
            send_coze_alert(msg)
            signal["coze_sent"] = True
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Coze推送失败: {e}")
    
    def get_signals_for_display(self, limit=50):
        return self.signals[-limit:]

SIGNAL_NOTIFIER = SignalNotifier()

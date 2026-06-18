"""情绪因子计算器"""
from datetime import datetime, timedelta

class SentimentFactorCalculator:
    def __init__(self):
        self.windows = [3, 5, 10]
    def calc_daily(self, code, analyzed_items):
        scores = [it["sentiment_score"] for it in analyzed_items if it.get("sentiment_score") is not None]
        if not scores:
            return None
        pos = sum(1 for s in scores if s > 0.1)
        neg = sum(1 for s in scores if s < -0.1)
        n = len(scores)
        return {
            "code": code,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "avg_score": round(sum(scores)/n, 4),
            "pos_ratio": round(pos/n, 4),
            "neg_ratio": round(neg/n, 4),
            "news_count": n,
        }
    def save_daily(self, daily):
        try:
            from core.database import execute_sql
            execute_sql("INSERT INTO sentiment_daily (code,trade_date,avg_score,pos_ratio,neg_ratio,news_count) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                        "avg_score=VALUES(avg_score),pos_ratio=VALUES(pos_ratio),neg_ratio=VALUES(neg_ratio)",
                (daily["code"],daily["date"],daily["avg_score"],daily["pos_ratio"],daily["neg_ratio"],daily["news_count"]))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"save_daily: {e}")
    def get_history(self, code, days=30):
        try:
            from core.database import query_sql
            return query_sql("SELECT * FROM sentiment_daily WHERE code=%s ORDER BY trade_date DESC LIMIT %s", (code,days)) or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"get_history: {e}")
            return []

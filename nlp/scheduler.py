"""定时调度器——定期采集情绪数据"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from .collector import SentimentCollector
from .analyzer import SentimentAnalyzer
from .factor import SentimentFactorCalculator

logger = logging.getLogger(__name__)

class SentimentScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.collector = SentimentCollector()
        self.analyzer = SentimentAnalyzer()
        self.factor = SentimentFactorCalculator()
    def start(self):
        self.scheduler.add_job(self.run_once, "interval", minutes=30, id="sentiment_collect")
        self.scheduler.start()
        logger.info("情绪调度已启动，每30分钟执行一次")
    def run_once(self):
        try:
            from core.database import query_sql
            codes = [r["code"] for r in (query_sql("SELECT DISTINCT code FROM holdings") or [])]
            if not codes:
                return
            logger.info("情绪采集: 开始采集 %d 只股票", len(codes))
            items = self.collector.collect(codes)
            items = self.collector.dedup(items)
            logger.info("情绪采集: 采集到 %d 条新闻", len(items))
            analyzed = self.analyzer.analyze(items)
            self.collector.save_to_db(analyzed)
            for code in codes:
                code_items = [it for it in analyzed if it.get("code")==code]
                if code_items:
                    daily = self.factor.calc_daily(code, code_items)
                    if daily:
                        self.factor.save_daily(daily)
            logger.info("情绪采集: 完成 %s", datetime.now().strftime("%H:%M:%S"))
        except Exception as e:
            logger.warning("sentiment run failed: %s", e)
    def stop(self):
        self.scheduler.shutdown()

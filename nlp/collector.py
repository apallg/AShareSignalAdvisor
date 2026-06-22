"""情绪数据采集器——爬取新浪个股新闻"""
import hashlib
from datetime import datetime
from core.data_sources.scraper.sina_news import SinaNewsScraper

class SentimentCollector:
    def __init__(self):
        self.scraper = SinaNewsScraper(min_interval=2.0)
    def collect(self, codes):
        items = []
        raw = self.scraper.batch_get(codes)
        for code, news in raw.items():
            for item in news:
                item["code"] = code
                item["source"] = "sina_news"
                item["collected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                item["hash"] = hashlib.md5((item["title"]+item.get("date","")).encode()).hexdigest()[:12]
                items.append(item)
        return items
    def collect_single(self, code):
        return self.collect([code])
    def dedup(self, items):
        seen = set()
        return [i for i in items if not (i["hash"] in seen or seen.add(i["hash"]))]
    def save_to_db(self, items):
        try:
            from core.database import execute_sql
            for item in items:
                execute_sql("INSERT IGNORE INTO raw_news (code,title,url,date,source,hash,collected_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (item["code"],item["title"],item["url"],item["date"],item["source"],item["hash"],item["collected_at"]))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"save_to_db: {e}")
    def get_all_latest(self):
        try:
            from core.database import query_sql
            return query_sql("SELECT * FROM raw_news ORDER BY date DESC LIMIT 50") or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"get_all_latest: {e}")
            return []

    def get_latest_news(self, code, limit=20):
        try:
            from core.database import query_sql
            return query_sql("SELECT * FROM raw_news WHERE code=%s ORDER BY date DESC LIMIT %s", (code,limit)) or []
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"get_latest_news: {e}")
            return []

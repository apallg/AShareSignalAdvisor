"""新闻数据 API"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/{code}")
def get_stock_news(code: str, limit: int = 20):
    from nlp.collector import SentimentCollector
    news = SentimentCollector().get_latest_news(code, limit)
    return {"data": news}

@router.get("/{code}/refresh")
def refresh_news(code: str):
    from nlp.collector import SentimentCollector
    from nlp.analyzer import SentimentAnalyzer
    c = SentimentCollector(); a = SentimentAnalyzer()
    items = c.dedup(c.collect_single(code))
    analyzed = a.analyze(items)
    c.save_to_db(analyzed)
    return {"data": {"count": len(analyzed), "code": code}}

@router.get("/latest/list")
def get_latest_news_all(limit: int = 20):
    news = SentimentCollector().get_all_latest()
    return {"data": news[:limit]}

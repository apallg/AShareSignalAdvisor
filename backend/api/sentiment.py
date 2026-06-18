"""情绪数据 API"""
from datetime import datetime, timedelta
from fastapi import APIRouter
router = APIRouter()


@router.get("/{code}")
def get_stock_sentiment(code: str, days: int = 30):
    from nlp.factor import SentimentFactorCalculator
    data = SentimentFactorCalculator().get_history(code, days)
    return {"data": data}


@router.get("/market/overview")
def get_market_sentiment():
    from core.database import Database
    if not Database.is_available():
        return {"data": {"today": {}, "trend": []}}
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    td = Database.fetchall(
        "SELECT AVG(avg_score) as avg_score, SUM(news_count) as total_news, "
        "AVG(pos_ratio) as pos_ratio, AVG(neg_ratio) as neg_ratio "
        "FROM sentiment_daily WHERE trade_date=%s", (today,))
    trend = Database.fetchall(
        "SELECT trade_date as date, AVG(avg_score) as score "
        "FROM sentiment_daily WHERE trade_date>=%s GROUP BY trade_date ORDER BY trade_date", (week_ago,))
    return {"data": {"today": td[0] if td else {}, "trend": trend}}


@router.get("/sectors/rank")
def get_sector_sentiment():
    from core.database import Database
    if not Database.is_available():
        return {"data": []}
    rows = Database.fetchall(
        "SELECT s.sector_name as code, AVG(sd.avg_score) as score "
        "FROM sentiment_daily sd JOIN stock_sectors s ON sd.code=s.code "
        "WHERE sd.trade_date>=DATE_SUB(CURDATE(), INTERVAL 5 DAY) "
        "GROUP BY s.sector_name ORDER BY score DESC LIMIT 20")
    return {"data": rows or []}

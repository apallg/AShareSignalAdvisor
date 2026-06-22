"""
A股交易时间工具：交易日历 / 交易时段判断 / 收盘前窗口
"""
import datetime
import time
import logging
from typing import Optional, Set

logger = logging.getLogger(__name__)

MORNING_START = datetime.time(9, 30)
MORNING_END = datetime.time(11, 30)
AFTERNOON_START = datetime.time(13, 0)
AFTERNOON_END = datetime.time(15, 0)

_trading_dates_cache: Optional[Set[datetime.date]] = None
_cache_updated: Optional[datetime.date] = None


def _build_trading_dates() -> Set[datetime.date]:
    """从 akshare 获取交易日历，失败时使用 weekday 回退"""
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        if df is not None and len(df) > 0:
            col = df.columns[0]
            dates = set()
            for v in df[col]:
                if hasattr(v, "date"):
                    dates.add(v.date())
                else:
                    dates.add(datetime.datetime.strptime(str(v)[:10], "%Y-%m-%d").date())
            logger.info(f"交易日历已加载: {len(dates)} 个交易日 (akshare)")
            return dates
    except Exception as e:
        logger.warning(f"akshare 交易日历获取失败，使用 weekday 回退: {e}")

    today = datetime.date.today()
    dates = set()
    for i in range(-366, 366):
        d = today + datetime.timedelta(days=i)
        if d.weekday() < 5:
            dates.add(d)
    return dates


def _refresh_cache():
    global _trading_dates_cache, _cache_updated
    today = datetime.date.today()
    if _trading_dates_cache is None or _cache_updated != today:
        _trading_dates_cache = _build_trading_dates()
        _cache_updated = today


def is_trading_day(dt: datetime.datetime = None) -> bool:
    """判断是否为 A 股交易日"""
    if dt is None:
        dt = datetime.datetime.now()
    _refresh_cache()
    if hasattr(dt, "date"):
        return dt.date() in _trading_dates_cache
    return dt in _trading_dates_cache


def is_trading_time(dt: datetime.datetime = None) -> bool:
    """判断当前是否在 A 股交易时段内 (9:30-11:30 或 13:00-15:00)"""
    if dt is None:
        dt = datetime.datetime.now()
    if not is_trading_day(dt):
        return False
    t = dt.time()
    return (MORNING_START <= t <= MORNING_END) or (AFTERNOON_START <= t <= AFTERNOON_END)


def is_force_close_window(dt: datetime.datetime = None, force_close_time: str = "14:54") -> bool:
    """判断是否在收盘前强制平仓窗口内 (默认 14:54-15:00)"""
    if dt is None:
        dt = datetime.datetime.now()
    if not is_trading_day(dt):
        return False
    t = dt.time()
    h, m = map(int, force_close_time.split(":"))
    fc = datetime.time(h, m)
    return t >= fc and t <= AFTERNOON_END


def get_trading_session(dt: datetime.datetime = None) -> str:
    """返回当前时段: morning / afternoon / lunch_break / closed / non_trading"""
    if dt is None:
        dt = datetime.datetime.now()
    if not is_trading_day(dt):
        return "non_trading"
    t = dt.time()
    if MORNING_START <= t <= MORNING_END:
        return "morning"
    if AFTERNOON_START <= t <= AFTERNOON_END:
        return "afternoon"
    if MORNING_END < t < AFTERNOON_START:
        return "lunch_break"
    return "closed"


def time_until_close(dt: datetime.datetime = None) -> int:
    """距离收盘(15:00)还有多少秒，已收盘返回负值"""
    if dt is None:
        dt = datetime.datetime.now()
    if not is_trading_day(dt):
        return -1
    close_dt = datetime.datetime.combine(dt.date(), AFTERNOON_END)
    return int((close_dt - dt).total_seconds())


def next_trading_time(dt: datetime.datetime = None) -> Optional[datetime.datetime]:
    """返回下一个交易时段的起始时间"""
    if dt is None:
        dt = datetime.datetime.now()
    current_date = dt.date()
    session = get_trading_session(dt)

    if session == "non_trading":
        for offset in range(7):
            check = current_date + datetime.timedelta(days=offset)
            if is_trading_day(datetime.datetime.combine(check, datetime.time(12, 0))):
                return datetime.datetime.combine(check, MORNING_START)
    elif session == "morning":
        return datetime.datetime.combine(current_date, AFTERNOON_START)
    elif session in ("lunch_break", "closed"):
        for offset in range(1, 7):
            check = current_date + datetime.timedelta(days=offset)
            if is_trading_day(datetime.datetime.combine(check, datetime.time(12, 0))):
                return datetime.datetime.combine(check, MORNING_START)

    return None

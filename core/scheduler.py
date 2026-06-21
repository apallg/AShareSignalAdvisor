"""交易日定时扫描调度器"""
import threading
import logging
import datetime
import time

import config

logger = logging.getLogger(__name__)

MORNING_TIME = getattr(config, "SCAN_MORNING_TIME", "09:35")
AFTERNOON_TIME = getattr(config, "SCAN_AFTERNOON_TIME", "14:55")
DEFAULT_THRESHOLD = getattr(config, "SCAN_DEFAULT_THRESHOLD", 7)

SESSION_AM = "早盘"
SESSION_PM = "尾盘"
SESSION_MANUAL = "手动"


def _parse_time(s):
    h, m = map(int, s.split(":"))
    return datetime.time(h, m)


def _is_trading_day(dt):
    return dt.weekday() < 5


class TradingDayScheduler:
    def __init__(self):
        self._thread = None
        self._running = False
        self._morning_t = _parse_time(MORNING_TIME)
        self._afternoon_t = _parse_time(AFTERNOON_TIME)
        self.morning_time = MORNING_TIME
        self.afternoon_time = AFTERNOON_TIME
        self.default_threshold = DEFAULT_THRESHOLD
        self.last_scan = None
        self.last_result = None
        self.next_morning = None
        self.next_afternoon = None

    @property
    def running(self):
        return self._running

    def status(self):
        return {
            "running": self._running,
            "morning_time": self.morning_time,
            "afternoon_time": self.afternoon_time,
            "default_threshold": self.default_threshold,
            "last_scan": self.last_scan,
            "last_result": self.last_result,
            "next_morning": self.next_morning,
            "next_afternoon": self.next_afternoon,
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"交易日定时扫描已启动 {SESSION_AM}{self.morning_time} {SESSION_PM}{self.afternoon_time} 阈值{self.default_threshold}")

    def stop(self):
        self._running = False
        logger.info("交易日定时扫描已停止")

    def trigger(self):
        t = threading.Thread(target=self._run_scan, args=(SESSION_MANUAL,), daemon=True)
        t.start()

    def _get_next_times(self):
        now = datetime.datetime.now()
        today = now.date()

        d = today
        while True:
            if _is_trading_day(d):
                m = datetime.datetime.combine(d, self._morning_t)
                a = datetime.datetime.combine(d, self._afternoon_t)
                times = []
                if d > today or now < m:
                    times.append((SESSION_AM, m))
                if d > today or now < a:
                    times.append((SESSION_PM, a))
                if times:
                    return times
            d += datetime.timedelta(days=1)

    def _run_scan(self, session_name):
        from core.portfolio_manager import PortfolioScanner
        try:
            scanner = PortfolioScanner()
            results = scanner.scan_all(threshold=self.default_threshold, include={"financial": False})
            self.last_scan = datetime.datetime.now().isoformat()
            self.last_result = f"{session_name}: {len(results)}条风险"
            logger.info(f"定时扫描 [{session_name}] 完成: {len(results)}条风险")
        except Exception as e:
            self.last_result = f"{session_name}: 失败 - {e}"
            logger.error(f"定时扫描 [{session_name}] 失败: {e}")

    def _run(self):
        while self._running:
            try:
                times = self._get_next_times()
                session_name, next_dt = times[0]

                nm = None
                na = None
                for sn, dt in times:
                    if sn == SESSION_AM:
                        nm = dt.isoformat()
                    else:
                        na = dt.isoformat()
                if nm != self.next_morning:
                    self.next_morning = nm
                if na != self.next_afternoon:
                    self.next_afternoon = na

                wait = (next_dt - datetime.datetime.now()).total_seconds()
                logger.info(f"下次定时扫描: {session_name} {next_dt.isoformat()} (等待{wait/60:.0f}分钟)")

                while self._running and wait > 0:
                    time.sleep(min(wait, 60))
                    wait = (next_dt - datetime.datetime.now()).total_seconds()

                if self._running:
                    self._run_scan(session_name)
            except Exception as e:
                logger.error(f"调度器异常: {e}")
                time.sleep(60)


_scheduler = None


def get_scheduler() -> TradingDayScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TradingDayScheduler()
    return _scheduler

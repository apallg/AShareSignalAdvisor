"""分时段调度器 - 定时扫描持仓并推送风险告警"""
import logging
import threading
from datetime import datetime, time
from typing import Optional, Callable, List
 
logger = logging.getLogger(__name__)
 
 
class Scheduler:
    """简易调度器, 支持指定时间点执行扫描任务"""
 
    def __init__(self):
        self._tasks: List[dict] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
 
    def add_task(self, task_func: Callable, hour: int, minute: int, label: str = ""):
        """添加定时任务"""
        self._tasks.append({
            "func": task_func,
            "hour": hour,
            "minute": minute,
            "label": label or f"{hour:02d}:{minute:02d}",
        })
        logger.info(f"已添加定时任务: {label} @ {hour:02d}:{minute:02d}")
 
    def start(self):
        """启动调度器（后台线程）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("调度器已启动 (后台线程)")
 
    def stop(self):
        """停止调度器"""
        self._running = False
        logger.info("调度器已停止")
 
    def _run_loop(self):
        """主循环，每分钟检查一次是否需要执行任务"""
        while self._running:
            now = datetime.now()
            for task in self._tasks:
                if task["hour"] == now.hour and task["minute"] == now.minute:
                    try:
                        logger.info(f"执行定时任务: {task['label']}")
                        task["func"]()
                    except Exception as e:
                        logger.error(f"定时任务执行失败 [{task['label']}]: {e}")
            # 每 60 秒检查一次
            import time
            time.sleep(60)
 
    @property
    def is_running(self) -> bool:
        return self._running
 
    @property
    def tasks(self) -> List[dict]:
        return self._tasks
 
 
# ─── 预设默认调度时段 ─────────────────────────
 
DEFAULT_SCHEDULE = [
    (8, 30, "盘前扫描"),    # 开盘前
    (11, 30, "午盘扫描"),   # 午间休市
    (15, 30, "收盘扫描"),   # 收盘后
    (20, 0, "晚间扫描"),    # 晚间复盘
]
 
 
def create_default_scheduler(scanner) -> Scheduler:
    """创建默认调度器, 绑定持仓扫描任务"""
    sched = Scheduler()
 
    def scan_job():
        alerts = scanner.scan_all(threshold=5)
        count = len(alerts)
        if count > 0:
            codes = ", ".join(a["stock_code"] for a in alerts)
            logger.info(f"扫描完成: {count} 只持仓触发告警: {codes}")
        else:
            logger.info("扫描完成: 未触发告警")
 
    for hour, minute, label in DEFAULT_SCHEDULE:
        sched.add_task(scan_job, hour, minute, label)
 
    return sched
 
 
def run_once(scanner) -> List[dict]:
    """立即执行一次全量扫描"""
    logger.info("手动触发全量扫描")
    return scanner.scan_all(threshold=5)

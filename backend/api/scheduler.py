"""定时扫描调度 API"""
from fastapi import APIRouter
from core.scheduler import get_scheduler

router = APIRouter()


@router.get("/status")
def scheduler_status():
    s = get_scheduler()
    return {"data": s.status()}


@router.post("/start")
def scheduler_start():
    get_scheduler().start()
    return {"data": get_scheduler().status()}


@router.post("/stop")
def scheduler_stop():
    get_scheduler().stop()
    return {"data": get_scheduler().status()}


@router.post("/trigger")
def scheduler_trigger():
    get_scheduler().trigger()
    return {"status": "ok", "message": "手动扫描已触发"}

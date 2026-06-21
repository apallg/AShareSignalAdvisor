"""定时扫描调度 API"""
from fastapi import APIRouter
from core.scheduler import get_scheduler

router = APIRouter()


@router.get("/status")
def scheduler_status():
    return {"data": get_scheduler().status()}


@router.post("/start")
def scheduler_start():
    s = get_scheduler()
    s.start()
    return {"data": s.status()}


@router.post("/stop")
def scheduler_stop():
    s = get_scheduler()
    s.stop()
    return {"data": s.status()}


@router.post("/trigger")
def scheduler_trigger():
    get_scheduler().trigger()
    return {"data": {"triggered": True}}

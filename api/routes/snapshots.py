"""快照管理 API"""
import asyncio
import threading
from fastapi import APIRouter, HTTPException
from core.snapshot import create_snapshot, run_scan, get_snapshots, get_snapshot, delete_snapshot
from core.rules import init_rules

router = APIRouter()

# 扫描任务管理
_scan_tasks = {}
_scan_progress = {}


@router.on_event("startup")
async def startup():
    init_rules()


@router.post("")
async def new_snapshot(name: str = None):
    snapshot_id = create_snapshot(name=name)
    # 在后台线程中运行扫描
    progress = {}

    def progress_cb(data):
        progress.update(data)

    def run():
        try:
            run_scan(snapshot_id, "C:\\", progress_callback=progress_cb)
        except Exception as e:
            progress["error"] = str(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    _scan_tasks[snapshot_id] = t
    _scan_progress[snapshot_id] = progress

    return {"snapshot_id": snapshot_id, "message": "扫描已启动"}


@router.get("")
async def list_snapshots(limit: int = 20):
    return get_snapshots(limit)


@router.get("/{snapshot_id}")
async def get_one(snapshot_id: int):
    snap = get_snapshot(snapshot_id)
    if not snap:
        raise HTTPException(404, "快照不存在")
    return snap


@router.delete("/{snapshot_id}")
async def remove(snapshot_id: int):
    delete_snapshot(snapshot_id)
    return {"message": "已删除"}


@router.get("/{snapshot_id}/progress")
async def progress(snapshot_id: int):
    """获取扫描进度"""
    from sse_starlette.sse import EventSourceResponse

    async def event_generator():
        import json
        while True:
            p = _scan_progress.get(snapshot_id, {})
            yield {"data": json.dumps(p)}
            if p.get("done") or p.get("error"):
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())

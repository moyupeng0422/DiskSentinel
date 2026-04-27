"""实时监控 API（ReadDirectoryChangesW + SSE）"""
import json
import os
import asyncio
import threading
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import win32file
import win32con

router = APIRouter()

FILE_LIST_DIRECTORY = 0x0001

_monitor_running = False
_monitor_thread = None
_event_queue = None
_stop_event = threading.Event()
_loop = None

ACTION_MAP = {
    1: "created",
    2: "deleted",
    3: "modified",
    4: "renamed_old",
    5: "renamed_new",
}


def _monitor_loop(path: str):
    try:
        hDir = win32file.CreateFile(
            path,
            FILE_LIST_DIRECTORY,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
            None,
            win32file.OPEN_EXISTING,
            win32file.FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
    except Exception as e:
        _loop.call_soon_threadsafe(_event_queue.put_nowait, {"type": "error", "message": str(e)})
        return

    while not _stop_event.is_set():
        try:
            results = win32file.ReadDirectoryChangesW(
                hDir,
                1024 * 64,
                True,
                win32con.FILE_NOTIFY_CHANGE_FILE_NAME
                | win32con.FILE_NOTIFY_CHANGE_DIR_NAME
                | win32con.FILE_NOTIFY_CHANGE_SIZE
                | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE,
                None,
                None,
            )
            for action, filename in results:
                if isinstance(filename, bytes):
                    filename = filename.decode("utf-8", errors="replace")
                full_path = os.path.join(path, filename)
                action_type = ACTION_MAP.get(action, "unknown")
                size = 0
                try:
                    if action_type != "deleted":
                        size = os.path.getsize(full_path)
                except OSError:
                    pass
                _loop.call_soon_threadsafe(_event_queue.put_nowait, {
                    "type": action_type,
                    "path": full_path,
                    "name": filename,
                    "size": size,
                })
        except Exception:
            continue

    win32file.CloseHandle(hDir)


@router.post("/start")
async def start_monitor():
    global _monitor_running, _monitor_thread, _stop_event, _event_queue, _loop
    if _monitor_running:
        return {"status": "already_running"}
    _stop_event.clear()
    _loop = asyncio.get_event_loop()
    _event_queue = asyncio.Queue()
    _monitor_running = True
    _monitor_thread = threading.Thread(target=_monitor_loop, args=("C:\\",), daemon=True)
    _monitor_thread.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_monitor():
    global _monitor_running
    if not _monitor_running:
        return {"status": "not_running"}
    _stop_event.set()
    _monitor_running = False
    return {"status": "stopped"}


@router.get("/status")
async def status():
    return {"running": _monitor_running}


@router.get("/events")
async def events():
    async def event_generator():
        while _monitor_running:
            try:
                event = await asyncio.wait_for(_event_queue.get(), timeout=30)
                yield {"data": json.dumps(event)}
            except asyncio.TimeoutError:
                yield {"data": ""}
    return EventSourceResponse(event_generator())

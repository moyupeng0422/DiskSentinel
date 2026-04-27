"""仪表盘 API"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter
from core.disk_info import get_disk_usage
from core.snapshot import get_usage_history, record_disk_usage
from core.scanner import quick_scan_dirs

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)

# 目录扫描状态
_dir_scan = {"status": "idle", "dir_count": 0, "results": None, "file_types": None}


@router.get("/overview")
async def overview():
    usage = get_disk_usage("C:")
    record_disk_usage("C:")
    return usage


@router.get("/usage-history")
async def usage_history(days: int = 30):
    data = get_usage_history(days)
    return data


@router.post("/largest-dirs")
async def largest_dirs(top: int = 100):
    """启动目录扫描（后台线程），同时收集文件类型统计"""
    global _dir_scan
    if _dir_scan["status"] == "scanning":
        return {"status": "scanning", "dir_count": _dir_scan["dir_count"]}

    _dir_scan = {"status": "scanning", "dir_count": 0, "results": None, "file_types": None}

    def run():
        def on_progress(count):
            _dir_scan["dir_count"] = count

        data = quick_scan_dirs("C:\\", top, progress_callback=on_progress)
        _dir_scan["results"] = data["dirs"]
        _dir_scan["file_types"] = data["file_types"]
        _dir_scan["status"] = "completed"

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started", "dir_count": 0}


@router.get("/largest-dirs")
async def get_largest_dirs():
    """获取扫描结果（目录 + 文件类型）"""
    if _dir_scan["results"]:
        return {"status": "completed", "dirs": _dir_scan["results"], "file_types": _dir_scan["file_types"]}
    return {"status": _dir_scan["status"], "dir_count": _dir_scan.get("dir_count", 0)}


@router.get("/largest-files")
async def largest_files(top: int = 100, snapshot_id: int = None):
    if snapshot_id:
        from database import get_db
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT file_path, file_size, alloc_size, extension FROM file_entries WHERE snapshot_id=? ORDER BY file_size DESC LIMIT ?",
                (snapshot_id, top),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # 无 snapshot 时直接扫描
    import os
    import heapq
    from config import DEFAULT_EXCLUDES

    def scan():
        files = []
        for root, dirs, filenames in os.walk("C:\\"):
            dirs[:] = [d for d in dirs
                        if not d.startswith("$")
                        and d != "System Volume Information"
                        and not any(os.path.join(root, d).lower().startswith(os.path.normpath(e).lower()) for e in DEFAULT_EXCLUDES)]
            for fname in filenames:
                try:
                    fp = os.path.join(root, fname)
                    size = os.path.getsize(fp)
                    files.append({"path": fp, "size": size, "name": fname})
                except (OSError, PermissionError):
                    continue
        files.sort(key=lambda x: x["size"], reverse=True)
        return files[:top]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, scan)


@router.get("/file-type-stats")
async def file_type_stats():
    """从目录扫描缓存中获取文件类型统计（不再单独扫描）"""
    if _dir_scan["file_types"]:
        return _dir_scan["file_types"]
    return {"status": _dir_scan["status"]}

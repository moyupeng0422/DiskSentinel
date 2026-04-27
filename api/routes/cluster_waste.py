"""簇浪费分析 API"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Query
from core.cluster_waste import analyze_directory_waste, analyze_directory_waste_summary

router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=1)
_waste_running = False


@router.get("/stats")
async def waste_stats():
    """获取 C 盘簇浪费汇总统计（快速估算）"""
    loop = asyncio.get_event_loop()
    summary = await loop.run_in_executor(_executor, analyze_directory_waste_summary, "C:\\")
    return summary


@router.get("/results")
async def waste_results(top: int = Query(50, ge=1, le=500)):
    """获取浪费最多的文件列表"""
    global _waste_running
    if _waste_running:
        return {"status": "scanning", "message": "扫描进行中..."}
    _waste_running = True
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(_executor, analyze_directory_waste, "C:\\", top)
        return {"status": "completed", "files": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        _waste_running = False

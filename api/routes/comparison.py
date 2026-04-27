"""快照对比 API"""
from fastapi import APIRouter, HTTPException
from core.snapshot import compare_snapshots, get_snapshot

router = APIRouter()


@router.get("/{base_id}/{compare_id}/new-files")
async def new_files(base_id: int, compare_id: int):
    result = compare_snapshots(base_id, compare_id)
    return {"items": result["new_files"], "summary": result["summary"]}


@router.get("/{base_id}/{compare_id}/deleted-files")
async def deleted_files(base_id: int, compare_id: int):
    result = compare_snapshots(base_id, compare_id)
    return {"items": result["deleted_files"], "summary": result["summary"]}


@router.get("/{base_id}/{compare_id}/grown-files")
async def grown_files(base_id: int, compare_id: int):
    result = compare_snapshots(base_id, compare_id)
    return {"items": result["grown_files"], "summary": result["summary"]}


@router.get("/{base_id}/{compare_id}/shrunk-files")
async def shrunk_files(base_id: int, compare_id: int):
    result = compare_snapshots(base_id, compare_id)
    return {"items": result["shrunk_files"], "summary": result["summary"]}


@router.get("/{base_id}/{compare_id}/summary")
async def summary(base_id: int, compare_id: int):
    base = get_snapshot(base_id)
    compare = get_snapshot(compare_id)
    if not base or not compare:
        raise HTTPException(404, "快照不存在")
    result = compare_snapshots(base_id, compare_id)
    return result["summary"]

"""清理 API"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.rules import get_rules, toggle_rule, get_rules_by_ids
from core.cleaner import (
    scan_cleanable_files,
    scan_dir_files,
    execute_cleanup_with_backup,
    restore_from_backup,
    get_backup_targets,
    get_backup_history,
    get_cleanup_history,
)

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)

# AI 推送的待清理文件（内存存储，重启清空）
_selected_dirs = []   # [{"path": str, "reason": str}]


class PreviewRequest(BaseModel):
    rule_ids: Optional[list[int]] = None
    use_enabled: bool = True


class DirCleanupRequest(BaseModel):
    dirs: list[str]
    backup_drive: str


class ExecuteRequest(BaseModel):
    rule_ids: list[int]
    backup_drive: str


class RestoreRequest(BaseModel):
    batch_id: str


class ToggleRequest(BaseModel):
    enabled: bool


@router.get("/rules")
async def list_rules():
    return get_rules()


@router.put("/rules/{rule_id}", response_model=dict)
async def toggle(rule_id: int, body: ToggleRequest):
    toggle_rule(rule_id, body.enabled)
    return {"message": "已更新"}


@router.post("/preview")
async def preview(body: PreviewRequest):
    """预览可清理文件（不执行删除）"""
    if body.use_enabled and not body.rule_ids:
        rules = [r for r in get_rules() if r["is_enabled"]]
    else:
        rules = get_rules_by_ids(body.rule_ids or [])

    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(_executor, scan_cleanable_files, rules)
    total_size = sum(f["size"] for f in files)
    by_category = {}
    for f in files:
        cat = f["category"]
        if cat not in by_category:
            by_category[cat] = {"count": 0, "size": 0, "rules": set()}
        by_category[cat]["count"] += 1
        by_category[cat]["size"] += f["size"]
        by_category[cat]["rules"].add(f["rule_name"])

    for cat in by_category:
        by_category[cat]["rules"] = list(by_category[cat]["rules"])

    return {
        "total_files": len(files),
        "total_size": total_size,
        "by_category": by_category,
        "files": files[:500],  # 最多返回 500 条预览
    }


@router.post("/execute")
async def execute(body: ExecuteRequest):
    """备份到指定盘后执行清理"""
    rules = get_rules_by_ids(body.rule_ids)
    if not rules:
        raise HTTPException(400, "未选择清理规则")

    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(_executor, scan_cleanable_files, rules)
    if not files:
        return {"success": True, "message": "没有可清理的文件", "files_moved": 0, "bytes_freed": 0}

    result = await loop.run_in_executor(_executor, execute_cleanup_with_backup, files, body.backup_drive)
    return result


@router.get("/backup-targets")
async def backup_targets():
    return get_backup_targets()


@router.post("/select-dirs")
async def select_dirs(body: dict):
    """AI 推送可清理目录到仪表盘自动勾选"""
    global _selected_dirs
    dirs = body.get("dirs", [])
    for d in dirs:
        if not any(s["path"] == d["path"] for s in _selected_dirs):
            _selected_dirs.append(d)
    return {"added": len(dirs), "total": len(_selected_dirs)}


@router.get("/selected-dirs")
async def get_selected_dirs():
    """获取 AI 推送的目录列表"""
    return _selected_dirs


@router.delete("/selected-dirs")
async def clear_selected_dirs():
    """清空 AI 推送的目录列表"""
    global _selected_dirs
    _selected_dirs = []
    return {"message": "已清空"}


@router.post("/preview-dirs")
async def preview_dirs(body: dict):
    """预览指定目录中的文件"""
    dirs = body.get("dirs", [])
    if not dirs:
        return {"total_files": 0, "total_size": 0, "files": []}
    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(_executor, scan_dir_files, dirs)
    total_size = sum(f["size"] for f in files)
    return {
        "total_files": len(files),
        "total_size": total_size,
        "files": files[:500],
    }


@router.post("/execute-dirs")
async def execute_dirs(body: DirCleanupRequest):
    """备份到指定盘后清理选中目录中的文件"""
    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(_executor, scan_dir_files, body.dirs)
    if not files:
        return {"success": True, "message": "没有可清理的文件", "files_moved": 0, "bytes_freed": 0}
    result = await loop.run_in_executor(_executor, execute_cleanup_with_backup, files, body.backup_drive)
    return result


@router.post("/restore")
async def restore(body: RestoreRequest):
    result = restore_from_backup(body.batch_id)
    return result


@router.get("/backups")
async def backups():
    return get_backup_history()


@router.get("/history")
async def history(limit: int = 100):
    return get_cleanup_history(limit)

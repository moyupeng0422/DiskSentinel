"""清理引擎：规则解析、预览、备份执行、恢复"""
import os
import shutil
import time
import fnmatch
from datetime import datetime, timezone
from database import get_db
from config import PROTECTED_PATHS, BACKUP_ROOT_DIR


def is_safe_to_delete(file_path: str) -> bool:
    """检查路径是否安全可删除"""
    normalized = os.path.normpath(file_path).lower()
    for protected in PROTECTED_PATHS:
        if normalized.startswith(os.path.normpath(protected).lower()):
            return False
    return True


def resolve_path(pattern: str) -> str:
    """解析路径中的环境变量"""
    expanded = os.path.expandvars(pattern)
    expanded = os.path.expanduser(expanded)
    return expanded


def scan_cleanable_files(rules: list) -> list:
    """根据规则列表扫描可清理文件（递归子目录）"""
    results = []
    now = time.time()

    for rule in rules:
        if not rule.get("is_enabled", True):
            continue

        min_age_seconds = rule.get("min_age_days", 0) * 86400
        file_patterns = [p.strip() for p in rule.get("file_pattern", "").split(",") if p.strip()] if rule.get("file_pattern") else []
        exclude_patterns = [p.strip() for p in rule.get("exclude_pattern", "").split(",") if p.strip()] if rule.get("exclude_pattern") else []
        match_all = not file_patterns  # file_pattern 为 "*" 或空时匹配所有文件

        for path_pattern in rule["path_pattern"].split(","):
            base_path = resolve_path(path_pattern.strip())
            if not os.path.isdir(base_path):
                continue

            try:
                entries = list(os.scandir(base_path))
            except (PermissionError, OSError):
                continue

            # 用栈实现递归遍历子目录
            stack = list(entries)
            while stack:
                entry = stack.pop()
                try:
                    if entry.is_dir(follow_symlinks=False):
                        try:
                            sub_entries = list(os.scandir(entry.path))
                            stack.extend(sub_entries)
                        except (PermissionError, OSError):
                            continue
                        continue

                    stat = entry.stat(follow_symlinks=False)
                except (OSError, PermissionError):
                    continue

                if min_age_seconds > 0 and (now - stat.st_mtime) < min_age_seconds:
                    continue

                if not match_all:
                    if not any(fnmatch.fnmatch(entry.name, p) for p in file_patterns):
                        continue

                if exclude_patterns:
                    if any(fnmatch.fnmatch(entry.name, p) for p in exclude_patterns):
                        continue

                if not is_safe_to_delete(entry.path):
                    continue

                results.append({
                    "path": entry.path,
                    "name": entry.name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "category": rule["category"],
                    "risk_level": rule.get("risk_level", "low"),
                })

    results.sort(key=lambda x: x["size"], reverse=True)
    return results


def get_backup_targets() -> list:
    """获取可用备份目标盘（排除 C 盘）"""
    from core.disk_info import get_available_drives, get_drive_free_space
    targets = []
    for drive in get_available_drives():
        if drive.upper().startswith("C"):
            continue
        free = get_drive_free_space(drive)
        if free > 0:
            targets.append({
                "drive": drive,
                "free_bytes": free,
                "label": f"{drive} (可用 {free / 1024 / 1024 / 1024:.1f} GB)",
            })
    return targets


def execute_cleanup_with_backup(files: list, backup_drive: str) -> dict:
    """备份到指定盘后清理文件。

    流程：将文件移动到备份目录 → 验证 → 完成
    失败时回滚已移动的文件。
    """
    from database import get_db

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(backup_drive + "\\", BACKUP_ROOT_DIR, batch_id)
    moved_files = []
    total_freed = 0
    total_failed = 0
    errors = []

    # 检查备份目标空间
    required = sum(f["size"] for f in files)
    from core.disk_info import get_drive_free_space
    available = get_drive_free_space(backup_drive)
    if required > available * 0.9:  # 保留 10% 余量
        return {
            "success": False,
            "error": f"备份空间不足：需要 {_fmt_size(required)}，{backup_drive} 可用 {_fmt_size(available)}",
            "batch_id": batch_id,
        }

    os.makedirs(backup_dir, exist_ok=True)
    action_time = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    try:
        # 创建备份批次记录
        conn.execute(
            "INSERT INTO cleanup_backups (batch_id, backup_drive, backup_dir, created_at, status) VALUES (?, ?, ?, ?, 'in_progress')",
            (batch_id, backup_drive, backup_dir, action_time),
        )
        conn.commit()
    finally:
        conn.close()

    for file_info in files:
        src = file_info["path"]
        if not os.path.exists(src):
            continue

        # 计算备份目标路径（保留原始目录结构，去掉盘符前缀）
        rel_path = os.path.relpath(src, os.path.splitdrive(src)[0] + "\\")
        dest = os.path.join(backup_dir, rel_path)
        dest_dir = os.path.dirname(dest)

        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, dest)
            moved_files.append({"src": src, "dest": dest, "size": file_info["size"]})
            total_freed += file_info["size"]

            # 记录成功
            conn = get_db()
            conn.execute(
                "INSERT INTO cleanup_actions (action_time, batch_id, rule_id, file_path, file_size, action_type, status, backup_path) VALUES (?, ?, ?, ?, ?, 'backup_and_delete', 'success', ?)",
                (action_time, batch_id, file_info.get("rule_id"), src, file_info["size"], dest),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            total_failed += 1
            errors.append(f"{src}: {str(e)}")
            conn = get_db()
            conn.execute(
                "INSERT INTO cleanup_actions (action_time, batch_id, rule_id, file_path, file_size, action_type, status, error_message) VALUES (?, ?, ?, ?, ?, 'backup_and_delete', 'failed', ?)",
                (action_time, batch_id, file_info.get("rule_id"), src, file_info["size"], str(e)),
            )
            conn.commit()
            conn.close()

    # 更新备份批次状态
    conn = get_db()
    conn.execute(
        "UPDATE cleanup_backups SET total_files=?, total_size=?, status='completed' WHERE batch_id=?",
        (len(moved_files), total_freed, batch_id),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "batch_id": batch_id,
        "backup_dir": backup_dir,
        "files_moved": len(moved_files),
        "files_failed": total_failed,
        "bytes_freed": total_freed,
        "errors": errors[:20],  # 最多返回 20 条错误
    }


def restore_from_backup(batch_id: str) -> dict:
    """从备份恢复文件到原位"""
    conn = get_db()
    try:
        backup = conn.execute("SELECT * FROM cleanup_backups WHERE batch_id=?", (batch_id,)).fetchone()
        if not backup:
            return {"success": False, "error": "备份批次不存在"}
        backup = dict(backup)
    finally:
        conn.close()

    backup_dir = backup["backup_dir"]
    if not os.path.isdir(backup_dir):
        return {"success": False, "error": "备份目录不存在"}

    # 获取该批次所有成功操作
    conn = get_db()
    try:
        actions = conn.execute(
            "SELECT file_path, backup_path, file_size FROM cleanup_actions WHERE batch_id=? AND status='success'",
            (batch_id,),
        ).fetchall()
    finally:
        conn.close()

    restored = 0
    failed = 0
    errors = []
    action_time = datetime.now(timezone.utc).isoformat()

    for action in actions:
        src = action["backup_path"]
        dest = action["file_path"]
        if not os.path.exists(src):
            failed += 1
            continue

        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            restored += 1

            conn = get_db()
            conn.execute(
                "INSERT INTO cleanup_actions (action_time, batch_id, file_path, file_size, action_type, status) VALUES (?, ?, ?, ?, 'restore', 'success')",
                (action_time, batch_id, dest, action["file_size"]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            failed += 1
            errors.append(f"{dest}: {str(e)}")

    # 清空备份目录（如果全部恢复成功）
    if failed == 0 and os.path.isdir(backup_dir):
        shutil.rmtree(backup_dir, ignore_errors=True)

    return {
        "success": failed == 0,
        "files_restored": restored,
        "files_failed": failed,
        "errors": errors[:20],
    }


def get_backup_history() -> list:
    """获取备份历史"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM cleanup_backups ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_cleanup_history(limit: int = 100) -> list:
    """获取清理操作历史"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM cleanup_actions ORDER BY action_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def scan_dir_files(dir_paths: list) -> list:
    """扫描指定目录列表中的所有文件"""
    results = []
    for dir_path in dir_paths:
        if not os.path.isdir(dir_path):
            continue
        try:
            entries = list(os.scandir(dir_path))
        except (PermissionError, OSError):
            continue
        stack = list(entries)
        while stack:
            entry = stack.pop()
            try:
                if entry.is_dir(follow_symlinks=False):
                    try:
                        stack.extend(list(os.scandir(entry.path)))
                    except (PermissionError, OSError):
                        continue
                    continue
                stat = entry.stat(follow_symlinks=False)
            except (OSError, PermissionError):
                continue
            if not is_safe_to_delete(entry.path):
                continue
            results.append({
                "path": entry.path,
                "name": entry.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    results.sort(key=lambda x: x["size"], reverse=True)
    return results


def _fmt_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

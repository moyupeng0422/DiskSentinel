"""快照管理：创建、存储、对比"""
import os
import time
from datetime import datetime, timezone
from database import get_db
from core.scanner import scan_drive


def create_snapshot(drive: str = "C:\\", name: str = None) -> int:
    """创建新快照，返回 snapshot_id。在后台线程中执行扫描。"""
    if not name:
        name = f"快照 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    from core.disk_info import get_cluster_size
    cluster_size = get_cluster_size(drive)

    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO snapshots (name, drive, scan_started, cluster_size) VALUES (?, ?, ?, ?)",
            (name, drive, datetime.now(timezone.utc).isoformat(), cluster_size),
        )
        snapshot_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    return snapshot_id


def run_scan(snapshot_id: int, drive: str = "C:\\", progress_callback=None):
    """执行扫描并写入数据库（阻塞调用，应在后台线程中运行）"""
    conn = get_db()
    total_files = 0
    total_size = 0
    total_alloc = 0

    def on_progress(file_count, skipped_dirs, skipped_files, done=False):
        if progress_callback:
            progress_callback({
                "snapshot_id": snapshot_id,
                "file_count": file_count,
                "skipped_dirs": len(skipped_dirs) if isinstance(skipped_dirs, set) else skipped_dirs,
                "skipped_files": skipped_files,
                "done": done,
            })

    try:
        for batch, count in scan_drive(drive, progress_callback=on_progress):
            rows = [
                (snapshot_id, path, size, alloc, mtime, parent, ext)
                for path, size, alloc, mtime, parent, ext in batch
            ]
            conn.executemany(
                "INSERT INTO file_entries (snapshot_id, file_path, file_size, alloc_size, mtime, parent_path, extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            total_files = count
            for _, size, alloc, *_ in batch:
                total_size += size
                total_alloc += alloc

        # 更新快照完成状态
        conn.execute(
            "UPDATE snapshots SET scan_finished=?, total_files=?, total_size=?, total_alloc=?, status='completed' WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), total_files, total_size, total_alloc, snapshot_id),
        )

        # 记录磁盘使用量
        from core.disk_info import get_disk_usage
        usage = get_disk_usage(drive.rstrip("\\"))
        conn.execute(
            "INSERT INTO disk_usage_history (recorded_at, drive, total_bytes, used_bytes, free_bytes, snapshot_id) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), drive, usage["total_bytes"], usage["used_bytes"], usage["free_bytes"], snapshot_id),
        )
        conn.commit()

        on_progress(total_files, 0, 0, done=True)
    except Exception as e:
        conn.execute(
            "UPDATE snapshots SET status='failed', error_message=? WHERE id=?",
            (str(e), snapshot_id),
        )
        conn.commit()
        raise
    finally:
        conn.close()


def get_snapshots(limit: int = 20) -> list:
    """获取快照列表"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, drive, scan_started, scan_finished, total_files, total_size, cluster_size, status FROM snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_snapshot(snapshot_id: int) -> dict:
    """获取单个快照详情"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_snapshot(snapshot_id: int):
    """删除快照及其文件条目"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM file_entries WHERE snapshot_id=?", (snapshot_id,))
        conn.execute("DELETE FROM snapshots WHERE id=?", (snapshot_id,))
        conn.commit()
    finally:
        conn.close()


def compare_snapshots(base_id: int, compare_id: int) -> dict:
    """对比两个快照，返回差异"""
    conn = get_db()
    try:
        # 新增文件
        new_files = conn.execute("""
            SELECT c.file_path, c.file_size, c.alloc_size, c.mtime, c.extension
            FROM file_entries c
            LEFT JOIN file_entries b ON c.file_path = b.file_path AND b.snapshot_id = ?
            WHERE c.snapshot_id = ? AND b.id IS NULL
            ORDER BY c.file_size DESC LIMIT 500
        """, (base_id, compare_id)).fetchall()

        # 删除的文件
        deleted_files = conn.execute("""
            SELECT b.file_path, b.file_size, b.alloc_size, b.mtime, b.extension
            FROM file_entries b
            LEFT JOIN file_entries c ON b.file_path = c.file_path AND c.snapshot_id = ?
            WHERE b.snapshot_id = ? AND c.id IS NULL
            ORDER BY b.file_size DESC LIMIT 500
        """, (compare_id, base_id)).fetchall()

        # 变大的文件
        grown_files = conn.execute("""
            SELECT c.file_path, b.file_size AS old_size, c.file_size AS new_size,
                   c.alloc_size, c.mtime, c.extension,
                   (c.file_size - b.file_size) AS delta
            FROM file_entries c
            JOIN file_entries b ON c.file_path = b.file_path
            WHERE c.snapshot_id = ? AND b.snapshot_id = ? AND c.file_size > b.file_size
            ORDER BY delta DESC LIMIT 500
        """, (compare_id, base_id)).fetchall()

        # 变小的文件
        shrunk_files = conn.execute("""
            SELECT c.file_path, b.file_size AS old_size, c.file_size AS new_size,
                   c.alloc_size, c.mtime, c.extension,
                   (b.file_size - c.file_size) AS delta
            FROM file_entries c
            JOIN file_entries b ON c.file_path = b.file_path
            WHERE c.snapshot_id = ? AND b.snapshot_id = ? AND c.file_size < b.file_size
            ORDER BY delta DESC LIMIT 500
        """, (compare_id, base_id)).fetchall()

        # 汇总统计
        new_total = sum(r["file_size"] for r in new_files)
        deleted_total = sum(r["file_size"] for r in deleted_files)
        grown_total = sum(r["delta"] for r in grown_files)
        shrunk_total = sum(r["delta"] for r in shrunk_files)

        return {
            "base_snapshot": get_snapshot(base_id),
            "compare_snapshot": get_snapshot(compare_id),
            "summary": {
                "new_count": len(new_files),
                "new_total_bytes": new_total,
                "deleted_count": len(deleted_files),
                "deleted_total_bytes": deleted_total,
                "grown_count": len(grown_files),
                "grown_total_bytes": grown_total,
                "shrunk_count": len(shrunk_files),
                "shrunk_total_bytes": shrunk_total,
            },
            "new_files": [dict(r) for r in new_files],
            "deleted_files": [dict(r) for r in deleted_files],
            "grown_files": [dict(r) for r in grown_files],
            "shrunk_files": [dict(r) for r in shrunk_files],
        }
    finally:
        conn.close()


def record_disk_usage(drive: str = "C:"):
    """记录当前磁盘使用量（不依赖快照）"""
    from core.disk_info import get_disk_usage
    usage = get_disk_usage(drive)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO disk_usage_history (recorded_at, drive, total_bytes, used_bytes, free_bytes) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), drive, usage["total_bytes"], usage["used_bytes"], usage["free_bytes"]),
        )
        conn.commit()
    finally:
        conn.close()


def get_usage_history(days: int = 30, drive: str = "C:") -> list:
    """获取磁盘使用量历史"""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT recorded_at, total_bytes, used_bytes, free_bytes
            FROM disk_usage_history
            WHERE drive=? AND recorded_at >= datetime('now', ?)
            ORDER BY recorded_at ASC
        """, (drive, f"-{days} days")).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

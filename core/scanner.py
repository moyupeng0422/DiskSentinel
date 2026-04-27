"""文件扫描引擎 - 遍历目录树收集文件元数据"""
import os
import math
import time
from config import DEFAULT_EXCLUDES, SCAN_BATCH_SIZE
from core.disk_info import get_cluster_size


def should_exclude(path: str) -> bool:
    """检查路径是否在排除列表中"""
    normalized = os.path.normpath(path).lower()
    for exc in DEFAULT_EXCLUDES:
        if normalized.startswith(os.path.normpath(exc).lower()):
            return True
    return False


def scan_drive(root_path: str, progress_callback=None):
    """扫描驱动器，生成文件元数据批次。

    Yields (batch, file_count) 元组，每个 batch 是列表：
    [(file_path, file_size, alloc_size, mtime, parent_path, extension), ...]
    """
    cluster_size = get_cluster_size(root_path)
    file_count = 0
    batch = []
    skipped_dirs = set()
    skipped_files = 0

    def _scan_dir(current_path):
        nonlocal file_count, batch, skipped_files
        try:
            entries = list(os.scandir(current_path))
        except (PermissionError, OSError) as e:
            skipped_dirs.add(current_path)
            return

        for entry in entries:
            if should_exclude(entry.path):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    yield from _scan_dir(entry.path)
                else:
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        size = stat.st_size
                        alloc = math.ceil(size / cluster_size) * cluster_size
                        mtime = stat.st_mtime
                        parent = os.path.dirname(entry.path)
                        ext = os.path.splitext(entry.name)[1].lower() or "(no-ext)"
                        batch.append((entry.path, size, alloc, mtime, parent, ext))
                        file_count += 1
                    except (PermissionError, OSError):
                        skipped_files += 1
                        continue

                    if len(batch) >= SCAN_BATCH_SIZE:
                        if progress_callback:
                            progress_callback(file_count, len(skipped_dirs), skipped_files)
                        yield batch, file_count
                        batch = []
            except (PermissionError, OSError):
                continue

    yield from _scan_dir(root_path)

    if batch:
        if progress_callback:
            progress_callback(file_count, len(skipped_dirs), skipped_files)
        yield batch, file_count

    if progress_callback:
        progress_callback(file_count, len(skipped_dirs), skipped_files, done=True)


def _walk_dir_size(path, current_depth=0):
    """递归计算目录大小（不限深度），返回 (total_size, file_count, has_permission_error)"""
    total = 0
    file_count = 0
    perm_error = False
    try:
        entries = os.scandir(path)
    except (PermissionError, OSError):
        return 0, 0, True

    for entry in entries:
        if should_exclude(entry.path):
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                sub_size, sub_count, sub_err = _walk_dir_size(entry.path, current_depth + 1)
                total += sub_size
                file_count += sub_count
                if sub_err:
                    perm_error = True
            else:
                st = entry.stat(follow_symlinks=False)
                total += st.st_size
                file_count += 1
        except (PermissionError, OSError):
            perm_error = True
            continue

    return total, file_count, perm_error


def quick_scan_dirs(root_path: str, max_depth: int = 3, progress_callback=None) -> dict:
    """扫描 C 盘所有目录，返回大小排行 top N（不限层级）。

    同时收集文件类型统计，一次遍历完成两项任务。
    返回 {"dirs": [...], "file_types": {...}}
    """
    top_n = 100

    categories = {
        ".sys": "系统文件", ".dll": "系统文件", ".exe": "可执行文件",
        ".msi": "安装包", ".cab": "安装包",
        ".log": "日志", ".tmp": "临时文件", ".temp": "临时文件",
        ".jpg": "图片", ".jpeg": "图片", ".png": "图片", ".gif": "图片",
        ".bmp": "图片", ".svg": "图片", ".ico": "图标", ".webp": "图片",
        ".mp4": "视频", ".avi": "视频", ".mkv": "视频", ".mov": "视频", ".wmv": "视频",
        ".mp3": "音频", ".wav": "音频", ".flac": "音频",
        ".pdf": "文档", ".doc": "文档", ".docx": "文档", ".xls": "文档",
        ".xlsx": "文档", ".ppt": "文档", ".pptx": "文档", ".txt": "文档",
        ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包", ".tar": "压缩包",
        ".js": "代码", ".py": "代码", ".ts": "代码", ".html": "代码",
        ".css": "代码", ".json": "代码", ".xml": "代码",
        ".dat": "数据文件", ".db": "数据文件", ".sqlite": "数据文件",
        ".ini": "配置文件", ".cfg": "配置文件", ".yaml": "配置文件", ".yml": "配置文件",
    }
    type_stats = {}

    dir_sizes = {}
    dir_count = 0
    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]
        dir_count += 1
        if progress_callback and dir_count % 500 == 0:
            progress_callback(dir_count)
        size = 0
        count = 0
        perm = False
        for fname in files:
            try:
                fpath = os.path.join(root, fname)
                st = os.stat(fpath)
                file_size = st.st_size
                size += file_size
                count += 1
                ext = os.path.splitext(fname)[1].lower() or "(no-ext)"
                if ext not in type_stats:
                    type_stats[ext] = {"size": 0, "count": 0}
                type_stats[ext]["size"] += file_size
                type_stats[ext]["count"] += 1
            except (OSError, PermissionError):
                perm = True
        dir_sizes[root] = {"total_size": size, "file_count": count, "own_size": size, "permission_error": perm}

    # 文件类型汇总到分类
    cat_stats = {}
    for ext, stats in type_stats.items():
        cat = categories.get(ext, "other")
        if cat not in cat_stats:
            cat_stats[cat] = {"size": 0, "count": 0, "extensions": []}
        cat_stats[cat]["size"] += stats["size"]
        cat_stats[cat]["count"] += stats["count"]
        cat_stats[cat]["extensions"].append(ext)
    file_types = dict(sorted(cat_stats.items(), key=lambda x: x[1]["size"], reverse=True))

    # 向上汇总：子目录大小加到父目录
    sorted_paths = sorted(dir_sizes.keys(), key=lambda p: p.count(os.sep), reverse=True)
    for path in sorted_paths:
        parent = os.path.dirname(path)
        if parent in dir_sizes:
            dir_sizes[parent]["total_size"] += dir_sizes[path]["total_size"]
            dir_sizes[parent]["file_count"] += dir_sizes[path]["file_count"]
            if dir_sizes[path]["permission_error"]:
                dir_sizes[parent]["permission_error"] = True

    # 按 total_size 排序，然后折叠父子关系
    all_dirs = [(v["total_size"], v["own_size"], k, v["file_count"], v["permission_error"])
                for k, v in dir_sizes.items() if k != root_path and v["total_size"] > 0]
    all_dirs.sort(key=lambda x: x[0], reverse=True)

    candidates = all_dirs[:top_n * 3]
    hidden = set()

    for total_size, own_size, path, count, perm in candidates:
        if path in hidden:
            continue
        prefix = path + os.sep
        child_total = 0
        for ct, co, cp, cc, cpe in candidates:
            if cp.startswith(prefix):
                child_total += ct
        if child_total >= total_size * 0.9:
            hidden.add(path)

    top = [c for c in candidates if c[2] not in hidden][:top_n]

    dir_results = []
    for total_size, own_size, path, count, perm in top:
        dir_results.append({"path": path, "own_size": own_size, "total_size": total_size, "file_count": count, "permission_error": perm})

    return {"dirs": dir_results, "file_types": file_types}

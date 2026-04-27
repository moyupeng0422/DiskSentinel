"""NTFS 簇浪费分析"""
import ctypes
from ctypes import wintypes
import math
from core.disk_info import get_cluster_size


class FILE_STANDARD_INFO(ctypes.Structure):
    _fields_ = [
        ("AllocationSize", ctypes.c_ulonglong),
        ("EndOfFile", ctypes.c_ulonglong),
        ("NumberOfLinks", wintypes.DWORD),
        ("DeletePending", wintypes.BOOLEAN),
        ("Directory", wintypes.BOOLEAN),
    ]


def get_allocation_size(file_path: str) -> int:
    """通过 GetFileInformationByHandleEx 获取精确分配大小"""
    import win32file
    import win32con

    try:
        handle = win32file.CreateFile(
            file_path,
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ,
            None,
            win32con.OPEN_EXISTING,
            0,
            None,
        )
    except Exception:
        return 0

    handle_val = handle.Detach()
    try:
        info = FILE_STANDARD_INFO()
        result = ctypes.windll.kernel32.GetFileInformationByHandleEx(
            handle_val, 1, ctypes.byref(info), ctypes.sizeof(info)
        )
        if result:
            return info.AllocationSize
        return 0
    except Exception:
        return 0
    finally:
        ctypes.windll.kernel32.CloseHandle(handle_val)


def estimate_alloc_size(file_size: int, cluster_size: int) -> int:
    """快速估算分配大小（适用于扫描阶段）"""
    if file_size == 0:
        return 0
    return ((file_size + cluster_size - 1) // cluster_size) * cluster_size


def calc_waste(file_size: int, alloc_size: int) -> dict:
    """计算单个文件的浪费信息"""
    waste = alloc_size - file_size
    waste_pct = round(waste / alloc_size * 100, 1) if alloc_size > 0 else 0
    return {"waste_bytes": waste, "waste_percent": waste_pct}


def analyze_directory_waste(directory: str, top_n: int = 50) -> list:
    """分析指定目录下所有文件的簇浪费，返回浪费最多的 top_n 个文件（快速估算）"""
    import os
    from config import DEFAULT_EXCLUDES

    cluster_size = get_cluster_size()
    results = []

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs
                    if not d.startswith("$")
                    and d != "System Volume Information"
                    and not any((os.path.join(root, d)).lower().startswith(os.path.normpath(e).lower()) for e in DEFAULT_EXCLUDES)]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                file_size = os.path.getsize(fpath)
                alloc_size = estimate_alloc_size(file_size, cluster_size)
                waste = alloc_size - file_size
                if waste > 0:
                    results.append({
                        "file_path": fpath,
                        "file_size": file_size,
                        "alloc_size": alloc_size,
                        "waste_bytes": waste,
                        "waste_percent": round(waste / alloc_size * 100, 1) if alloc_size else 0,
                    })
            except (OSError, PermissionError):
                continue

    results.sort(key=lambda x: x["waste_bytes"], reverse=True)
    return results[:top_n]


def analyze_directory_waste_summary(directory: str) -> dict:
    """分析指定目录的簇浪费汇总"""
    import os
    from config import DEFAULT_EXCLUDES

    cluster_size = get_cluster_size()
    total_waste = 0
    total_alloc = 0
    total_files = 0
    affected_files = 0
    dir_waste = {}

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs
                    if not d.startswith("$")
                    and d != "System Volume Information"
                    and not any((os.path.join(root, d)).lower().startswith(os.path.normpath(e).lower()) for e in DEFAULT_EXCLUDES)]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                file_size = os.path.getsize(fpath)
                alloc_size = estimate_alloc_size(file_size, cluster_size)
                waste = alloc_size - file_size

                total_files += 1
                total_alloc += alloc_size
                total_waste += waste
                if waste > 0:
                    affected_files += 1

                # 按一级子目录汇总
                rel = os.path.relpath(root, directory)
                top_dir = rel.split(os.sep)[0] if rel != "." else "(root)"
                if top_dir not in dir_waste:
                    dir_waste[top_dir] = {"waste": 0, "alloc": 0, "files": 0}
                dir_waste[top_dir]["waste"] += waste
                dir_waste[top_dir]["alloc"] += alloc_size
                dir_waste[top_dir]["files"] += 1
            except (OSError, PermissionError):
                continue

    dir_list = sorted(dir_waste.items(), key=lambda x: x[1]["waste"], reverse=True)
    return {
        "total_waste": total_waste,
        "total_alloc": total_alloc,
        "total_files": total_files,
        "affected_files": affected_files,
        "avg_waste_pct": round(total_waste / total_alloc * 100, 1) if total_alloc else 0,
        "cluster_size": cluster_size,
        "by_directory": [{"dir": d, **v} for d, v in dir_list[:30]],
    }

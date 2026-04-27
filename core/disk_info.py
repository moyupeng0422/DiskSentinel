"""磁盘信息获取（容量、簇大小）"""
import ctypes
from ctypes import wintypes


def get_cluster_size(drive_root: str = "C:\\") -> int:
    """通过 GetDiskFreeSpaceW 获取簇大小"""
    kernel32 = ctypes.windll.kernel32
    sectors_per_cluster = wintypes.DWORD(0)
    bytes_per_sector = wintypes.DWORD(0)
    free_clusters = wintypes.DWORD(0)
    total_clusters = wintypes.DWORD(0)

    result = kernel32.GetDiskFreeSpaceW(
        drive_root,
        ctypes.byref(sectors_per_cluster),
        ctypes.byref(bytes_per_sector),
        ctypes.byref(free_clusters),
        ctypes.byref(total_clusters),
    )
    if result:
        return sectors_per_cluster.value * bytes_per_sector.value
    return 4096


def get_disk_usage(drive: str = "C:") -> dict:
    """获取磁盘使用情况"""
    free_bytes = ctypes.c_ulonglong(0)
    total_bytes = ctypes.c_ulonglong(0)
    available_bytes = ctypes.c_ulonglong(0)

    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        drive,
        ctypes.byref(available_bytes),
        ctypes.byref(total_bytes),
        ctypes.byref(free_bytes),
    )

    used_bytes = total_bytes.value - free_bytes.value
    usage_pct = round(used_bytes / total_bytes.value * 100, 1) if total_bytes.value else 0

    return {
        "drive": drive,
        "total_bytes": total_bytes.value,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes.value,
        "available_bytes": available_bytes.value,
        "usage_percent": usage_pct,
        "cluster_size": get_cluster_size(drive + "\\"),
    }


def get_available_drives() -> list:
    """获取所有可用驱动器列表"""
    import string
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for i in range(26):
        if bitmask & (1 << i):
            letter = string.ascii_uppercase[i] + ":"
            drives.append(letter)
    return drives


def get_drive_free_space(drive: str = "D:") -> int:
    """获取指定驱动器可用空间"""
    free_bytes = ctypes.c_ulonglong(0)
    total_bytes = ctypes.c_ulonglong(0)
    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        drive, ctypes.byref(free_bytes), ctypes.byref(total_bytes), None
    )
    return free_bytes.value

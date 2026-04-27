"""DiskSentinel 配置"""

# 扫描设置
SCAN_DRIVE = "C:\\"
SCAN_BATCH_SIZE = 5000
SCAN_PORT = 8765

# 受保护路径（绝对不可删除/移动）
PROTECTED_PATHS = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]

# 默认排除目录（扫描时跳过）
DEFAULT_EXCLUDES = [
    r"C:\Windows\WinSxS",
    r"C:\Windows\Installer",
    r"C:\$Recycle.Bin",
    r"C:\System Volume Information",
    r"C:\hiberfil.sys",
    r"C:\pagefile.sys",
    r"C:\swapfile.sys",
]

# 备份设置
BACKUP_ROOT_DIR = "DiskSentinel_Backup"

# 数据库路径
import os
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "disk-sentinel.db")

# 自动清理旧快照天数
AUTO_CLEANUP_DAYS = 30

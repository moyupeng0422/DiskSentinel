"""清理规则定义与加载"""
import os
import glob as glob_module
from database import get_db

# 内置清理规则（无需 YAML 依赖）
BUILTIN_RULES = [
    {
        "name": "Windows 临时文件 (用户)",
        "category": "temp",
        "description": "用户临时目录中的临时文件",
        "path_pattern": "%TEMP%",
        "file_pattern": "*.tmp,*.log,*.old,*.bak,*.chk",
        "exclude_pattern": "*.exe,*.dll",
        "min_age_days": 3,
        "risk_level": "low",
        "is_enabled": True,
    },
    {
        "name": "Windows 临时文件 (系统)",
        "category": "temp",
        "description": "系统临时目录中的临时文件",
        "path_pattern": "C:\\Windows\\Temp",
        "file_pattern": "*.tmp,*.log,*.old,*.bak,*.chk,*.etl",
        "exclude_pattern": "*.exe,*.dll,*.sys",
        "min_age_days": 7,
        "risk_level": "medium",
        "is_enabled": True,
    },
    {
        "name": "Windows Update 下载缓存",
        "category": "update",
        "description": "Windows Update 下载的安装包缓存",
        "path_pattern": "C:\\Windows\\SoftwareDistribution\\Download",
        "file_pattern": "*",
        "exclude_pattern": "",
        "min_age_days": 7,
        "risk_level": "medium",
        "is_enabled": True,
    },
    {
        "name": "Windows 错误报告",
        "category": "logs",
        "description": "Windows 错误报告文件",
        "path_pattern": "C:\\ProgramData\\Microsoft\\Windows\\WER",
        "file_pattern": "*",
        "exclude_pattern": "",
        "min_age_days": 30,
        "risk_level": "low",
        "is_enabled": True,
    },
    {
        "name": "Windows 日志文件",
        "category": "logs",
        "description": "系统日志目录中的旧日志",
        "path_pattern": "C:\\Windows\\Logs",
        "file_pattern": "*.log,*.etl,*.txt,*.csv",
        "exclude_pattern": "",
        "min_age_days": 30,
        "risk_level": "low",
        "is_enabled": True,
    },
    {
        "name": "缩略图缓存",
        "category": "cache",
        "description": "Windows 资源管理器缩略图缓存",
        "path_pattern": "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer",
        "file_pattern": "thumbcache_*.db",
        "exclude_pattern": "",
        "min_age_days": 7,
        "risk_level": "low",
        "is_enabled": True,
    },
    {
        "name": "浏览器缓存 (Chrome)",
        "category": "cache",
        "description": "Chrome 浏览器缓存文件",
        "path_pattern": "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Cache",
        "file_pattern": "*",
        "exclude_pattern": "",
        "min_age_days": 3,
        "risk_level": "low",
        "is_enabled": True,
    },
    {
        "name": "浏览器缓存 (Edge)",
        "category": "cache",
        "description": "Edge 浏览器缓存文件",
        "path_pattern": "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Cache",
        "file_pattern": "*",
        "exclude_pattern": "",
        "min_age_days": 3,
        "risk_level": "low",
        "is_enabled": True,
    },
    {
        "name": "预读取数据",
        "category": "temp",
        "description": "Windows Prefetch 预读取缓存",
        "path_pattern": "C:\\Windows\\Prefetch",
        "file_pattern": "*.pf",
        "exclude_pattern": "",
        "min_age_days": 14,
        "risk_level": "low",
        "is_enabled": False,
    },
    {
        "name": "回收站",
        "category": "other",
        "description": "回收站中的文件",
        "path_pattern": "C:\\$Recycle.Bin",
        "file_pattern": "*",
        "exclude_pattern": "",
        "min_age_days": 7,
        "risk_level": "medium",
        "is_enabled": False,
    },
]


def init_rules():
    """初始化清理规则到数据库"""
    conn = get_db()
    try:
        existing = {r[0] for r in conn.execute("SELECT name FROM cleanup_rules").fetchall()}
        for rule in BUILTIN_RULES:
            if rule["name"] not in existing:
                conn.execute(
                    "INSERT INTO cleanup_rules (name, category, description, path_pattern, file_pattern, exclude_pattern, min_age_days, risk_level, is_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rule["name"], rule["category"], rule["description"], rule["path_pattern"],
                     rule["file_pattern"], rule.get("exclude_pattern", ""), rule["min_age_days"],
                     rule["risk_level"], 1 if rule["is_enabled"] else 0),
                )
        conn.commit()
    finally:
        conn.close()


def get_rules() -> list:
    """获取所有清理规则"""
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM cleanup_rules ORDER BY category, name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def toggle_rule(rule_id: int, enabled: bool):
    """启用/禁用规则"""
    conn = get_db()
    try:
        conn.execute("UPDATE cleanup_rules SET is_enabled=? WHERE id=?", (1 if enabled else 0, rule_id))
        conn.commit()
    finally:
        conn.close()


def get_rules_by_ids(rule_ids: list) -> list:
    """根据 ID 列表获取规则"""
    if not rule_ids:
        return []
    conn = get_db()
    try:
        placeholders = ",".join("?" * len(rule_ids))
        rows = conn.execute(f"SELECT * FROM cleanup_rules WHERE id IN ({placeholders})", rule_ids).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

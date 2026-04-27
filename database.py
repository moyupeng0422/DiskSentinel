"""SQLite 数据库初始化与数据访问"""
import sqlite3
import os
from config import DB_PATH

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    drive         TEXT NOT NULL DEFAULT 'C:',
    scan_started  TEXT NOT NULL,
    scan_finished TEXT,
    total_files   INTEGER DEFAULT 0,
    total_size    INTEGER DEFAULT 0,
    total_alloc   INTEGER DEFAULT 0,
    cluster_size  INTEGER DEFAULT 4096,
    status        TEXT DEFAULT 'running',
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_drive ON snapshots(drive);
CREATE INDEX IF NOT EXISTS idx_snapshots_started ON snapshots(scan_started);

CREATE TABLE IF NOT EXISTS file_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id   INTEGER NOT NULL,
    file_path     TEXT NOT NULL,
    file_size     INTEGER NOT NULL,
    alloc_size    INTEGER NOT NULL,
    mtime         REAL NOT NULL,
    is_dir        INTEGER DEFAULT 0,
    parent_path   TEXT NOT NULL,
    extension     TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_fe_snapshot_path ON file_entries(snapshot_id, file_path);
CREATE INDEX IF NOT EXISTS idx_fe_parent ON file_entries(snapshot_id, parent_path);
CREATE INDEX IF NOT EXISTS idx_fe_ext ON file_entries(snapshot_id, extension);

CREATE TABLE IF NOT EXISTS disk_usage_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at     TEXT NOT NULL,
    drive           TEXT NOT NULL,
    total_bytes     INTEGER NOT NULL,
    used_bytes      INTEGER NOT NULL,
    free_bytes      INTEGER NOT NULL,
    snapshot_id     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_duh_recorded ON disk_usage_history(recorded_at);

CREATE TABLE IF NOT EXISTS cleanup_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    description     TEXT,
    path_pattern    TEXT NOT NULL,
    file_pattern    TEXT,
    exclude_pattern TEXT,
    min_age_days    INTEGER DEFAULT 0,
    is_enabled      INTEGER DEFAULT 1,
    risk_level      TEXT DEFAULT 'low',
    estimated_size  INTEGER DEFAULT 0,
    last_scanned    TEXT
);

CREATE TABLE IF NOT EXISTS cleanup_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_time     TEXT NOT NULL,
    batch_id        TEXT,
    rule_id         INTEGER,
    file_path       TEXT NOT NULL,
    file_size       INTEGER NOT NULL,
    action_type     TEXT NOT NULL,
    status          TEXT NOT NULL,
    error_message   TEXT,
    backup_path     TEXT
);
CREATE INDEX IF NOT EXISTS idx_ca_time ON cleanup_actions(action_time);
CREATE INDEX IF NOT EXISTS idx_ca_batch ON cleanup_actions(batch_id);

CREATE TABLE IF NOT EXISTS cleanup_backups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        TEXT NOT NULL UNIQUE,
    backup_drive    TEXT NOT NULL,
    backup_dir      TEXT NOT NULL,
    total_files     INTEGER DEFAULT 0,
    total_size      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    status          TEXT DEFAULT 'completed'
);
CREATE INDEX IF NOT EXISTS idx_cb_batch ON cleanup_backups(batch_id);
"""


def get_db():
    """获取数据库连接（上下文管理器）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

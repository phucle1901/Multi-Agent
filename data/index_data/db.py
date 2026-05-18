"""SQLite connection + schema init."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from data.index_data import config


def get_conn(path: Path | str = config.DB_PATH) -> sqlite3.Connection:
    """Mở connection + apply pragma theo spec."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Chạy schema.sql để tạo bảng + index + trigger."""
    sql = config.SCHEMA_SQL.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


if __name__ == "__main__":
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    init_schema(conn)
    rows = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    ).fetchall()
    for r in rows:
        print(f"{r['type']:8}  {r['name']}")
    print(f"\nDB tại: {config.DB_PATH}")

"""
履歴データベース — SQLiteで応募・メッセージ・判定ログを管理

Usage:
  python tools/db.py init                    → テーブル初期化
  python tools/db.py log-job '{"id":"...","title":"...","proposal":"..."}'
  python tools/db.py log-message '{"thread_id":"...","client":"...","body":"..."}'
  python tools/db.py stats                   → 変換率統計を表示
  python tools/db.py stats-category          → カテゴリ別統計
"""

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "history.db")


@contextmanager
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                job_title TEXT NOT NULL,
                job_url TEXT,
                category TEXT,
                search_keyword TEXT,
                budget INTEGER DEFAULT 0,
                match_score INTEGER DEFAULT 0,
                proposal_text TEXT,
                status TEXT DEFAULT 'applied',
                applied_at TEXT NOT NULL,
                responded_at TEXT,
                contracted_at TEXT,
                completed_at TEXT,
                revenue INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(job_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                thread_url TEXT,
                client_name TEXT,
                job_title TEXT,
                phase TEXT,
                direction TEXT NOT NULL,
                body TEXT NOT NULL,
                reply_generated TEXT,
                action TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
            CREATE INDEX IF NOT EXISTS idx_app_applied ON applications(applied_at);
            CREATE INDEX IF NOT EXISTS idx_msg_thread ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at);
        """)


def log_application(data):
    init_db()
    with get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO applications
            (job_id, job_title, job_url, category, search_keyword,
             budget, match_score, proposal_text, status, applied_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'notified', datetime('now', 'localtime'))
        """, (
            data.get("id", ""),
            data.get("title", ""),
            data.get("url", ""),
            data.get("category", ""),
            data.get("search_keyword", ""),
            data.get("budget", 0),
            data.get("score", 0),
            data.get("proposal", ""),
        ))


def log_message(data):
    init_db()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO messages
            (thread_id, thread_url, client_name, job_title,
             phase, direction, body, reply_generated, action)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("thread_id", ""),
            data.get("thread_url", ""),
            data.get("client", ""),
            data.get("job_title", ""),
            data.get("phase", ""),
            data.get("direction", "received"),
            data.get("body", ""),
            data.get("reply_generated", ""),
            data.get("action", "pending"),
        ))


def get_conversion_stats(days=30):
    init_db()
    with get_db() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status IN ('responded','contracted','completed')
                    THEN 1 ELSE 0 END) as responded,
                SUM(CASE WHEN status IN ('contracted','completed')
                    THEN 1 ELSE 0 END) as contracted,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                COALESCE(SUM(revenue), 0) as revenue
            FROM applications WHERE applied_at >= ?
        """, (cutoff,)).fetchone()
        return dict(row)


def get_category_stats(days=30):
    init_db()
    with get_db() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT category, COUNT(*) as count,
                SUM(CASE WHEN status IN ('contracted','completed')
                    THEN 1 ELSE 0 END) as contracted
            FROM applications WHERE applied_at >= ?
            GROUP BY category ORDER BY count DESC
        """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]


COMMANDS = {
    "init": lambda: (init_db(), print("DB初期化完了")),
    "log-job": lambda: log_application(json.loads(sys.argv[2])),
    "log-message": lambda: log_message(json.loads(sys.argv[2])),
    "stats": lambda: print(json.dumps(get_conversion_stats(), ensure_ascii=False, indent=2)),
    "stats-category": lambda: print(json.dumps(get_category_stats(), ensure_ascii=False, indent=2)),
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    handler = COMMANDS.get(cmd)
    if handler:
        handler()
    else:
        print(f"Usage: python tools/db.py [{' | '.join(COMMANDS.keys())}]")

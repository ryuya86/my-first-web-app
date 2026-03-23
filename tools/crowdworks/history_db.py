"""
応募・メッセージ履歴データベース — SQLiteで全ログを保存・分析
"""

import sqlite3
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "crowdworks_history.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """テーブルを初期化"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                job_title TEXT NOT NULL,
                job_url TEXT,
                category TEXT,
                search_keyword TEXT,
                budget_min INTEGER,
                budget_max INTEGER,
                match_score INTEGER DEFAULT 0,
                competitor_count INTEGER DEFAULT 0,
                client_rating REAL DEFAULT 0,
                proposal_text TEXT,
                status TEXT DEFAULT 'applied',
                applied_at TEXT NOT NULL,
                responded_at TEXT,
                contracted_at TEXT,
                delivered_at TEXT,
                completed_at TEXT,
                revenue INTEGER DEFAULT 0,
                hours_spent REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(job_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                thread_url TEXT,
                client_name TEXT,
                job_id TEXT,
                job_title TEXT,
                phase TEXT,
                direction TEXT NOT NULL,
                body TEXT NOT NULL,
                reply_generated TEXT,
                reply_sent TEXT,
                ng_violations TEXT,
                action TEXT,
                response_time_minutes INTEGER,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS monthly_revenue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year_month TEXT NOT NULL,
                total_applications INTEGER DEFAULT 0,
                total_responses INTEGER DEFAULT 0,
                total_contracts INTEGER DEFAULT 0,
                total_completed INTEGER DEFAULT 0,
                total_revenue INTEGER DEFAULT 0,
                total_hours REAL DEFAULT 0,
                avg_hourly_rate REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(year_month)
            );

            CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
            CREATE INDEX IF NOT EXISTS idx_app_category ON applications(category);
            CREATE INDEX IF NOT EXISTS idx_app_applied ON applications(applied_at);
            CREATE INDEX IF NOT EXISTS idx_msg_thread ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at);

            CREATE TABLE IF NOT EXISTS auto_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_type TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT,
                confidence REAL,
                risk_level TEXT,
                context_json TEXT,
                outcome TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_autodec_created ON auto_decisions(created_at);
            CREATE INDEX IF NOT EXISTS idx_autodec_action ON auto_decisions(action);
        """)


# --- 応募関連 ---

def log_application(job, proposal, match_score=0, competitor_count=0, client_rating=0):
    """応募ログを記録"""
    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO applications
            (job_id, job_title, job_url, category, search_keyword,
             budget_min, budget_max, match_score, competitor_count,
             client_rating, proposal_text, status, applied_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'applied', datetime('now', 'localtime'))
        """, (
            job.get("id", ""),
            job.get("title", ""),
            job.get("url", ""),
            job.get("category", ""),
            job.get("search_keyword", ""),
            job.get("budget_min", 0),
            job.get("budget_max", 0),
            match_score,
            competitor_count,
            client_rating,
            proposal,
        ))


def update_application_status(job_id, status, revenue=0, hours_spent=0):
    """応募ステータスを更新"""
    with get_db() as conn:
        now = datetime.now().isoformat()
        time_col = {
            "responded": "responded_at",
            "contracted": "contracted_at",
            "delivered": "delivered_at",
            "completed": "completed_at",
        }.get(status)

        if time_col:
            conn.execute(f"""
                UPDATE applications
                SET status = ?, {time_col} = ?, revenue = ?, hours_spent = ?
                WHERE job_id = ?
            """, (status, now, revenue, hours_spent, job_id))
        else:
            conn.execute(
                "UPDATE applications SET status = ? WHERE job_id = ?",
                (status, job_id),
            )


# --- メッセージ関連 ---

def log_message(thread_id, thread_url, client_name, job_id, job_title,
                phase, direction, body, reply_generated="", reply_sent="",
                ng_violations="", action="", response_time_minutes=0):
    """メッセージログを記録"""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO messages
            (thread_id, thread_url, client_name, job_id, job_title,
             phase, direction, body, reply_generated, reply_sent,
             ng_violations, action, response_time_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            thread_id, thread_url, client_name, job_id, job_title,
            phase, direction, body, reply_generated, reply_sent,
            ng_violations, action, response_time_minutes,
        ))


def get_pending_replies(hours=2):
    """指定時間以上返信されていないメッセージを取得"""
    with get_db() as conn:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = conn.execute("""
            SELECT * FROM messages
            WHERE direction = 'received'
              AND action = 'pending'
              AND created_at < ?
            ORDER BY created_at ASC
        """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]


# --- 集計・分析 ---

def get_conversion_stats(days=30):
    """指定期間の変換率統計"""
    with get_db() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        row = conn.execute("""
            SELECT
                COUNT(*) as total_applied,
                SUM(CASE WHEN status IN ('responded','contracted','delivered','completed')
                    THEN 1 ELSE 0 END) as total_responded,
                SUM(CASE WHEN status IN ('contracted','delivered','completed')
                    THEN 1 ELSE 0 END) as total_contracted,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as total_completed,
                SUM(revenue) as total_revenue,
                SUM(hours_spent) as total_hours,
                AVG(match_score) as avg_match_score
            FROM applications
            WHERE applied_at >= ?
        """, (cutoff,)).fetchone()
        return dict(row)


def get_category_stats(days=30):
    """カテゴリ別受注率"""
    with get_db() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT
                category,
                COUNT(*) as applied,
                SUM(CASE WHEN status IN ('contracted','delivered','completed')
                    THEN 1 ELSE 0 END) as contracted,
                SUM(revenue) as revenue
            FROM applications
            WHERE applied_at >= ?
            GROUP BY category
            ORDER BY contracted DESC
        """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]


def log_auto_decision(decision_type, action, reason, confidence=0,
                      risk_level="", context_json="", outcome=""):
    """自動判定ログを記録"""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO auto_decisions
            (decision_type, action, reason, confidence, risk_level, context_json, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (decision_type, action, reason, confidence, risk_level, context_json, outcome))


def update_auto_decision_outcome(decision_id, outcome):
    """自動判定の結果を更新"""
    with get_db() as conn:
        conn.execute(
            "UPDATE auto_decisions SET outcome = ? WHERE id = ?",
            (outcome, decision_id),
        )


def get_auto_decision_stats(days=1):
    """指定期間の自動判定統計"""
    with get_db() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT
                action,
                COUNT(*) as count
            FROM auto_decisions
            WHERE created_at >= ?
            GROUP BY action
        """, (cutoff,)).fetchall()
        return {row["action"]: row["count"] for row in rows}


def get_response_time_stats(days=30):
    """返信速度の統計"""
    with get_db() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        row = conn.execute("""
            SELECT
                COUNT(*) as total_messages,
                AVG(response_time_minutes) as avg_response_time,
                MIN(response_time_minutes) as min_response_time,
                MAX(response_time_minutes) as max_response_time
            FROM messages
            WHERE direction = 'received'
              AND response_time_minutes > 0
              AND created_at >= ?
        """, (cutoff,)).fetchone()
        return dict(row)


def generate_monthly_summary(year_month=None):
    """月次サマリーを生成・保存"""
    if not year_month:
        year_month = datetime.now().strftime("%Y-%m")

    with get_db() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) as total_applications,
                SUM(CASE WHEN status IN ('responded','contracted','delivered','completed')
                    THEN 1 ELSE 0 END) as total_responses,
                SUM(CASE WHEN status IN ('contracted','delivered','completed')
                    THEN 1 ELSE 0 END) as total_contracts,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as total_completed,
                COALESCE(SUM(revenue), 0) as total_revenue,
                COALESCE(SUM(hours_spent), 0) as total_hours
            FROM applications
            WHERE strftime('%Y-%m', applied_at) = ?
        """, (year_month,)).fetchone()

        data = dict(row)
        data["year_month"] = year_month
        data["avg_hourly_rate"] = (
            data["total_revenue"] / data["total_hours"]
            if data["total_hours"] > 0 else 0
        )

        conn.execute("""
            INSERT OR REPLACE INTO monthly_revenue
            (year_month, total_applications, total_responses, total_contracts,
             total_completed, total_revenue, total_hours, avg_hourly_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            year_month, data["total_applications"], data["total_responses"],
            data["total_contracts"], data["total_completed"],
            data["total_revenue"], data["total_hours"], data["avg_hourly_rate"],
        ))

        return data


# 初期化
init_db()


if __name__ == "__main__":
    # テスト
    log_application(
        {"id": "test-001", "title": "テスト案件", "url": "https://example.com", "category": "data_entry"},
        "テスト提案文",
        match_score=85,
    )
    print("応募ログ記録完了")

    stats = get_conversion_stats()
    print(f"変換率統計: {stats}")

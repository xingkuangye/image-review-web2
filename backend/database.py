import sqlite3
from datetime import datetime
from pathlib import Path
import os

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'review.db')

def get_db():
    """Get a database connection.
    Each call creates a new independent connection, making it safe for use in
    thread executors (run_in_executor). SQLite connections cannot be shared across
    threads by default, but by creating fresh connections per call, we ensure
    thread safety.
    """
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    Path(os.path.dirname(DATABASE_PATH)).mkdir(parents=True, exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            nickname TEXT NOT NULL DEFAULT '匿名用户',
            created_at TEXT NOT NULL,
            last_active TEXT NOT NULL,
            is_banned INTEGER DEFAULT 0,
            user_token TEXT UNIQUE,
            credibility_score REAL,
            credibility_agrees INTEGER DEFAULT 0,
            credibility_total INTEGER DEFAULT 0
        )
    ''')
    
    # 创建角色表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            image_path TEXT NOT NULL,
            avatar_path TEXT
        )
    ''')
    
    # 创建图片表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            role_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        )
    ''')
    
    # 创建审核记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            FOREIGN KEY (image_id) REFERENCES images(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(image_id, user_id)
        )
    ''')
    
    # 创建设置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()

    # 创建索引以优化查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_role_id ON images(role_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_image_id ON reviews(image_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_reviewed_at ON reviews(reviewed_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)')

    conn.commit()
    conn.close()


def migrate_add_credibility():
    """为已有数据库添加可信度字段"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN credibility_score REAL")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN credibility_agrees INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN credibility_total INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN user_token TEXT")
        except Exception:
            pass
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_user_token ON users(user_token)")
        except Exception:
            pass
        conn.commit()
    finally:
        if conn:
            conn.close()


def update_all_credibility(required_weight=4.0):
    """全量重新计算所有用户可信度（加权投票）
    先根据当前信用分找出已完成图片，清空后重新计算，
    避免在无已完成图片时误清空用户信用分。
    """
    conn = get_db()
    cursor = conn.cursor()

    # 先根据当前信用分找出完成图片后再清空，避免丢失
    cursor.execute('''
        SELECT r.image_id
        FROM reviews r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.status IN ('pass', 'fail')
        GROUP BY r.image_id
        HAVING COALESCE(SUM(COALESCE(u.credibility_score, 0.5)), 0) >= ?
    ''', (required_weight,))
    completed_ids = [row[0] for row in cursor.fetchall()]

    if not completed_ids:
        conn.close()
        return  # 无图片完成，不破坏现有信用分

    # 初始化所有用户
    cursor.execute("UPDATE users SET credibility_score = NULL, credibility_agrees = 0, credibility_total = 0")

    for image_id in completed_ids:
        cursor.execute('''
            SELECT r.user_id, r.status, COALESCE(u.credibility_score, 0.5)
            FROM reviews r
            LEFT JOIN users u ON r.user_id = u.id
            WHERE r.image_id = ? AND r.status IN ('pass', 'fail')
        ''', (image_id,))
        rows = cursor.fetchall()

        if len(set(r[0] for r in rows)) < 2:
            continue

        w_pass = sum(r[2] for r in rows if r[1] == 'pass')
        w_fail = sum(r[2] for r in rows if r[1] == 'fail')
        final_result = 'pass' if w_pass >= w_fail else 'fail'

        for user_id, vote, _ in rows:
            agrees = 1 if vote == final_result else 0
            cursor.execute('''
                UPDATE users SET
                    credibility_agrees = credibility_agrees + ?,
                    credibility_total = credibility_total + 1,
                    credibility_score = CAST(credibility_agrees + ? + 1 AS REAL) / (credibility_total + 1 + 2)
                WHERE id = ?
            ''', (agrees, agrees, user_id))

    conn.commit()
    conn.close()


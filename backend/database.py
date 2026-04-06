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
            is_banned INTEGER DEFAULT 0
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
    conn.close()

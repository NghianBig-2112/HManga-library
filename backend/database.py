"""
Database Module (SQLite)
========================
Khởi tạo và quản lý kết nối cơ sở dữ liệu SQLite cục bộ.
"""

import sqlite3
from pathlib import Path

# Đường dẫn đến file cơ sở dữ liệu SQLite (thư mục dữ liệu vĩnh viễn, không phải cache)
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "manga.db"


def get_db() -> sqlite3.Connection:
    """Tạo và trả về một kết nối SQLite mới."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Tạo các bảng cơ sở dữ liệu nếu chưa tồn tại và nạp sẵn thể loại mẫu."""
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS comics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gallery_id TEXT,
                title TEXT NOT NULL,
                author TEXT,
                cover_filename TEXT,
                source_url TEXT
            );

            CREATE TABLE IF NOT EXISTS genres (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS comic_genres (
                comic_id INTEGER REFERENCES comics(id) ON DELETE CASCADE,
                genre_id INTEGER REFERENCES genres(id) ON DELETE CASCADE,
                PRIMARY KEY (comic_id, genre_id)
            );

            CREATE TABLE IF NOT EXISTS authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS comic_authors (
                comic_id INTEGER REFERENCES comics(id) ON DELETE CASCADE,
                author_id INTEGER REFERENCES authors(id) ON DELETE CASCADE,
                PRIMARY KEY (comic_id, author_id)
            );

            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comic_id INTEGER NOT NULL REFERENCES comics(id) ON DELETE CASCADE,
                chapter_number REAL NOT NULL,
                title TEXT,
                base_url TEXT NOT NULL,
                start_page INTEGER NOT NULL DEFAULT 1,
                end_page INTEGER NOT NULL,
                UNIQUE (comic_id, chapter_number)
            );

            CREATE INDEX IF NOT EXISTS idx_comics_title ON comics(title);
            CREATE INDEX IF NOT EXISTS idx_comics_author ON comics(author);
            CREATE INDEX IF NOT EXISTS idx_chapters_comic_id ON chapters(comic_id);
            CREATE INDEX IF NOT EXISTS idx_chapters_number ON chapters(comic_id, chapter_number);
            CREATE INDEX IF NOT EXISTS idx_genres_name ON genres(name);
            CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name);
            CREATE INDEX IF NOT EXISTS idx_comic_authors ON comic_authors(comic_id, author_id);
        """)

        # Xóa các thể loại chưa có truyện nào liên kết (không dùng thể loại mặc định có sẵn)
        conn.execute("DELETE FROM genres WHERE id NOT IN (SELECT DISTINCT genre_id FROM comic_genres)")

        # Tự động migrate dữ liệu tác giả từ bảng comics sang authors và comic_authors
        comics_with_authors = conn.execute("SELECT id, author FROM comics WHERE author IS NOT NULL AND TRIM(author) != ''").fetchall()
        for c in comics_with_authors:
            c_id = c["id"]
            author_str = c["author"]
            author_names = [a.strip() for a in author_str.split(",") if a.strip()]
            for a_name in author_names:
                conn.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", (a_name,))
                a_row = conn.execute("SELECT id FROM authors WHERE name = ?", (a_name,)).fetchone()
                if a_row:
                    conn.execute("INSERT OR IGNORE INTO comic_authors (comic_id, author_id) VALUES (?, ?)", (c_id, a_row["id"]))

        conn.commit()
        print("[INFO] Database SQLite ready with authors schema.")
    finally:
        conn.close()

"""
HManga Library - Database Module (PostgreSQL / Supabase)
=========================================================
Quản lý kết nối và khởi tạo lược đồ dữ liệu theo Hướng 2:
- Tách riêng bảng 'artists' và 'comic_artists'
- Tách riêng bảng 'genres' và 'comic_genres'
- Tối ưu bảng 'comics' có sẵn artist, language, category để hiển thị nhanh
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Thiết lập encoding utf-8 cho console để in tiếng Việt không bị lỗi
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 1. Đọc file cấu hình .env (ưu tiên thư mục gốc, sau đó đến thư mục backend)
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env" if (ROOT_DIR / ".env").exists() else BACKEND_DIR / ".env"
load_dotenv(ENV_FILE)

DATABASE_URL = os.getenv("DATABASE_URL")

# 2. Câu lệnh xóa sạch các bảng cũ nếu muốn làm mới hoàn toàn (Reset)
DROP_TABLES_SQL = """
DROP TABLE IF EXISTS comic_tags CASCADE;
DROP TABLE IF EXISTS tags CASCADE;
DROP TABLE IF EXISTS comic_genres CASCADE;
DROP TABLE IF EXISTS comic_artists CASCADE;
DROP TABLE IF EXISTS genres CASCADE;
DROP TABLE IF EXISTS artists CASCADE;
DROP TABLE IF EXISTS chapters CASCADE;
DROP TABLE IF EXISTS comics CASCADE;
DROP TABLE IF EXISTS folders CASCADE;
"""

# 3. Định nghĩa câu lệnh tạo bảng theo Hướng 2 (Chuẩn kiến trúc)
SCHEMA_SQL = """
-- 1. BẢNG THƯ MỤC (Folders)
CREATE TABLE IF NOT EXISTS folders (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT ''
);

-- 2. BẢNG TRUYỆN (Comics)
CREATE TABLE IF NOT EXISTS comics (
    id BIGINT PRIMARY KEY,                        -- Gallery ID từ NHentai
    folder_id BIGINT REFERENCES folders(id) ON DELETE SET NULL,
    media_id TEXT NOT NULL,                       -- Mã media CDN (vd: 48410)
    title TEXT NOT NULL,                          -- Tên truyện chuẩn
    artist TEXT DEFAULT 'Unknown',               -- Tên tác giả (lưu để hiển thị nhanh ở trang chủ)
    language TEXT DEFAULT 'Unknown',             -- Ngôn ngữ chính (english, japanese...)
    category TEXT DEFAULT 'Unknown',             -- Thể loại chính (manga, doujinshi...)
    cover_url TEXT NOT NULL,                      -- URL ảnh bìa
    num_pages INT NOT NULL DEFAULT 1,             -- Tổng số trang truyện
    page_exts TEXT DEFAULT '',                    -- Chuỗi đuôi ảnh từng trang (vd: 'jppwwg')
    created_at TIMESTAMPTZ DEFAULT NOW()          -- Thời điểm thêm vào thư viện
);

-- 3. BẢNG CHAPTER (Chapters)
CREATE TABLE IF NOT EXISTS chapters (
    id BIGSERIAL PRIMARY KEY,
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    chapter_number NUMERIC NOT NULL,              -- Số thứ tự tập (1, 2, 2.5...)
    title TEXT,                                   -- Tên chapter ("Toàn bộ", "Tập 1"...)
    media_id TEXT NOT NULL,                       -- CDN media của tập này
    start_page INT NOT NULL DEFAULT 1,            -- Trang bắt đầu
    end_page INT NOT NULL,                        -- Trang kết thúc
    page_exts TEXT DEFAULT ''                     -- Chuỗi đuôi ảnh từng trang của tập này
);

-- 4. BẢNG TÁC GIẢ (Artists) - Tách riêng phục vụ lọc truyện
CREATE TABLE IF NOT EXISTS artists (
    id BIGINT PRIMARY KEY,                        -- ID artist từ NHentai
    name TEXT NOT NULL,                           -- Tên tác giả
    slug TEXT NOT NULL                            -- Slug tìm kiếm
);

-- 5. BẢNG NỐI TRUYỆN VÀ TÁC GIẢ (Comic - Artists)
CREATE TABLE IF NOT EXISTS comic_artists (
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    artist_id BIGINT REFERENCES artists(id) ON DELETE CASCADE,
    PRIMARY KEY (comic_id, artist_id)
);

-- 6. BẢNG THỂ LOẠI (Genres) - Tách riêng chỉ chứa thể loại
CREATE TABLE IF NOT EXISTS genres (
    id BIGINT PRIMARY KEY,                        -- ID tag từ NHentai
    name TEXT NOT NULL,                           -- Tên thể loại (maid, schoolgirl, comedy...)
    slug TEXT NOT NULL                            -- Slug tìm kiếm
);

-- 7. BẢNG NỐI TRUYỆN VÀ THỂ LOẠI (Comic - Genres)
CREATE TABLE IF NOT EXISTS comic_genres (
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    genre_id BIGINT REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (comic_id, genre_id)
);

-- TỐI ƯU HÓA CHỈ MỤC TRUY VẤN (Indexes)
CREATE INDEX IF NOT EXISTS idx_comics_folder ON comics(folder_id);
CREATE INDEX IF NOT EXISTS idx_comics_title ON comics(title);
CREATE INDEX IF NOT EXISTS idx_chapters_comic ON chapters(comic_id);
CREATE INDEX IF NOT EXISTS idx_comic_artists_artist ON comic_artists(artist_id);
CREATE INDEX IF NOT EXISTS idx_comic_genres_genre ON comic_genres(genre_id);
CREATE INDEX IF NOT EXISTS idx_artists_name ON artists(name);
CREATE INDEX IF NOT EXISTS idx_genres_name ON genres(name);
"""


def get_connection():
    """Tạo kết nối tới PostgreSQL/Supabase, kết quả trả về dạng Dictionary."""
    if not DATABASE_URL:
        raise ValueError("Chưa cấu hình DATABASE_URL trong file .env!")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db(reset: bool = False):
    """
    Khởi tạo toàn bộ cấu trúc CSDL theo Hướng 2.
    - reset = True: Xóa sạch các bảng cũ (tags, comic_tags...) để làm mới hoàn toàn.
    - reset = False: Chỉ chạy CREATE TABLE IF NOT EXISTS.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if reset:
                    print("[INFO] Đang làm mới: Xóa các bảng cũ trên Supabase...")
                    cur.execute(DROP_TABLES_SQL)

                # 1. Chạy câu lệnh tạo các bảng mới
                print("[INFO] Đang khởi tạo các bảng mới theo kiến trúc phân tách...")
                cur.execute(SCHEMA_SQL)

                # 2. Tạo thư mục 'Mặc định' đầu tiên
                cur.execute("""
                    INSERT INTO folders (name, description)
                    VALUES (%s, %s)
                    ON CONFLICT (name) DO NOTHING;
                """, ("Mặc định", "Thư mục truyện mặc định"))

                conn.commit()
                print("[SUCCESS] Làm mới và khởi tạo Database thành công 100% trên Supabase!")
    except Exception as e:
        print(f"[LỖI] Khởi tạo Database thất bại: {e}")
        raise e


if __name__ == "__main__":
    # Mặc định khi chạy trực tiếp file này sẽ reset làm mới lại Supabase
    init_db(reset=True)

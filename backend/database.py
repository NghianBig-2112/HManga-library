"""
HManga Library - Module Cơ Sở Dữ Liệu (PostgreSQL / Supabase)
=============================================================
Chịu trách nhiệm:
1. Đọc biến môi trường DATABASE_URL từ file .env và tạo kết nối tới Supabase.
2. Định nghĩa và khởi tạo lược đồ 7 bảng chuẩn hóa:
   - folders        : Lưu danh sách thư mục phân loại truyện.
   - comics         : Lưu thông tin chính của bộ truyện (kèm artist, language, category, page_exts để truy vấn nhanh).
   - chapters       : Lưu danh sách các tập/chương của mỗi bộ truyện.
   - artists        : Lưu danh sách tác giả duy nhất.
   - comic_artists  : Bảng trung gian (N-N) nối truyện và tác giả.
   - genres         : Lưu danh sách thể loại (tags) duy nhất.
   - comic_genres   : Bảng trung gian (N-N) nối truyện và thể loại.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Thiết lập bảng mã UTF-8 cho console Windows để in tiếng Việt không bị lỗi font
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==================== 1. CẤU HÌNH KẾT NỐI (.ENV) ====================
# Ưu tiên đọc file .env ở thư mục gốc dự án, nếu không có thì tìm trong thư mục backend/
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env" if (ROOT_DIR / ".env").exists() else BACKEND_DIR / ".env"
load_dotenv(ENV_FILE)

DATABASE_URL = os.getenv("DATABASE_URL")


# ==================== 2. ĐỊNH NGHĨA LƯỢC ĐỒ CSDL (SQL SCHEMA) ====================

# Câu lệnh xóa sạch toàn bộ bảng (dùng khi cần Reset lại Database từ đầu)
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

# Câu lệnh khởi tạo 7 bảng chính và bộ chỉ mục (Indexes) tối ưu tốc độ tìm kiếm
SCHEMA_SQL = """
-- 1. BẢNG THƯ MỤC (Folders): Phân loại truyện theo danh mục cá nhân
CREATE TABLE IF NOT EXISTS folders (
    id BIGSERIAL PRIMARY KEY,                     -- ID thư mục tự tăng (1 = Mặc định)
    name TEXT UNIQUE NOT NULL,                    -- Tên thư mục (không trùng lặp)
    description TEXT DEFAULT ''                   -- Mô tả thư mục
);

-- 2. BẢNG TRUYỆN (Comics): Lưu thông tin tổng quan của từng bộ truyện
CREATE TABLE IF NOT EXISTS comics (
    id BIGINT PRIMARY KEY,                        -- Gallery ID gốc từ NHentai
    folder_id BIGINT REFERENCES folders(id) ON DELETE SET NULL,
    media_id TEXT NOT NULL,                       -- Mã thư mục ảnh trên CDN NHentai
    title TEXT NOT NULL,                          -- Tên truyện rút gọn (title_pretty)
    artist TEXT DEFAULT 'Unknown',               -- Tên tác giả (lưu sẵn để hiển thị nhanh ở Trang chủ)
    language TEXT DEFAULT 'Unknown',             -- Ngôn ngữ chính (english, japanese, chinese...)
    category TEXT DEFAULT 'Unknown',             -- Phân loại chính (manga, doujinshi...)
    cover_url TEXT NOT NULL,                      -- Đường dẫn ảnh bìa trên CDN
    num_pages INT NOT NULL DEFAULT 1,             -- Tổng số trang của bộ truyện gốc
    page_exts TEXT DEFAULT '',                    -- Chuỗi mã hóa đuôi ảnh từng trang (vd: 'jppwwg' -> jpg, png, webp, gif)
    created_at TIMESTAMPTZ DEFAULT NOW()          -- Thời điểm thêm truyện vào thư viện (dùng để sắp xếp mới nhất)
);

-- 3. BẢNG CHƯƠNG/TẬP (Chapters): Hỗ trợ chia nhỏ truyện dài hoặc gộp nhiều phần (Series)
CREATE TABLE IF NOT EXISTS chapters (
    id BIGSERIAL PRIMARY KEY,                     -- ID chapter tự tăng
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    chapter_number NUMERIC NOT NULL,              -- Số thứ tự chương (hỗ trợ cả số lẻ như 1.5, 2.5)
    title TEXT,                                   -- Tiêu đề chương ("Toàn bộ", "Chapter 1"...)
    media_id TEXT NOT NULL,                       -- Mã media CDN riêng của chương này (hỗ trợ gộp từ Gallery ID khác)
    start_page INT NOT NULL DEFAULT 1,            -- Trang bắt đầu của chương
    end_page INT NOT NULL,                        -- Trang kết thúc của chương
    page_exts TEXT DEFAULT ''                     -- Chuỗi mã hóa đuôi ảnh riêng của chương này
);

-- 4. BẢNG TÁC GIẢ (Artists): Lưu danh sách tác giả để phục vụ bộ lọc ở Trang chủ
CREATE TABLE IF NOT EXISTS artists (
    id BIGINT PRIMARY KEY,                        -- ID tag artist từ NHentai
    name TEXT NOT NULL,                           -- Tên tác giả
    slug TEXT NOT NULL                            -- Chuỗi đường dẫn thân thiện (slug)
);

-- 5. BẢNG NỐI TRUYỆN - TÁC GIẢ (Comic_Artists): Quan hệ nhiều - nhiều (N-N)
CREATE TABLE IF NOT EXISTS comic_artists (
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    artist_id BIGINT REFERENCES artists(id) ON DELETE CASCADE,
    PRIMARY KEY (comic_id, artist_id)
);

-- 6. BẢNG THỂ LOẠI (Genres): Lưu danh sách các tag nội dung/thể loại chi tiết
CREATE TABLE IF NOT EXISTS genres (
    id BIGINT PRIMARY KEY,                        -- ID tag thể loại từ NHentai
    name TEXT NOT NULL,                           -- Tên thể loại (schoolgirl, romance, comedy...)
    slug TEXT NOT NULL                            -- Chuỗi đường dẫn thân thiện (slug)
);

-- 7. BẢNG NỐI TRUYỆN - THỂ LOẠI (Comic_Genres): Quan hệ nhiều - nhiều (N-N)
CREATE TABLE IF NOT EXISTS comic_genres (
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    genre_id BIGINT REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (comic_id, genre_id)
);

-- TẠO CHỈ MỤC (INDEXES): Tăng tốc truy vấn lọc theo thư mục, tác giả, thể loại và tìm kiếm tên truyện
CREATE INDEX IF NOT EXISTS idx_comics_folder ON comics(folder_id);
CREATE INDEX IF NOT EXISTS idx_comics_title ON comics(title);
CREATE INDEX IF NOT EXISTS idx_chapters_comic ON chapters(comic_id);
CREATE INDEX IF NOT EXISTS idx_comic_artists_artist ON comic_artists(artist_id);
CREATE INDEX IF NOT EXISTS idx_comic_genres_genre ON comic_genres(genre_id);
CREATE INDEX IF NOT EXISTS idx_artists_name ON artists(name);
CREATE INDEX IF NOT EXISTS idx_genres_name ON genres(name);
"""


# ==================== 3. CÁC HÀM KẾT NỐI & KHỞI TẠO CSDL ====================

def get_connection():
    """
    Mở kết nối tới PostgreSQL (Supabase).
    Sử dụng RealDictCursor để mọi dòng dữ liệu trả về đều có dạng Dictionary (key: tên cột).
    """
    if not DATABASE_URL:
        raise ValueError("Chưa cấu hình DATABASE_URL trong file .env!")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db(reset: bool = False):
    """
    Kiểm tra và khởi tạo cấu trúc bảng trên Supabase.
    - reset = False (mặc định khi chạy server): Chỉ tạo bảng nếu chưa tồn tại, giữ nguyên dữ liệu cũ.
    - reset = True (khi chạy trực tiếp file database.py): Xóa sạch các bảng cũ và tạo mới hoàn toàn.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Xóa toàn bộ bảng cũ nếu bật chế độ reset
                if reset:
                    print("[INFO] Đang làm mới: Xóa các bảng cũ trên Supabase...")
                    cur.execute(DROP_TABLES_SQL)

                # 2. Tạo các bảng và chỉ mục (Indexes) nếu chưa có
                print("[INFO] Đang khởi tạo các bảng CSDL...")
                cur.execute(SCHEMA_SQL)

                # 3. Đảm bảo luôn có sẵn thư mục 'Mặc định' (ID = 1)
                cur.execute("""
                    INSERT INTO folders (name, description)
                    VALUES (%s, %s)
                    ON CONFLICT (name) DO NOTHING;
                """, ("Mặc định", "Thư mục truyện mặc định"))

                conn.commit()
                print("[SUCCESS] Khởi tạo Database thành công 100% trên Supabase!")
    except Exception as e:
        print(f"[LỖI] Khởi tạo Database thất bại: {e}")
        raise e


if __name__ == "__main__":
    # Khi chạy trực tiếp lệnh `python database.py`, hệ thống sẽ xóa sạch bảng cũ và tạo lại từ đầu
    init_db(reset=True)


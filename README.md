# 📚 HManga-library

Website đọc và quản lý truyện tranh cá nhân — đồng bộ đám mây với **Supabase (PostgreSQL)**, tích hợp trực tiếp **NHentai API v2**, cơ chế đọc truyện **Zero-Storage** (không tốn dung lượng ổ đĩa) và khả năng khôi phục dữ liệu tự động.

---

## 🏗️ Kiến trúc dự án: Clean Layered Architecture (v4.0)

Hệ thống được thiết kế theo kiến trúc phân tầng tinh gọn, loại bỏ các thành phần cồng kềnh, tối ưu hóa 100% cho **Supabase Cloud Database**:

```
HManga-library/
├── backend/                       ← FastAPI (Python) — Clean Layered
│   ├── data/                      ← Thư mục lưu bản sao lưu dự phòng
│   │   └── backup.json            ← Snapshot dữ liệu tối giản (Disaster Recovery)
│   ├── database.py                ← Kết nối Supabase (Client Singleton)
│   ├── models.py                  ← Pydantic schemas cho request validation & Chapter
│   ├── services.py                ← Toàn bộ Business Logic, Supabase queries & Chapter
│   ├── nhentai.py                 ← Trích xuất thông tin, CDN & In-Memory Image Proxy
│   ├── backup.py                  ← Logic kết xuất & Tự động phục hồi lên Supabase
│   ├── main.py                    ← Khởi tạo app FastAPI, static files & routes API
│   ├── requirements.txt           ← Dependencies (fastapi, uvicorn, supabase, requests...)
│   ├── .env                       ← File cấu hình biến môi trường (URL, Key)
│   └── .env.example               ← File mẫu cấu hình biến môi trường
│
├── frontend/                      ← HTML5 + Modern Dark CSS + Vanilla JS
│   ├── assets/                    ← Icon, logo và ảnh dự phòng
│   ├── index.html                 ← Thư viện cá nhân: Quản lý Thư mục & Tác giả
│   ├── discover.html              ← Khám phá NHentai: Bộ lọc gợi ý từ chính thư viện
│   ├── detail.html                ← Chi tiết truyện & Quản lý Chapter (Gộp bộ / Chia trang)
│   ├── reader.html                ← Trình đọc truyện (Webtoon cuộn dọc / Manga từng trang)
│   ├── style.css                  ← Toàn bộ stylesheet giao diện Dark Theme hiện đại
│   └── app.js                     ← API Client, Toast, Confirm modal dùng chung
│
├── DATABASE_REDESIGN.md           ← Bản thiết kế kiến trúc cơ sở dữ liệu chi tiết
└── README.md                      ← Hướng dẫn sử dụng & tài liệu dự án
```

| Thành phần | Công nghệ | Chi tiết |
|---|---|---|
| **Frontend** | HTML5 + CSS3 + Vanilla JS (Dark theme) | Tương tác mượt mà, không cần Node.js hay build tool |
| **Backend** | FastAPI + Uvicorn (Clean Layered) | Port `8000` (serve cả REST API và giao diện web tĩnh) |
| **Database** | **Supabase (PostgreSQL Cloud)** | 5 bảng cốt lõi + Chapters, dữ liệu nằm vĩnh viễn trên Cloud |
| **Storage Engine** | **Zero-Storage (In-Memory Streaming)** | Đọc truyện trực tiếp qua proxy RAM, 0 byte ổ cứng |

---

## ⚡ Cài đặt & Khởi chạy (Siêu đơn giản)

### Bước 1: Clone repository
```powershell
git clone https://github.com/Dekisugi-2112/HManga-library.git
cd HManga-library
```

### Bước 2: Cài đặt Python dependencies
```powershell
cd backend
pip install -r requirements.txt
```

### Bước 3: Cấu hình biến môi trường
Tạo file `backend/.env` (hoặc sao chép từ `.env.example`):
```env
# NHentai API Configuration (Tùy chọn)
NHENTAI_API_KEY=

# Supabase Configuration (Bắt buộc)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
```

### Bước 4: Tạo bảng trên Supabase (Chỉ cần chạy 1 lần khi tạo project mới)
Vào mục **SQL Editor** trên [Supabase Dashboard](https://supabase.com/dashboard) và chạy script:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS folders (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS comics (
    id BIGINT PRIMARY KEY,
    media_id TEXT NOT NULL,
    title_pretty TEXT NOT NULL,
    cover_path TEXT NOT NULL,
    num_pages INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tags (
    id BIGINT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folder_comics (
    folder_id BIGINT REFERENCES folders(id) ON DELETE CASCADE,
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (folder_id, comic_id)
);

CREATE TABLE IF NOT EXISTS comic_tags (
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    tag_id BIGINT REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (comic_id, tag_id)
);

CREATE TABLE IF NOT EXISTS chapters (
    id BIGSERIAL PRIMARY KEY,
    comic_id BIGINT REFERENCES comics(id) ON DELETE CASCADE,
    chapter_number NUMERIC NOT NULL,
    title TEXT,
    media_id TEXT NOT NULL,
    start_page INT NOT NULL DEFAULT 1,
    end_page INT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comics_title ON comics USING gin (title_pretty gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tags_type ON tags(type);
CREATE INDEX IF NOT EXISTS idx_comic_tags_tag ON comic_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_folder_comics_folder ON folder_comics(folder_id);
CREATE INDEX IF NOT EXISTS idx_chapters_comic_id ON chapters(comic_id);
```

### Bước 5: Khởi chạy Server
```powershell
uvicorn main:app --reload
```

Khi thấy thông báo sau là hệ thống đã sẵn sàng:
```
[INFO] Kết nối Supabase thành công và sẵn sàng phục vụ.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Mở trình duyệt truy cập: **http://localhost:8000**

---

## 📖 Tính năng nổi bật

### 1. Thư viện cá nhân thông minh (`/index.html`)
- **Quản lý Thư mục kiểu Spotify (Playlists)**: Tạo, đổi tên, xóa thư mục và phân loại truyện theo sở thích.
- **Quản lý Tác giả (Authors)**: Tự động trích xuất tác giả từ các bộ truyện đã lưu; nhấp vào tác giả để xem nhanh toàn bộ tác phẩm của họ trong thư viện.
- **Tìm kiếm nhanh**: Lọc truyện theo tên, thư mục hoặc tác giả tức thì.
- **Thêm truyện 1-Click**: Nhập ID truyện (VD: `686045`) $\rightarrow$ Xem trước $\rightarrow$ Lưu vào thư viện.

### 2. Khám phá NHentai cá nhân hóa (`/discover.html`)
- **Bộ lọc gợi ý theo gu**: Thanh bên trái tự động hiển thị danh sách **Tác giả** và **Thể loại** từ *các truyện bạn đang lưu trong thư viện*.
- **Tìm kiếm toàn cục**: Bấm vào bất kỳ tác giả/thể loại nào để tìm toàn bộ tác phẩm trên kho NHentai (`artist:"..."`, `tag:"..."`).
- **Bộ lọc 3 nấc tiện lợi**: Nhấp 1: *Chọn* $\rightarrow$ Nhấp 2: *Loại trừ* $\rightarrow$ Nhấp 3: *Bỏ chọn*.

### 3. Mô hình Chapter thống nhất (`/detail.html`)
Xử lý linh hoạt cả 2 trường hợp quản lý truyện:
- **Trường hợp 1 (Gộp nhiều bộ thành 1 truyện)**: Gộp các volume/tập truyện riêng biệt trên NHentai thành 1 bộ nhiều chapter (mỗi chapter lưu `media_id` riêng của gallery đó).
- **Trường hợp 2 (Chia 1 bộ dài thành nhiều chapter)**: Tự động chia 1 bộ truyện 200 trang thành nhiều chương nhỏ theo dải trang (1-30, 31-60...) giúp theo dõi tiến độ dễ dàng.

### 4. Trình đọc truyện mượt mà (`/reader.html`)
- **📜 Webtoon**: Cuộn dọc liên tục, tự động căn chỉnh tỷ lệ khung hình không giật layout.
- **📄 Manga**: Lật từng trang, hỗ trợ phím mũi tên ← / → và lăn chuột.
- **Smart Fallback**: Tự động chuyển đổi định dạng ảnh linh hoạt (`.webp` $\rightarrow$ `.jpg` $\rightarrow$ `.png` $\rightarrow$ `.jpeg`) đảm bảo không bị lỗi ảnh 404.

---

## 🔄 Cơ chế Sao lưu & Phục hồi thảm họa (Disaster Recovery)

- **Dữ liệu chính**: Nằm 24/7 trên **Supabase Cloud**, không bị mất khi xóa project trên máy tính hay chuyển máy mới.
- **Snapshot dự phòng (`backup.json`)**: Mỗi khi bạn thêm/xóa truyện hoặc đổi chapter, hệ thống tự động xuất bản ghi tối giản vào file `backend/data/backup.json`.
- **Tự động phục hồi khi Supabase bị xóa (sau 1-2 tháng)**:
  1. Tạo project Supabase mới.
  2. Dán mã SQL tạo bảng.
  3. Cập nhật `SUPABASE_URL` và `SUPABASE_KEY` mới vào file `.env`.
  4. Chạy server: Hệ thống tự động nhận diện database trống (`COUNT == 0`) và bơm lại 100% truyện, thư mục và chapter trong **đúng 1 giây**!

---

## 🗄️ Database Schema Summary

| Bảng | Khóa chính (PK) | Mô tả |
|---|---|---|
| `comics` | `id` (ID gốc NHentai) | Lưu 5 trường cốt lõi: `id`, `media_id`, `title_pretty`, `cover_path`, `num_pages` |
| `tags` | `id` (ID tag NHentai) | Lưu Tác giả (`type = 'artist'`) và Thể loại (`type = 'tag'`) |
| `comic_tags` | `(comic_id, tag_id)` | Bảng liên kết nhiều-nhiều giữa truyện và tags (`ON DELETE CASCADE`) |
| `folders` | `id BIGSERIAL` | Danh sách thư mục (Spotify-Style Playlists) |
| `folder_comics`| `(folder_id, comic_id)` | Bảng liên kết nhiều-nhiều giữa thư mục và truyện (`ON DELETE CASCADE`) |
| `chapters` | `id BIGSERIAL` | Danh sách chương truyện (`comic_id`, `chapter_number`, `title`, `media_id`, `start_page`, `end_page`) |

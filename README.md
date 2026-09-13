# 📚 HManga-library

Website đọc truyện tranh cá nhân — lưu trữ và đọc manga/manhwa/manhua từ nhiều nguồn (tối ưu cho NHentai).

---

## 🏗️ Kiến trúc dự án: Clean Layered Architecture

Dự án sử dụng **Kiến trúc phân tầng phẳng (Flat Layered Architecture)** tối giản, loại bỏ hoàn toàn sự cồng kềnh của Modular Monolith cũ, tối ưu hóa 100% cho **SQLite cục bộ**:

```
HManga-library/
├── backend/                       ← FastAPI (Python) — Clean Layered
│   ├── data_cache/                ← Thư mục lưu dữ liệu SQLite & Backup
│   │   ├── manga.db               ← File cơ sở dữ liệu SQLite duy nhất (tự động tạo)
│   │   └── backup.json            ← Tự động sao lưu dữ liệu dạng JSON
│   ├── database.py                ← Kết nối SQLite (get_db) & DDL tạo bảng
│   ├── models.py                  ← Pydantic schemas cho request validation
│   ├── services.py                ← Toàn bộ business logic & truy vấn SQLite
│   ├── nhentai.py                 ← Trích xuất thông tin & CDN từ NHentai
│   ├── backup.py                  ← Logic sao lưu & phục hồi database
│   ├── main.py                    ← Khởi tạo app FastAPI, static files & routes API
│   └── requirements.txt           ← Dependencies tối giản
│
├── frontend/                      ← HTML5 + Modern Dark CSS + Vanilla JS
│   ├── assets/                    ← Ảnh bìa tải về local (đặt theo gallery_id)
│   ├── index.html                 ← Trang chủ: Header đa năng + Bố cục 2 cột (Sidebar & Truyện)
│   ├── detail.html                ← Chi tiết truyện & Quản lý Chapter (Thêm/Sửa/Xóa chapter, Xóa truyện)
│   ├── reader.html                ← Trình đọc truyện (Webtoon cuộn dọc / Manga từng trang)
│   ├── backup.html                ← Trang sao lưu & phục hồi cơ sở dữ liệu
│   ├── style.css                  ← Toàn bộ stylesheet giao diện Dark Theme hiện đại
│   └── app.js                     ← API Client, Toast, Confirm modal dùng chung
└── README.md
```

| Thành phần | Công nghệ | Chi tiết |
|---|---|---|
| Frontend | HTML5 + CSS3 + Vanilla JS (Dark theme) | Tương tác mượt mà, không cần Node.js hay build tool |
| Backend | FastAPI + Uvicorn (Clean Layered) | Port `8000` (serve cả REST API và giao diện web tĩnh) |
| Database | **SQLite cục bộ (`manga.db`)** | Tự động tạo khi khởi chạy, chạy offline 100% |

---

## ⚡ Cài đặt & Chạy lần đầu (Siêu đơn giản)

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

### Bước 3: Khởi chạy Server

```powershell
uvicorn main:app --reload
```

Khi thấy thông báo sau là hệ thống đã sẵn sàng:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

### Bước 4: Mở trình duyệt

Truy cập: **http://localhost:8000** (hoặc `http://127.0.0.1:8000`)

*(Không cần cài đặt database server, không cần API key, không cần internet để đọc truyện đã lưu!)*

---

## 🔄 Sao lưu dữ liệu
Toàn bộ dữ liệu của bạn nằm trong file `backend/data_cache/manga.db` và được tự động backup ra `backend/data_cache/backup.json`:
- Sao chép file: `backend/data_cache/manga.db` (hoặc `backup.json`)
- Sao chép thư mục ảnh bìa: `frontend/assets/`

---

## 📖 Tính năng & Cách sử dụng

### 1. Trang chủ thông minh (`/index.html`)
- **Header Đa Năng:**
  - Ô tìm kiếm truyện (Live search hoặc nhấn nút Tìm / Enter).
  - Ô nhập ID truyện (VD: `524984`) + Nút **Thêm**: tự động cào thông tin, tạo Chapter 1 và tải ảnh bìa về máy ngay tức thì.
  - Nút truy cập nhanh trang Sao lưu.
- **Bố cục 2 Cột (2-Column Layout):**
  - **Cột trái (Sidebar):** Danh mục Thể loại và Tác giả kèm số lượng truyện; lọc truyện ngay chỉ với một cú nhấp chuột.
  - **Cột phải (Lưới truyện):** Hiển thị danh sách truyện, số lượng và các tag bộ lọc đang áp dụng kèm nút xóa lọc nhanh.

### 2. Đọc truyện (`/reader.html`)
- **📜 Cuộn dọc (Webtoon)**: Tải toàn bộ ảnh theo chiều dọc mượt mà.
- **📄 Từng trang (Manga)**: Xem từng ảnh, dùng phím mũi tên ← / → trên bàn phím hoặc nhấp chuột / lăn chuột.
- Nút **⇦ Chương trước** và **Chương sau ⇨** ở thanh điều hướng.

### 3. Chi tiết truyện & Quản lý chương (`/detail.html`)
- Xem thông tin truyện, tác giả, danh sách các thể loại.
- **Thêm Chapter mới**: Nhập ID của Chapter trên NHentai (VD: `592875`), hệ thống tự động đánh số và lấy link đọc.
- Chỉnh sửa số thứ tự / tiêu đề chapter hoặc xóa chapter.
- Xóa bộ truyện (tự động dọn dẹp cơ sở dữ liệu và xóa file ảnh bìa local).

### 4. Sao lưu & Phục hồi (`/backup.html`)
- Tải file sao lưu JSON về máy tính.
- Phục hồi cơ sở dữ liệu từ file sao lưu có sẵn hoặc upload file JSON lên hệ thống.


---

## 🗄️ Database Schema (SQLite)

| Bảng | Mô tả |
|---|---|
| `comics` | Thông tin bộ truyện (tên, tác giả, cover, gallery_id, source_url) |
| `genres` | Danh sách thể loại (UNIQUE name) |
| `comic_genres` | Bảng liên kết nhiều-nhiều giữa truyện và thể loại (`ON DELETE CASCADE`) |
| `chapters` | Chương truyện (`base_url` + `start_page` + `end_page`) |

---

## 💡 Cơ chế lưu trữ ảnh không tốn dung lượng

1. **Không tải toàn bộ ảnh chương về máy**.
2. Database chỉ lưu **URL trang đầu tiên** (`base_url`) và **khoảng trang** (`start_page` → `end_page`).
3. Khi đọc, frontend **render dãy URL động**:
   ```
   Trang 1: https://i.nhentai.net/galleries/4126277/1.webp
   Trang 2: https://i.nhentai.net/galleries/4126277/2.webp
   ...
   ```
4. Frontend tải ảnh trực tiếp qua CDN nguồn với `referrerpolicy="no-referrer"`.
5. **Smart Fallback**: Nếu ảnh `.webp` lỗi, tự động thử `.jpg` → `.png` → `.jpeg` → ảnh dự phòng `rem.jpg`.
6. **Chỉ ảnh bìa** được tải về local `frontend/assets/` đặt theo `gallery_id`.

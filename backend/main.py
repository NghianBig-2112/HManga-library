"""
HManga Library - Backend Entrypoint (FastAPI)
==============================================
Tập tin khởi chạy chính của ứng dụng backend FastAPI.
Nhiệm vụ:
- Khởi tạo FastAPI application và cấu hình CORS middleware.
- Đăng ký các router RESTful API cho Comics, Chapters, Images, Search, Genres, Authors.
- Cung cấp (Mount) thư mục ảnh bìa (cover images) và toàn bộ giao diện tĩnh Frontend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Import các router từ các module chức năng
from modules.comics.router import router as comics_router
from modules.chapters.router import router as chapters_router
from modules.images.router import router as images_router
from modules.search.router import router as search_router
from modules.genres.router import router as genres_router
from modules.authors.router import router as authors_router

# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="HManga Library API",
    description="API quản lý và đọc thư viện truyện cá nhân HManga",
    version="1.0.0"
)

# Cấu hình CORS Middleware cho phép gọi API từ nhiều nguồn (phù hợp khi chạy dev / local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đường dẫn thư mục giao diện tĩnh Frontend (HTML, CSS, JS, assets)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

# Đường dẫn thư mục lưu trữ ảnh bìa cục bộ (frontend/assets)
COVER_DIR = FRONTEND_DIR / "assets"
COVER_DIR.mkdir(parents=True, exist_ok=True)

# 1. Đăng ký các API Routers
app.include_router(comics_router)      # API quản lý truyện (danh sách, chi tiết, thêm, xóa)
app.include_router(chapters_router)    # API quản lý chapter truyện
app.include_router(images_router)      # API giải mã URL ảnh & proxy ảnh tránh chặn referrer
app.include_router(search_router)      # API tìm kiếm nâng cao theo tên, tác giả, thể loại
app.include_router(genres_router)      # API quản lý thể loại (genres)
app.include_router(authors_router)     # API quản lý tác giả

# 2. Mount thư mục tĩnh phục vụ xem ảnh bìa cục bộ (/api/covers/{filename})
app.mount("/api/covers", StaticFiles(directory=str(COVER_DIR)), name="covers")

# 3. Mount thư mục tĩnh cho toàn bộ giao diện Frontend (/ -> index.html, style.css, ...)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

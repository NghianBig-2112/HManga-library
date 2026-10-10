"""
HManga Library - Web API Server (FastAPI)
uvicorn main:app --reload
=========================================
Cổng giao tiếp duy nhất giữa Frontend và Backend.
"""

from typing import Optional, List
from pathlib import Path
import requests
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import init_db
import services
import backup
from nhentai import fetch_comic_from_nhentai

# 1. Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="HManga Library API",
    description="Hệ thống quản lý và đọc truyện tranh NHentai cá nhân",
    version="1.0.0"
)

# 2. Cấu hình CORS để Frontend kết nối thoải mái
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Tự động kiểm tra/tạo bảng CSDL khi Server khởi động
@app.on_event("startup")
def on_startup():
    init_db(reset=False)


# ==================== PYDANTIC SCHEMAS (ĐẦU VÀO) ====================

class ComicAddRequest(BaseModel):
    gallery_id: int
    folder_id: Optional[int] = 1

class ChapterSplitItem(BaseModel):
    title: str
    start_page: int
    end_page: int
    chapter_number: Optional[float] = None

class ComicSplitRequest(BaseModel):
    chapters: List[ChapterSplitItem]

class ChapterAddRequest(BaseModel):
    gallery_id: int
    title: Optional[str] = None
    chapter_number: Optional[float] = None

class FolderCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""

class ComicFolderUpdateRequest(BaseModel):
    folder_id: int

# ==================== COMICS ROUTES ====================
@app.get("/api/comics", summary="Lấy danh sách truyện ở Trang chủ (12 bộ / trang)")
def get_comics(
    folder_id: Optional[int] = Query(None, description="Lọc theo ID thư mục"),
    artist_id: Optional[int] = Query(None, description="Lọc theo ID tác giả"),
    page: int = Query(1, ge=1, description="Số trang hiện tại (bắt đầu từ 1)"),
    limit: int = Query(12, ge=1, le=100, description="Số lượng truyện mỗi trang (mặc định 12)")
):
    """Lấy danh sách truyện trong thư viện có phân trang 12 bộ mới nhất và hỗ trợ lọc."""
    return services.get_all_comics(folder_id=folder_id, artist_id=artist_id, page=page, limit=limit)


@app.get("/api/comics/check/{gallery_id}", summary="Kiểm tra ID và tên truyện trước khi thêm")
def check_comic(gallery_id: int):
    """Kiểm tra ID trong Supabase trước, nếu không có thì tìm trên NHentai và kiểm tra trùng title_pretty."""
    try:
        return services.check_comic_before_add(gallery_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/comics/{comic_id}", summary="Lấy chi tiết 1 bộ truyện")
def get_comic(comic_id: int):
    """Lấy thông tin chi tiết của truyện kèm tác giả, thể loại và danh sách các tập."""
    comic = services.get_comic_detail(comic_id)
    if not comic:
        raise HTTPException(status_code=404, detail="Không tìm thấy truyện trong thư viện!")
    return comic


@app.post("/api/comics", summary="Thêm truyện mới từ NHentai bằng ID")
def add_comic(data: ComicAddRequest):
    """Nhận Gallery ID, tự động cào dữ liệu và lưu vào thư viện."""
    try:
        result = services.add_comic_by_gallery_id(
            gallery_id=data.gallery_id,
            folder_id=data.folder_id or 1
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/comics/{comic_id}", summary="Xóa 1 bộ truyện khỏi thư viện")
def delete_comic(comic_id: int):
    """Xóa truyện và tự động dọn dẹp chapters, tags liên quan."""
    success = services.delete_comic(comic_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bộ truyện không tồn tại để xóa!")
    return {"status": "success", "message": f"Đã xóa thành công truyện ID {comic_id}"}

@app.put("/api/comics/{comic_id}/folder", summary="Đổi thư mục của 1 bộ truyện")
def change_comic_folder(comic_id: int, data: ComicFolderUpdateRequest):
    """Cập nhật thư mục (folder_id) cho bộ truyện."""
    try:
        updated = services.update_comic_folder(comic_id=comic_id, folder_id=data.folder_id)
        return {"status": "success", "comic": updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== CHAPTERS ROUTES ====================

@app.post("/api/comics/{comic_id}/split", summary="Chia nhỏ chương thủ công theo ý người dùng")
def split_chapters(comic_id: int, data: ComicSplitRequest):
    """Nhận danh sách các hồi do người dùng tự nhập mốc trang và lưu vào CSDL."""
    try:
        # Chuyển đổi danh sách Pydantic items thành list dictionary thuần
        chapters_data = [item.dict() for item in data.chapters]
        created_chapters = services.split_comic_into_chapters(comic_id, chapters_data)
        return {
            "status": "success",
            "comic_id": comic_id,
            "total_chapters": len(created_chapters),
            "chapters": created_chapters
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/comics/{comic_id}/chapters", summary="Thêm chapter từ một Gallery ID khác (Series nhiều phần)")
def add_chapter(comic_id: int, data: ChapterAddRequest):
    """Thêm một tập mới từ Gallery ID NHentai khác vào bộ truyện cha có sẵn."""
    try:
        created_chapter = services.add_chapter_from_gallery_id(
            comic_id=comic_id,
            gallery_id=data.gallery_id,
            chapter_number=data.chapter_number,
            title=data.title
        )
        return {"status": "success", "chapter": created_chapter}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/chapters/{chapter_id}/pages", summary="Lấy danh sách link ảnh để đọc online")
def get_chapter_pages(chapter_id: int):
    """Trả về danh sách tất cả các trang ảnh của chapter để trình đọc hiển thị."""
    pages = services.get_chapter_pages(chapter_id)
    if not pages:
        raise HTTPException(status_code=404, detail="Chapter không tồn tại hoặc không có trang nào!")
    return pages


# ==================== IMAGE PROXY (VƯỢT CHẶN NHÀ MẠNG) ====================

@app.get("/api/image-proxy", summary="Trung chuyển ảnh từ CDN để vượt tường lửa nhà mạng")
def image_proxy(url: str = Query(..., description="URL ảnh gốc từ CDN nhentai")):
    """
    Tải byte ảnh từ máy chủ CDN nhentai về RAM và trả trực tiếp cho trình duyệt.
    Không lưu bất kỳ file nào ra ổ cứng, vượt qua hoàn toàn bộ chặn của ISP Việt Nam.
    """
    if "nhentai.net" not in url:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ proxy ảnh từ nhentai.net!")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://nhentai.net/"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Không thể tải ảnh từ CDN!")

        media_type = resp.headers.get("Content-Type", "image/jpeg")
        return Response(content=resp.content, media_type=media_type)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối tải ảnh: {str(e)}")

@app.post("/api/folders", summary="Tạo thư mục mới")
def add_folder(data: FolderCreateRequest):
    try:
        return services.create_folder(name=data.name, description=data.description or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/folders", summary="Lấy danh sách thư mục")
def get_folders():
    return services.get_all_folders()

@app.put("/api/folders/{folder_id}", summary="Đổi tên thư mục")
def update_folder(folder_id: int, data: FolderCreateRequest):
    try:
        return services.rename_folder(
            folder_id=folder_id,
            new_name=data.name,
            description=data.description or ""
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/folders/{folder_id}", summary="Xóa thư mục")
def remove_folder(folder_id: int):
    try:
        services.delete_folder(folder_id=folder_id)
        return {"status": "success", "message": f"Đã xóa thư mục ID {folder_id}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/authors", summary="Lấy danh sách tác giả")
def get_authors():
    return services.get_all_authors()

@app.get("/api/nhentai/{gallery_id}", summary="Lấy trực tiếp dữ liệu từ nhentai.py bằng ID")
def get_nhentai_gallery(gallery_id: int):
    """Lấy dữ liệu truyện trực tiếp từ NHentai bằng hàm fetch_comic_from_nhentai."""
    try:
        data = fetch_comic_from_nhentai(gallery_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== BACKUP & RESTORE ROUTES ====================

@app.post("/api/backup", summary="Sao lưu toàn bộ dữ liệu từ Supabase ra file backup.json")
def backup_library():
    try:
        filepath = backup.save_backup_file()
        return {"status": "success", "filepath": filepath}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/restore", summary="Khôi phục toàn bộ dữ liệu từ file backup.json lên Supabase")
def restore_library():
    try:
        return backup.restore_backup_from_file()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== HÌNH NỀN & MOUNT FRONTEND ====================

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

# Điền đường dẫn thư mục chứa ảnh nền của bạn vào đây (có chữ r ở trước dấu ngoặc kép):
CUSTOM_BG_DIR = Path(r"D:\Anime\Twitter")

# Nếu thư mục trên tồn tại thì lấy ảnh ở đó, nếu không thì tự động lùi về frontend/assets
BACKGROUND_DIR = CUSTOM_BG_DIR if CUSTOM_BG_DIR.exists() else (FRONTEND_DIR / "assets")


@app.get("/api/backgrounds", summary="Lấy danh sách các file ảnh nền")
def get_backgrounds():
    """Tự động quét tất cả file ảnh trong thư mục BACKGROUND_DIR."""
    if not BACKGROUND_DIR.exists():
        return []

    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    files = [
        f.name for f in BACKGROUND_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in valid_exts and f.name.lower() != "rem.jpg"
    ]
    files.sort()
    return files


# 1. Mount thư mục ảnh nền vào đường dẫn /backgrounds (Đặt TRƯỚC khi mount "/")
if BACKGROUND_DIR.exists():
    app.mount("/backgrounds", StaticFiles(directory=str(BACKGROUND_DIR)), name="backgrounds")

# 2. Mount giao diện Frontend vào "/"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
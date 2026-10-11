"""
HManga Library - Web API Server (FastAPI)
=========================================
Lệnh khởi chạy: uvicorn main:app --reload

Đóng vai trò là cổng giao tiếp duy nhất giữa giao diện Frontend và các module Backend:
1. Tự động kiểm tra/khởi tạo bảng CSDL trên Supabase khi khởi động server.
2. Cung cấp hệ thống REST API quản lý Truyện, Chapter, Thư mục, Tác giả.
3. Cung cấp In-Memory Image Proxy (/api/image-proxy) để vượt tường lửa nhà mạng mà không tốn dung lượng ổ cứng.
4. Hỗ trợ Sao lưu & Khôi phục dữ liệu (backup.json) trực tiếp từ giao diện web.
5. Phục vụ trực tiếp các trang giao diện tĩnh (HTML/CSS/JS) và ảnh nền từ thư mục `frontend/`.
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


# ==================== 1. KHỞI TẠO FASTAPI & CẤU HÌNH HỆ THỐNG ====================

app = FastAPI(
    title="HManga Library API",
    description="Hệ thống quản lý và đọc truyện tranh NHentai cá nhân",
    version="1.0.0"
)

# Cấu hình CORS cho phép Frontend (kể cả khi mở bằng Live Server hoặc file rời) gọi API không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tự động kiểm tra và tạo bảng CSDL trên Supabase ngay khi Server vừa bật lên (không xóa dữ liệu cũ)
@app.on_event("startup")
def on_startup():
    init_db(reset=False)


# ==================== 2. ĐỊNH NGHĨA DỮ LIỆU ĐẦU VÀO (PYDANTIC SCHEMAS) ====================

class ComicAddRequest(BaseModel):
    """Dữ liệu gửi lên khi thêm bộ truyện mới vào thư viện."""
    gallery_id: int
    folder_id: Optional[int] = 1

class ChapterSplitItem(BaseModel):
    """Thông tin 1 hồi/chương khi người dùng chia nhỏ truyện dài."""
    title: str
    start_page: int
    end_page: int
    chapter_number: Optional[float] = None

class ComicSplitRequest(BaseModel):
    """Danh sách các hồi/chương dùng cho API chia nhỏ truyện."""
    chapters: List[ChapterSplitItem]

class ChapterAddRequest(BaseModel):
    """Dữ liệu gửi lên khi gộp thêm 1 phần mới (từ Gallery ID khác) làm Chapter tiếp theo."""
    gallery_id: int
    title: Optional[str] = None
    chapter_number: Optional[float] = None

class FolderCreateRequest(BaseModel):
    """Dữ liệu gửi lên khi tạo mới hoặc đổi tên thư mục."""
    name: str
    description: Optional[str] = ""

class ComicFolderUpdateRequest(BaseModel):
    """Dữ liệu gửi lên khi chuyển bộ truyện sang thư mục khác."""
    folder_id: int


# ==================== 3. NHÓM API QUẢN LÝ TRUYỆN (COMICS ROUTES) ====================

@app.get("/api/comics", summary="Lấy danh sách truyện ở Trang chủ (12 bộ / trang)")
def get_comics(
    folder_id: Optional[int] = Query(None, description="Lọc theo ID thư mục"),
    artist_id: Optional[int] = Query(None, description="Lọc theo ID tác giả"),
    page: int = Query(1, ge=1, description="Số trang hiện tại (bắt đầu từ 1)"),
    limit: int = Query(12, ge=1, le=100, description="Số lượng truyện mỗi trang (mặc định 12)")
):
    """Lấy danh sách truyện trong thư viện có phân trang (12 bộ mới nhất/trang) và hỗ trợ lọc theo Thư mục, Tác giả."""
    return services.get_all_comics(folder_id=folder_id, artist_id=artist_id, page=page, limit=limit)


@app.get("/api/comics/check/{gallery_id}", summary="Kiểm tra ID và tên truyện trước khi thêm")
def check_comic(gallery_id: int):
    """
    Kiểm tra khi người dùng bấm nút 'Tìm' ở Trang chủ:
    - Kiểm tra trùng ID trong Supabase trước.
    - Nếu chưa có ID, lấy dữ liệu từ NHentai và kiểm tra trùng tên truyện (`title_pretty`).
    """
    try:
        return services.check_comic_before_add(gallery_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/comics/{comic_id}", summary="Lấy chi tiết 1 bộ truyện")
def get_comic(comic_id: int):
    """Lấy đầy đủ thông tin chi tiết của truyện kèm tác giả, thể loại, danh sách chapter và link ảnh xem trước."""
    comic = services.get_comic_detail(comic_id)
    if not comic:
        raise HTTPException(status_code=404, detail="Không tìm thấy truyện trong thư viện!")
    return comic


@app.post("/api/comics", summary="Thêm truyện mới từ NHentai bằng ID")
def add_comic(data: ComicAddRequest):
    """Nhận Gallery ID và Folder ID, tự động cào dữ liệu từ NHentai và lưu vào thư viện."""
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
    """Xóa bộ truyện khỏi CSDL và tự động dọn dẹp toàn bộ chapters, liên kết tác giả/thể loại liên quan."""
    success = services.delete_comic(comic_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bộ truyện không tồn tại để xóa!")
    return {"status": "success", "message": f"Đã xóa thành công truyện ID {comic_id}"}


@app.put("/api/comics/{comic_id}/folder", summary="Đổi thư mục của 1 bộ truyện")
def change_comic_folder(comic_id: int, data: ComicFolderUpdateRequest):
    """Cập nhật thư mục (`folder_id`) mới cho bộ truyện khi người dùng chọn ở trang Chi tiết."""
    try:
        updated = services.update_comic_folder(comic_id=comic_id, folder_id=data.folder_id)
        return {"status": "success", "comic": updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== 4. NHÓM API QUẢN LÝ CHƯƠNG/TẬP (CHAPTERS ROUTES) ====================

@app.post("/api/comics/{comic_id}/split", summary="Chia nhỏ chương thủ công theo mốc trang")
def split_chapters(comic_id: int, data: ComicSplitRequest):
    """Nhận danh sách các chương cùng khoảng trang (`start_page` -> `end_page`) do người dùng nhập và lưu vào CSDL."""
    try:
        # Chuyển đổi danh sách Pydantic models sang list dictionary thuần để truyền vào tầng services
        chapters_data = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in data.chapters]
        created_chapters = services.split_comic_into_chapters(comic_id, chapters_data)
        return {
            "status": "success",
            "comic_id": comic_id,
            "total_chapters": len(created_chapters),
            "chapters": created_chapters
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/comics/{comic_id}/chapters", summary="Gộp thêm chapter mới từ một Gallery ID khác")
def add_chapter(comic_id: int, data: ChapterAddRequest):
    """Lấy dữ liệu từ một Gallery ID NHentai khác và gắn làm Chapter mới cho bộ truyện hiện tại (dùng cho Series nhiều phần)."""
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
    """Trả về danh sách đường dẫn ảnh của từng trang trong Chapter để trình đọc (`reader.html`) hiển thị."""
    pages = services.get_chapter_pages(chapter_id)
    if not pages:
        raise HTTPException(status_code=404, detail="Chapter không tồn tại hoặc không có trang nào!")
    return pages


# ==================== 5. TRUNG CHUYỂN ẢNH QUA RAM (IN-MEMORY IMAGE PROXY) ====================

@app.get("/api/image-proxy", summary="Trung chuyển ảnh từ CDN để vượt tường lửa nhà mạng")
def image_proxy(url: str = Query(..., description="URL ảnh gốc từ CDN nhentai")):
    """
    Tải dữ liệu byte của ảnh từ máy chủ CDN NHentai vào bộ nhớ RAM (kèm header Referer hợp lệ)
    và trả trực tiếp về cho trình duyệt.
    Giải pháp này giúp vượt chặn ISP và chống lỗi 403 Hotlink mà không cần lưu bất kỳ file ảnh nào xuống ổ cứng.
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


# ==================== 6. NHÓM API THƯ MỤC, TÁC GIẢ & TRA CỨU TRỰC TIẾP ====================

@app.post("/api/folders", summary="Tạo thư mục mới")
def add_folder(data: FolderCreateRequest):
    """Tạo một thư mục phân loại truyện mới."""
    try:
        return services.create_folder(name=data.name, description=data.description or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/folders", summary="Lấy danh sách thư mục")
def get_folders():
    """Lấy toàn bộ danh sách thư mục hiện có trong CSDL."""
    return services.get_all_folders()


@app.put("/api/folders/{folder_id}", summary="Đổi tên thư mục")
def update_folder(folder_id: int, data: FolderCreateRequest):
    """Đổi tên thư mục theo ID (không áp dụng cho thư mục Mặc định ID = 1)."""
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
    """Xóa thư mục và tự động chuyển các truyện bên trong về thư mục Mặc định (ID = 1)."""
    try:
        services.delete_folder(folder_id=folder_id)
        return {"status": "success", "message": f"Đã xóa thư mục ID {folder_id}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/authors", summary="Lấy danh sách tác giả")
def get_authors():
    """Lấy danh sách các tác giả đang có truyện trong thư viện để hiển thị lên bộ lọc."""
    return services.get_all_authors()


@app.get("/api/nhentai/{gallery_id}", summary="Lấy trực tiếp dữ liệu từ NHentai bằng ID")
def get_nhentai_gallery(gallery_id: int):
    """Tra cứu trực tiếp thông tin truyện từ NHentai API v2 mà không lưu vào CSDL."""
    try:
        data = fetch_comic_from_nhentai(gallery_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== 7. NHÓM API SAO LƯU & KHÔI PHỤC (BACKUP & RESTORE) ====================

@app.post("/api/backup", summary="Sao lưu toàn bộ dữ liệu từ Supabase ra file backup.json")
def backup_library():
    """Xuất toàn bộ dữ liệu từ 7 bảng trên Supabase ra file `backup.json` ở thư mục gốc."""
    try:
        filepath = backup.save_backup_file()
        return {"status": "success", "filepath": filepath}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/restore", summary="Khôi phục toàn bộ dữ liệu từ file backup.json lên Supabase")
def restore_library():
    """Đọc file `backup.json` ở thư mục gốc và nạp lại toàn bộ dữ liệu lên Supabase."""
    try:
        return backup.restore_backup_from_file()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== 8. QUẢN LÝ HÌNH NỀN & PHỤC VỤ GIAO DIỆN FRONTEND ====================

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
BACKGROUND_DIR = FRONTEND_DIR / "assets"


@app.get("/api/backgrounds", summary="Lấy danh sách các file ảnh nền trong frontend/assets")
def get_backgrounds():
    """
    Tự động quét tất cả file ảnh hợp lệ (.jpg, .jpeg, .png, .webp, .gif) trong thư mục `frontend/assets`
    (ngoại trừ ảnh logo `rem.jpg`) để người dùng chọn làm hình nền trên giao diện.
    """
    if not BACKGROUND_DIR.exists():
        return []

    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    files = [
        f.name for f in BACKGROUND_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in valid_exts and f.name.lower() != "rem.jpg"
    ]
    files.sort()
    return files


# Mount toàn bộ thư mục `frontend` vào đường dẫn gốc "/" (đặt ở cuối file để không che khuất các route /api/...)
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
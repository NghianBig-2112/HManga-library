"""
Comics Router Module
====================
Định nghĩa các endpoint RESTful API quản lý bộ truyện tranh (/api/comics):
- GET /api/comics: Lấy danh sách truyện (hỗ trợ lọc theo thể loại và tìm kiếm tên).
- GET /api/comics/{id}: Lấy chi tiết bộ truyện kèm danh sách chapters.
- POST /api/comics: Tạo bộ truyện mới kèm gán thể loại.
- PUT /api/comics/{id}: Chỉnh sửa thông tin bộ truyện.
- DELETE /api/comics/{id}: Xóa bộ truyện và file ảnh bìa liên quan.
- GET /api/comics/check/{gallery_id}: Kiểm tra bộ truyện đã có trong thư viện chưa theo gallery_id.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from modules.comics.schemas import ComicCreate, ComicUpdate, ComicResponse, ComicDetailResponse
import modules.comics.service as service

router = APIRouter(prefix="/api/comics", tags=["comics"])

@router.get("", response_model=List[ComicResponse])
def get_comics(genre: Optional[str] = None, q: Optional[str] = None):
    """
    API lấy danh sách toàn bộ truyện trong thư viện:
    - genre: Lọc theo tên thể loại (VD: ?genre=Action)
    - q: Tìm kiếm theo từ khóa tên truyện (VD: ?q=one+piece)
    """
    return service.get_all_comics(genre=genre, q=q)

@router.get("/{comic_id}", response_model=ComicDetailResponse)
def get_comic(comic_id: str):
    """
    API lấy thông tin chi tiết của 1 bộ truyện theo ID (kèm chapters và genres).
    Hỗ trợ cả ID số nguyên (VD: 5) hoặc mã Gallery ID (VD: '001-48410').
    """
    comic = service.get_comic_detail(comic_id)
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    return comic

@router.post("", response_model=ComicDetailResponse)
def create_comic(comic: ComicCreate):
    """
    API tạo mới một bộ truyện:
    - Nhận vào: title, author, genres[], source_url, gallery_id
    - Tự động gán/tạo thể loại trong database.
    """
    return service.create_comic(comic)

@router.put("/{comic_id}", response_model=ComicDetailResponse)
def update_comic(comic_id: str, comic: ComicUpdate):
    """
    API cập nhật thông tin bộ truyện theo ID hoặc gallery_id.
    """
    updated = service.update_comic(comic_id, comic)
    if not updated:
        raise HTTPException(status_code=404, detail="Comic not found to update")
    return updated

@router.delete("/{comic_id}")
def delete_comic(comic_id: str):
    """
    API xóa bộ truyện khỏi hệ thống (cascade xóa chapters, liên kết thể loại và file bìa local).
    Hỗ trợ cả ID số nguyên (VD: 5) hoặc mã Gallery ID (VD: '001-48410').
    """
    success = service.delete_comic(comic_id)
    if not success:
        raise HTTPException(status_code=404, detail="Comic not found to delete")
    return {"message": "Comic deleted successfully"}

@router.get("/check/{gallery_id}")
def check_comic_exists(gallery_id: str):
    """
    API kiểm tra xem truyện đã tồn tại trong thư viện chưa thông qua gallery_id.
    - Trả về: { exists: true, comic: {...} } nếu đã có.
    - Trả về: { exists: false } nếu chưa có.
    """
    comic = service.check_comic_by_gallery_id(gallery_id)
    if comic:
        return {"exists": True, "comic": comic}
    return {"exists": False}

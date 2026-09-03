"""
Genres Router Module
====================
Định nghĩa các endpoint RESTful API quản lý Thể loại (/api/genres):
- GET /api/genres: Lấy danh sách toàn bộ thể loại kèm số lượng truyện (`comic_count`).
- POST /api/genres: Tạo thể loại mới.
- PUT /api/genres/{id}: Đổi tên thể loại.
- DELETE /api/genres/{id}: Xóa thể loại khỏi hệ thống.
- GET /api/genres/{id}/comics: Lấy danh sách các bộ truyện thuộc thể loại.
"""

from fastapi import APIRouter, HTTPException
from typing import List
from modules.genres.schemas import GenreCreate, GenreUpdate, GenreResponse
from modules.comics.schemas import ComicResponse
import modules.genres.service as service

router = APIRouter(prefix="/api/genres", tags=["genres"])

@router.get("", response_model=List[GenreResponse])
def get_genres():
    """API lấy danh sách toàn bộ thể loại kèm số lượng truyện của từng thể loại"""
    return service.get_all_genres()

@router.post("", response_model=GenreResponse)
def create_genre(data: GenreCreate):
    """API tạo thêm một thể loại mới"""
    genre = service.create_genre(data.name)
    if not genre:
        raise HTTPException(status_code=400, detail="Failed to create genre")
    return genre

@router.put("/{genre_id}", response_model=GenreResponse)
def update_genre(genre_id: int, data: GenreUpdate):
    """API đổi tên thể loại theo ID. Trả về 404 nếu không tìm thấy ID."""
    updated = service.update_genre(genre_id, data.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Genre not found")
    return updated

@router.delete("/{genre_id}")
def delete_genre(genre_id: int):
    """API xóa thể loại khỏi hệ thống và gỡ liên kết khỏi các bộ truyện"""
    service.delete_genre(genre_id)
    return {"message": "Genre deleted successfully"}

@router.get("/{genre_id}/comics", response_model=List[ComicResponse])
def get_comics_by_genre(genre_id: int):
    """API lấy danh sách tất cả các bộ truyện thuộc về một thể loại cụ thể"""
    return service.get_comics_by_genre_id(genre_id)

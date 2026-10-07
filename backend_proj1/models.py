"""
Pydantic Models
===============
Tất cả schema request/response cho API (Supabase & Unified Chapter Model).
"""

from typing import Optional, List
from pydantic import BaseModel


# ==================== COMICS ====================

class ComicAddByIdRequest(BaseModel):
    gallery_id: int
    folder_id: Optional[int] = None
    pages_per_chapter: Optional[int] = None


class SaveFavoriteToLibraryRequest(BaseModel):
    gallery_id: int
    folder_id: Optional[int] = None
    pages_per_chapter: Optional[int] = None


# ==================== CHAPTERS & SEGMENTATION ====================

class ChapterAddByIdRequest(BaseModel):
    gallery_id: int
    chapter_number: Optional[float] = None
    title: Optional[str] = None


class ChapterCreateInternal(BaseModel):
    chapter_number: float
    title: Optional[str] = None
    media_id: Optional[str] = None
    start_page: int = 1
    end_page: int


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    chapter_number: Optional[float] = None
    media_id: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None


class SplitChapterRequest(BaseModel):
    pages_per_chapter: int  # Số trang cho mỗi chapter (VD: 30)


class CustomChapterRange(BaseModel):
    chapter_number: float
    title: Optional[str] = None
    media_id: Optional[str] = None
    start_page: int
    end_page: int


class CustomSplitChapterRequest(BaseModel):
    chapters: List[CustomChapterRange]


# ==================== FOLDERS (SPOTIFY-STYLE) ====================

class FolderCreate(BaseModel):
    name: str
    description: Optional[str] = ""


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class FolderAddComicRequest(BaseModel):
    comic_id: int

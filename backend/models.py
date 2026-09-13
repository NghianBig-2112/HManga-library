"""
Pydantic Models
===============
Tất cả schema request/response cho API.
"""

from typing import Optional
from pydantic import BaseModel


# ==================== COMICS ====================

class ComicAddByIdRequest(BaseModel):
    gallery_id: int


# ==================== CHAPTERS ====================

class ChapterAddByIdRequest(BaseModel):
    gallery_id: int
    chapter_number: Optional[float] = None
    title: Optional[str] = None


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    chapter_number: Optional[float] = None
    base_url: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None


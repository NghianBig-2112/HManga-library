"""
HManga Library - Backend (FastAPI)
===================================
Tất cả routes API và cấu hình server.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from database import init_db
from models import (
    ComicAddByIdRequest,
    ChapterAddByIdRequest, ChapterCreateInternal, ChapterUpdate,
)
import services

# Khởi tạo database & Tự động phục hồi nếu có file backup.json
init_db()
services.auto_restore_if_empty()

# Khởi tạo app
app = FastAPI(title="HManga Library API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== COMICS ====================

@app.get("/api/comics")
def get_comics(genre: str = None, q: str = None, author: str = None):
    return services.get_all_comics(genre=genre, q=q, author=author)


@app.get("/api/comics/preview/{gallery_id}")
def preview_comic(gallery_id: int):
    return services.preview_comic_by_id(gallery_id)


@app.get("/api/comics/{comic_id}")
def get_comic(comic_id: int):
    result = services.get_comic_detail(comic_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comic not found")
    return result


@app.post("/api/comics/add-by-id")
async def add_comic_by_id(data: ComicAddByIdRequest):
    return await services.create_comic_by_id(data.gallery_id)


@app.delete("/api/comics/{comic_id}")
def delete_comic(comic_id: int):
    success = services.delete_comic(comic_id)
    if not success:
        raise HTTPException(status_code=404, detail="Comic not found")
    return {"message": "Comic deleted successfully"}


# ==================== CHAPTERS ====================

@app.post("/api/comics/{comic_id}/chapters/add-by-id")
def add_chapter_by_id(comic_id: int, data: ChapterAddByIdRequest):
    return services.create_chapter_by_id(
        comic_id, data.gallery_id,
        chapter_number=data.chapter_number,
        title=data.title
    )


@app.post("/api/comics/{comic_id}/chapters")
def add_chapter_internal(comic_id: int, data: ChapterCreateInternal):
    return services.create_chapter_from_comic(comic_id, data)


@app.get("/api/chapters/{chapter_id}")
def get_chapter(chapter_id: int):
    result = services.get_chapter_by_id(chapter_id)
    if not result:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return result


@app.put("/api/chapters/{chapter_id}")
def update_chapter(chapter_id: int, data: ChapterUpdate):
    result = services.update_chapter(chapter_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return result


@app.delete("/api/chapters/{chapter_id}")
def delete_chapter(chapter_id: int):
    services.delete_chapter(chapter_id)
    return {"message": "Chapter deleted successfully"}


@app.get("/api/chapters/{chapter_id}/pages")
def get_chapter_pages(chapter_id: int):
    return services.generate_pages(chapter_id)


# ==================== GENRES ====================

@app.get("/api/genres")
def get_genres():
    return services.get_all_genres()


@app.get("/api/genres/{genre_id}/comics")
def get_comics_by_genre(genre_id: int):
    return services.get_comics_by_genre_id(genre_id)


# ==================== AUTHORS ====================

@app.get("/api/authors")
def get_authors():
    return services.get_all_authors()


@app.get("/api/authors/{author_name}/comics")
def get_comics_by_author(author_name: str):
    return services.get_comics_by_author(author_name)


# ==================== SEARCH ====================

@app.get("/api/search")
def search(q: str = None, genre: str = None, author: str = None):
    return services.search_comics(q=q, genre=genre, author=author)


# ==================== NHENTAI EXPLORE & ONLINE ====================

@app.get("/api/nhentai/explore")
def nhentai_explore(page: int = 1, sort: str = "date", q: str = None):
    return services.get_nhentai_explore_service(page=page, sort=sort, q=q)


@app.get("/api/nhentai/gallery/{gallery_id}/pages")
def nhentai_gallery_pages(gallery_id: int):
    return services.get_nhentai_online_gallery_service(gallery_id)


# ==================== STATIC FILES ====================

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

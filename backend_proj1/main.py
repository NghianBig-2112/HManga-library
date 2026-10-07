"""
HManga Library - Backend (FastAPI with Supabase)
================================================
Tất cả routes API và cấu hình server.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from database import init_db
from models import (
    ComicAddByIdRequest,
    SaveFavoriteToLibraryRequest,
    ChapterAddByIdRequest, ChapterCreateInternal, ChapterUpdate,
    SplitChapterRequest, CustomSplitChapterRequest,
    FolderCreate, FolderUpdate, FolderAddComicRequest,
)
import services

# Khởi tạo database & Tự động phục hồi nếu có file backup.json
init_db()
services.auto_restore_if_empty()

# Khởi tạo app
app = FastAPI(title="HManga Library API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== COMICS ====================

@app.get("/api/comics")
def get_comics(q: str = None, author_id: int = None, folder_id: int = None):
    return services.get_all_comics(folder_id=folder_id, author_id=author_id, q=q)


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
    return await services.create_comic_by_id(
        data.gallery_id,
        folder_id=data.folder_id,
        pages_per_chapter=data.pages_per_chapter
    )


@app.post("/api/comics/save-from-favorite")
async def save_from_favorite(data: SaveFavoriteToLibraryRequest):
    return await services.create_comic_by_id(
        data.gallery_id,
        folder_id=data.folder_id,
        pages_per_chapter=data.pages_per_chapter
    )


@app.post("/api/comics/{comic_id}/split-chapters")
def split_comic_chapters(comic_id: int, data: SplitChapterRequest):
    return services.split_comic_chapters(comic_id, data.pages_per_chapter)


@app.post("/api/comics/{comic_id}/custom-split-chapters")
def custom_split_comic_chapters(comic_id: int, data: CustomSplitChapterRequest):
    return services.custom_split_comic_chapters(comic_id, [c.model_dump() for c in data.chapters])


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


# ==================== AUTHORS (QUẢN LÝ TÁC GIẢ) ====================

@app.get("/api/authors")
def get_authors():
    return services.get_all_authors()


@app.get("/api/authors/{author_id}/comics")
def get_comics_by_author(author_id: str):
    return services.get_comics_by_author(author_id)


# ==================== DISCOVER FILTERS (TÁC GIẢ & THỂ LOẠI TỪ THƯ VIỆN) ====================

@app.get("/api/discover/filters")
def get_discover_filters():
    return services.get_saved_tags_for_discover()


# ==================== SEARCH ====================

@app.get("/api/search")
def search(q: str = None, author_id: int = None, folder_id: int = None):
    return services.search_comics(q=q, author_id=author_id, folder_id=folder_id)


# ==================== FOLDERS (SPOTIFY-STYLE) ====================

@app.get("/api/folders")
def get_folders():
    return services.get_all_folders()


@app.post("/api/folders")
def create_folder(data: FolderCreate):
    return services.create_folder(data.name, data.description)


@app.put("/api/folders/{folder_id}")
def update_folder(folder_id: int, data: FolderUpdate):
    return services.update_folder(folder_id, data.name, data.description)


@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: int):
    return services.delete_folder(folder_id)


@app.post("/api/folders/{folder_id}/comics")
def add_comic_to_folder(folder_id: int, data: FolderAddComicRequest):
    return services.add_comic_to_folder(folder_id, data.comic_id)


@app.delete("/api/folders/{folder_id}/comics/{comic_id}")
def remove_comic_from_folder(folder_id: int, comic_id: int):
    return services.remove_comic_from_folder(folder_id, comic_id)


# ==================== NHENTAI EXPLORE & ONLINE ====================

@app.get("/api/nhentai/explore")
def nhentai_explore(page: int = 1, sort: str = "date", q: str = None):
    return services.get_nhentai_explore_service(page=page, sort=sort, q=q)


@app.get("/api/nhentai/gallery/{gallery_id}/pages")
def nhentai_gallery_pages(gallery_id: int):
    return services.get_nhentai_online_gallery_service(gallery_id)


@app.get("/api/nhentai/image-proxy")
def nhentai_image_proxy(url: str):
    data, media_type = services.get_nhentai_image_proxy_service(url)
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
        }
    )


@app.get("/api/nhentai/favorites")
def nhentai_favorites(page: int = 1, q: str = None):
    return services.get_nhentai_favorites_service(page=page, q=q)


@app.post("/api/nhentai/gallery/{gallery_id}/favorite")
def nhentai_add_favorite(gallery_id: int):
    return services.add_nhentai_favorite_service(gallery_id)


@app.delete("/api/nhentai/gallery/{gallery_id}/favorite")
def nhentai_remove_favorite(gallery_id: int):
    return services.remove_nhentai_favorite_service(gallery_id)


@app.get("/api/nhentai/gallery/{gallery_id}/favorite")
def nhentai_check_favorite(gallery_id: int):
    return services.check_nhentai_favorite_service(gallery_id)


@app.get("/api/nhentai/status")
def nhentai_status():
    return services.get_nhentai_api_status_service()


# ==================== STATIC FILES ====================

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

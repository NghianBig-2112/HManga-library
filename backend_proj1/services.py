"""
Services Module (Supabase PostgreSQL)
=====================================
Toàn bộ business logic cho Comics, Chapters, Tags (Tác giả & Thể loại), Folders.
"""

import math
import urllib.parse
from pathlib import Path
from fastapi import HTTPException

from database import get_supabase
from nhentai import (
    fetch_nhentai_gallery,
    fetch_nhentai_explore,
    fetch_nhentai_online_pages,
    get_nhentai_image_proxy_data,
    fetch_nhentai_favorites,
    add_nhentai_favorite,
    remove_nhentai_favorite,
    check_nhentai_favorite,
    get_api_status,
    get_image_server,
    get_thumb_server,
)
from backup import (
    save_backup_file,
    restore_backup_from_file,
    auto_restore_if_empty,
    BACKUP_FILE,
)


def trigger_auto_backup():
    """Tự động lưu bản sao lưu mới nhất ra file backup.json."""
    try:
        save_backup_file()
    except Exception as e:
        print(f"[Warning] Auto backup failed: {e}")


# ==================== HELPERS ====================

def _format_cover_url(cover_path: str) -> str:
    """Tạo proxy URL cho ảnh bìa."""
    if not cover_path:
        return "/assets/default_cover.jpg"
    if cover_path.startswith("http"):
        raw_url = cover_path
    else:
        thumb_server = get_thumb_server()
        raw_url = f"{thumb_server}/{cover_path}"
    return f"/api/nhentai/image-proxy?url={urllib.parse.quote(raw_url)}"


# ==================== COMICS ====================

def get_all_comics(folder_id: int = None, author_id: int = None, q: str = None):
    """
    Lấy danh sách truyện trong thư viện:
    - Lọc theo folder_id (nếu có)
    - Lọc theo author_id (nếu có)
    - Tìm kiếm theo tên (q)
    """
    sb = get_supabase()

    # Nếu có lọc folder
    if folder_id is not None:
        fc_res = sb.table("folder_comics").select("comic_id").eq("folder_id", folder_id).execute()
        target_ids = [r["comic_id"] for r in (fc_res.data or [])]
        if not target_ids:
            return []
    elif author_id is not None:
        ct_res = sb.table("comic_tags").select("comic_id").eq("tag_id", author_id).execute()
        target_ids = [r["comic_id"] for r in (ct_res.data or [])]
        if not target_ids:
            return []
    else:
        target_ids = None

    query = sb.table("comics").select("id, media_id, title_pretty, cover_path, num_pages, created_at")
    if target_ids is not None:
        query = query.in_("id", target_ids)
    if q and q.strip():
        query = query.ilike("title_pretty", f"%{q.strip()}%")

    query = query.order("created_at", desc=True)
    res = query.execute()
    comics = res.data or []
    if not comics:
        return []

    comic_ids = [c["id"] for c in comics]

    # Gắn tags (tác giả & thể loại)
    ct_res = sb.table("comic_tags").select("comic_id, tags(id, type, name, slug)").in_("comic_id", comic_ids).execute()
    tags_by_comic = {}
    for row in (ct_res.data or []):
        c_id = row.get("comic_id")
        t = row.get("tags")
        if c_id and t:
            tags_by_comic.setdefault(c_id, []).append(t)

    # Gắn folders
    fc_res = sb.table("folder_comics").select("comic_id, folders(id, name)").in_("comic_id", comic_ids).execute()
    folders_by_comic = {}
    for row in (fc_res.data or []):
        c_id = row.get("comic_id")
        f = row.get("folders")
        if c_id and f:
            folders_by_comic.setdefault(c_id, []).append(f)

    # Format output
    output = []
    for c in comics:
        c_id = c["id"]
        c_tags = tags_by_comic.get(c_id, [])
        authors = [t["name"] for t in c_tags if t["type"] == "artist"]
        genres = [t["name"] for t in c_tags if t["type"] == "tag"]
        c_folders = folders_by_comic.get(c_id, [])

        output.append({
            "id": c_id,
            "gallery_id": c_id,
            "media_id": c["media_id"],
            "title": c["title_pretty"],
            "author": ", ".join(authors) if authors else "Unknown",
            "authors": authors,
            "genres": genres,
            "cover_url": _format_cover_url(c["cover_path"]),
            "num_pages": c["num_pages"],
            "folders": [f["name"] for f in c_folders],
            "folder_details": c_folders
        })

    return output


def get_comic_detail(comic_id: int):
    """Lấy thông tin chi tiết của 1 bộ truyện kèm Chapters và Tags."""
    sb = get_supabase()
    c_res = sb.table("comics").select("*").eq("id", comic_id).execute()
    if not c_res.data:
        return None
    comic = c_res.data[0]

    # Lấy Tags
    ct_res = sb.table("comic_tags").select("tags(id, type, name, slug)").eq("comic_id", comic_id).execute()
    tags = [r["tags"] for r in (ct_res.data or []) if r.get("tags")]
    authors = [t for t in tags if t["type"] == "artist"]
    genres = [t for t in tags if t["type"] == "tag"]

    # Lấy Chapters
    ch_res = sb.table("chapters").select("*").eq("comic_id", comic_id).order("chapter_number", desc=False).execute()
    chapters = ch_res.data or []

    # Lấy Folders
    fc_res = sb.table("folder_comics").select("folders(id, name)").eq("comic_id", comic_id).execute()
    folders = [r["folders"] for r in (fc_res.data or []) if r.get("folders")]

    return {
        "id": comic["id"],
        "gallery_id": comic["id"],
        "media_id": comic["media_id"],
        "title": comic["title_pretty"],
        "author": ", ".join([a["name"] for a in authors]) if authors else "Unknown",
        "authors": [a["name"] for a in authors],
        "author_details": authors,
        "genres": [g["name"] for g in genres],
        "cover_url": _format_cover_url(comic["cover_path"]),
        "num_pages": comic["num_pages"],
        "folders": [f["name"] for f in folders],
        "folder_details": folders,
        "chapters": chapters
    }


def preview_comic_by_id(gallery_id: int):
    """Xem trước thông tin truyện từ NHentai trước khi thêm vào thư viện."""
    info = fetch_nhentai_gallery(gallery_id)
    return {
        "id": info["id"],
        "title": info["title"],
        "author": info["author"],
        "authors": info.get("authors", []),
        "genres": info.get("genres", []),
        "cover_url": f"/api/nhentai/image-proxy?url={urllib.parse.quote(info['cover_url'])}",
        "num_pages": info["num_pages"]
    }


async def create_comic_by_id(gallery_id: int, folder_id: int = None, pages_per_chapter: int = None):
    """Lưu truyện vào Thư viện từ Gallery ID."""
    sb = get_supabase()
    info = fetch_nhentai_gallery(gallery_id)

    c_id = info["id"]
    media_id = str(info["media_id"])
    title_pretty = info["title"]
    cover_path = info.get("cover_path") or f"galleries/{media_id}/cover.{info.get('ext', 'jpg')}"
    num_pages = int(info["num_pages"])

    # 1. Lưu Comic
    sb.table("comics").upsert({
        "id": c_id,
        "media_id": media_id,
        "title_pretty": title_pretty,
        "cover_path": cover_path,
        "num_pages": num_pages
    }).execute()

    # 2. Gắn vào Folder (Mặc định nếu chưa chọn)
    if not folder_id:
        def_f = sb.table("folders").select("id").eq("name", "Mặc định").execute()
        folder_id = def_f.data[0]["id"] if def_f.data else 1

    sb.table("folder_comics").upsert({
        "folder_id": folder_id,
        "comic_id": c_id
    }).execute()

    # 3. Lưu Tags (Tác giả và Thể loại)
    tags_raw = info.get("tags", [])
    if not tags_raw:
        # Nếu info không có raw tags, dùng authors & genres đã bóc tách
        for a_name in info.get("authors", []):
            tags_raw.append({"id": abs(hash(f"artist_{a_name}")) % 1000000 + 500000, "type": "artist", "name": a_name, "slug": a_name.lower().replace(" ", "-")})
        for g_name in info.get("genres", []):
            tags_raw.append({"id": abs(hash(f"tag_{g_name}")) % 1000000 + 1000000, "type": "tag", "name": g_name, "slug": g_name.lower().replace(" ", "-")})

    for t in tags_raw:
        t_type = t.get("type")
        if t_type in ("artist", "tag"):
            sb.table("tags").upsert({
                "id": t["id"],
                "type": t_type,
                "name": t["name"].strip(),
                "slug": t.get("slug") or t["name"].strip().lower().replace(" ", "-")
            }).execute()
            sb.table("comic_tags").upsert({
                "comic_id": c_id,
                "tag_id": t["id"]
            }).execute()

    # 4. Tạo Chapters
    # Xóa chapter cũ nếu có
    sb.table("chapters").delete().eq("comic_id", c_id).execute()

    if pages_per_chapter and pages_per_chapter > 0:
        total_chaps = math.ceil(num_pages / pages_per_chapter)
        for i in range(total_chaps):
            c_num = float(i + 1)
            s_page = i * pages_per_chapter + 1
            e_page = min((i + 1) * pages_per_chapter, num_pages)
            sb.table("chapters").insert({
                "comic_id": c_id,
                "chapter_number": c_num,
                "title": f"Chương {int(c_num)} (Trang {s_page}-{e_page})",
                "media_id": media_id,
                "start_page": s_page,
                "end_page": e_page
            }).execute()
    else:
        # Chapter 1 mặc định trọn vẹn
        sb.table("chapters").insert({
            "comic_id": c_id,
            "chapter_number": 1.0,
            "title": "Full",
            "media_id": media_id,
            "start_page": 1,
            "end_page": num_pages
        }).execute()

    trigger_auto_backup()
    return get_comic_detail(c_id)


def delete_comic(comic_id: int) -> bool:
    """Xóa truyện khỏi thư viện."""
    sb = get_supabase()
    res = sb.table("comics").delete().eq("id", comic_id).execute()
    if res.data:
        trigger_auto_backup()
        return True
    return False


# ==================== CHAPTERS ====================

def create_chapter_by_id(comic_id: int, gallery_id: int, chapter_number: float = None, title: str = None):
    """
    Trường hợp 1: Thêm một chapter mới vào bộ truyện từ một Gallery ID riêng biệt (Gộp nhiều bộ).
    """
    sb = get_supabase()
    info = fetch_nhentai_gallery(gallery_id)
    ch_media_id = str(info["media_id"])
    ch_num_pages = int(info["num_pages"])

    if chapter_number is None:
        curr_chaps = sb.table("chapters").select("chapter_number").eq("comic_id", comic_id).order("chapter_number", desc=True).limit(1).execute()
        if curr_chaps.data:
            chapter_number = float(curr_chaps.data[0]["chapter_number"]) + 1.0
        else:
            chapter_number = 1.0

    if not title:
        title = info.get("title") or f"Chapter {chapter_number}"

    res = sb.table("chapters").insert({
        "comic_id": comic_id,
        "chapter_number": chapter_number,
        "title": title,
        "media_id": ch_media_id,
        "start_page": 1,
        "end_page": ch_num_pages
    }).execute()

    trigger_auto_backup()
    return res.data[0] if res.data else None


def create_chapter_from_comic(comic_id: int, data):
    """Thêm chapter thủ công."""
    sb = get_supabase()
    # Lấy media_id của comic nếu data không có media_id
    media_id = data.media_id
    if not media_id:
        c_res = sb.table("comics").select("media_id").eq("id", comic_id).execute()
        media_id = c_res.data[0]["media_id"] if c_res.data else str(comic_id)

    res = sb.table("chapters").insert({
        "comic_id": comic_id,
        "chapter_number": data.chapter_number,
        "title": data.title or f"Chapter {data.chapter_number}",
        "media_id": media_id,
        "start_page": data.start_page,
        "end_page": data.end_page
    }).execute()

    trigger_auto_backup()
    return res.data[0] if res.data else None


def split_comic_chapters(comic_id: int, pages_per_chapter: int):
    """
    Trường hợp 2: Chia 1 bộ truyện dài thành nhiều chapter đều nhau theo số trang.
    """
    sb = get_supabase()
    c_res = sb.table("comics").select("media_id, num_pages").eq("id", comic_id).execute()
    if not c_res.data:
        raise HTTPException(status_code=404, detail="Comic not found")

    media_id = c_res.data[0]["media_id"]
    num_pages = int(c_res.data[0]["num_pages"])

    if pages_per_chapter <= 0:
        raise HTTPException(status_code=400, detail="pages_per_chapter phải lớn hơn 0")

    # Xóa chapter cũ
    sb.table("chapters").delete().eq("comic_id", comic_id).execute()

    total_chaps = math.ceil(num_pages / pages_per_chapter)
    new_chaps = []
    for i in range(total_chaps):
        c_num = float(i + 1)
        s_page = i * pages_per_chapter + 1
        e_page = min((i + 1) * pages_per_chapter, num_pages)
        new_chaps.append({
            "comic_id": comic_id,
            "chapter_number": c_num,
            "title": f"Chương {int(c_num)} (Trang {s_page}-{e_page})",
            "media_id": media_id,
            "start_page": s_page,
            "end_page": e_page
        })

    sb.table("chapters").insert(new_chaps).execute()
    trigger_auto_backup()
    return get_comic_detail(comic_id)


def custom_split_comic_chapters(comic_id: int, chapters_data: list):
    """Chia chapter tùy chỉnh theo dải trang do người dùng tự nhập."""
    sb = get_supabase()
    c_res = sb.table("comics").select("media_id").eq("id", comic_id).execute()
    if not c_res.data:
        raise HTTPException(status_code=404, detail="Comic not found")

    default_media_id = c_res.data[0]["media_id"]

    sb.table("chapters").delete().eq("comic_id", comic_id).execute()
    new_chaps = []
    for ch in chapters_data:
        new_chaps.append({
            "comic_id": comic_id,
            "chapter_number": ch["chapter_number"],
            "title": ch.get("title") or f"Chapter {ch['chapter_number']}",
            "media_id": ch.get("media_id") or default_media_id,
            "start_page": ch["start_page"],
            "end_page": ch["end_page"]
        })

    sb.table("chapters").insert(new_chaps).execute()
    trigger_auto_backup()
    return get_comic_detail(comic_id)


def get_chapter_by_id(chapter_id: int):
    sb = get_supabase()
    res = sb.table("chapters").select("*").eq("id", chapter_id).execute()
    return res.data[0] if res.data else None


def update_chapter(chapter_id: int, data):
    sb = get_supabase()
    update_dict = {}
    if data.title is not None:
        update_dict["title"] = data.title
    if data.chapter_number is not None:
        update_dict["chapter_number"] = data.chapter_number
    if data.media_id is not None:
        update_dict["media_id"] = data.media_id
    if data.start_page is not None:
        update_dict["start_page"] = data.start_page
    if data.end_page is not None:
        update_dict["end_page"] = data.end_page

    if update_dict:
        res = sb.table("chapters").update(update_dict).eq("id", chapter_id).execute()
        trigger_auto_backup()
        return res.data[0] if res.data else None
    return get_chapter_by_id(chapter_id)


def delete_chapter(chapter_id: int):
    sb = get_supabase()
    sb.table("chapters").delete().eq("id", chapter_id).execute()
    trigger_auto_backup()
    return True


def generate_pages(chapter_id: int):
    """
    Sinh danh sách URL trang cho trình đọc dựa trên media_id và khoảng trang (start_page -> end_page).
    Định tuyến qua in-memory image proxy để vượt qua bộ chặn mạng.
    """
    chapter = get_chapter_by_id(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    media_id = chapter["media_id"]
    start_p = chapter["start_page"]
    end_p = chapter["end_page"]

    img_server = get_image_server()

    # Sinh danh sách URL qua image-proxy
    pages = []
    for p in range(start_p, end_p + 1):
        raw_url = f"{img_server}/galleries/{media_id}/{p}.webp"
        proxy_url = f"/api/nhentai/image-proxy?url={urllib.parse.quote(raw_url)}"
        pages.append(proxy_url)

    return {
        "chapter_id": chapter["id"],
        "comic_id": chapter["comic_id"],
        "chapter_number": chapter["chapter_number"],
        "title": chapter["title"],
        "media_id": media_id,
        "total_pages": len(pages),
        "pages": pages
    }


# ==================== AUTHORS (QUẢN LÝ TÁC GIẢ) ====================

def get_all_authors():
    """
    Lấy danh sách Tác giả có truyện trong thư viện:
    SELECT DISTINCT tags WHERE type = 'artist'
    """
    sb = get_supabase()
    res = sb.table("comic_tags").select("tags!inner(id, name, slug, type)").eq("tags.type", "artist").execute()
    authors_map = {}
    for r in (res.data or []):
        t = r.get("tags")
        if t:
            a_id = t["id"]
            if a_id not in authors_map:
                authors_map[a_id] = {
                    "id": a_id,
                    "name": t["name"],
                    "slug": t["slug"],
                    "count": 0
                }
            authors_map[a_id]["count"] += 1

    authors_list = list(authors_map.values())
    authors_list.sort(key=lambda x: x["name"].lower())
    return authors_list


def get_comics_by_author(author_id_or_name: str):
    """Lấy danh sách truyện trong thư viện của 1 tác giả."""
    sb = get_supabase()
    try:
        a_id = int(author_id_or_name)
        return get_all_comics(author_id=a_id)
    except ValueError:
        # Nếu truyền name
        t_res = sb.table("tags").select("id").eq("type", "artist").ilike("name", author_id_or_name).execute()
        if t_res.data:
            return get_all_comics(author_id=t_res.data[0]["id"])
        return []


# ==================== DISCOVER FILTER TAGS ====================

def get_saved_tags_for_discover():
    """
    Lấy danh sách Tác giả và Thể loại của các truyện ĐÃ LƯU TRONG THƯ VIỆN để đưa lên bộ lọc Khám phá.
    """
    sb = get_supabase()
    res = sb.table("comic_tags").select("tags!inner(id, name, slug, type)").execute()

    authors_set = {}
    genres_set = {}

    for r in (res.data or []):
        t = r.get("tags")
        if not t:
            continue
        if t["type"] == "artist":
            authors_set[t["id"]] = {"id": t["id"], "name": t["name"], "slug": t["slug"]}
        elif t["type"] == "tag":
            genres_set[t["id"]] = {"id": t["id"], "name": t["name"], "slug": t["slug"]}

    authors_list = sorted(list(authors_set.values()), key=lambda x: x["name"].lower())
    genres_list = sorted(list(genres_set.values()), key=lambda x: x["name"].lower())

    return {
        "authors": authors_list,
        "genres": genres_list
    }


# ==================== FOLDERS ====================

def get_all_folders():
    sb = get_supabase()
    res = sb.table("folders").select("id, name, description, created_at").order("id", desc=False).execute()
    folders = res.data or []

    # Đếm số truyện trong mỗi folder
    for f in folders:
        fc = sb.table("folder_comics").select("comic_id", count="exact").eq("folder_id", f["id"]).execute()
        f["comics_count"] = fc.count or 0

    return folders


def create_folder(name: str, description: str = ""):
    sb = get_supabase()
    res = sb.table("folders").insert({"name": name, "description": description}).execute()
    trigger_auto_backup()
    return res.data[0] if res.data else None


def update_folder(folder_id: int, name: str = None, description: str = None):
    sb = get_supabase()
    up = {}
    if name is not None:
        up["name"] = name
    if description is not None:
        up["description"] = description
    res = sb.table("folders").update(up).eq("id", folder_id).execute()
    trigger_auto_backup()
    return res.data[0] if res.data else None


def delete_folder(folder_id: int):
    sb = get_supabase()
    sb.table("folders").delete().eq("id", folder_id).execute()
    trigger_auto_backup()
    return {"message": "Folder deleted successfully"}


def add_comic_to_folder(folder_id: int, comic_id: int):
    sb = get_supabase()
    sb.table("folder_comics").upsert({"folder_id": folder_id, "comic_id": comic_id}).execute()
    trigger_auto_backup()
    return {"message": "Comic added to folder successfully"}


def remove_comic_from_folder(folder_id: int, comic_id: int):
    sb = get_supabase()
    sb.table("folder_comics").delete().eq("folder_id", folder_id).eq("comic_id", comic_id).execute()
    trigger_auto_backup()
    return {"message": "Comic removed from folder successfully"}


# ==================== SEARCH ====================

def search_comics(q: str = None, folder_id: int = None, author_id: int = None):
    return get_all_comics(folder_id=folder_id, author_id=author_id, q=q)


# ==================== NHENTAI WRAPPERS ====================

def get_nhentai_explore_service(page: int = 1, sort: str = "date", q: str = None):
    return fetch_nhentai_explore(page=page, sort=sort, query=q)


def get_nhentai_online_gallery_service(gallery_id: int):
    return fetch_nhentai_online_pages(gallery_id)


def get_nhentai_image_proxy_service(url: str):
    return get_nhentai_image_proxy_data(url)


def get_nhentai_favorites_service(page: int = 1, q: str = None):
    return fetch_nhentai_favorites(page=page, query=q)


def add_nhentai_favorite_service(gallery_id: int):
    return add_nhentai_favorite(gallery_id)


def remove_nhentai_favorite_service(gallery_id: int):
    return remove_nhentai_favorite(gallery_id)


def check_nhentai_favorite_service(gallery_id: int):
    return check_nhentai_favorite(gallery_id)


def get_nhentai_api_status_service():
    return get_api_status()

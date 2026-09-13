"""
NHentai Integration
===================
Kết nối và trích xuất dữ liệu từ API NHentai theo mã ID truyện.
"""

import subprocess
import json
import re
import urllib.parse
from fastapi import HTTPException


def _execute_curl(endpoint_or_url: str) -> dict:
    """Thực thi curl với header giả lập trình duyệt và bypass Cloudflare IP."""
    url = endpoint_or_url if endpoint_or_url.startswith("http") else f"https://nhentai.net{endpoint_or_url}"
    cmd = [
        "curl.exe", "-s",
        "--resolve", "nhentai.net:443:172.67.74.203",
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "-H", "Accept: application/json",
        url
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi kết nối tới NHentai: {str(e)}")

    if res.returncode != 0 or not res.stdout.strip():
        raise HTTPException(status_code=502, detail="Không thể kết nối đến máy chủ NHentai!")

    try:
        data = json.loads(res.stdout)
    except Exception:
        raise HTTPException(status_code=502, detail="Không thể giải mã dữ liệu trả về từ NHentai!")

    if isinstance(data, dict) and data.get("error"):
        detail_msg = data.get("details") or data.get("error")
        raise HTTPException(status_code=400, detail=f"NHentai API: {detail_msg}")

    return data


def fetch_nhentai_gallery(gallery_id: int) -> dict:
    """
    Gọi API NHentai lấy toàn bộ thông tin truyện theo ID.
    Trả về dict: { id, title, author, genres, num_pages, media_id, base_url, cover_url, ext }
    """
    if not gallery_id or int(gallery_id) <= 0:
        raise HTTPException(status_code=400, detail="ID truyện không hợp lệ!")

    clean_id = int(gallery_id)
    data = _execute_curl(f"/api/v2/galleries/{clean_id}")

    if not data or not data.get("id"):
        raise HTTPException(status_code=404, detail=f"Truyện với ID {clean_id} không tồn tại hoặc đã bị gỡ bỏ trên NHentai!")

    # Trích xuất tên truyện
    title_obj = data.get("title", {})
    raw_title = title_obj.get("pretty") or title_obj.get("english") or f"Manga #{clean_id}"
    clean_title = raw_title.strip()

    # Trích xuất tác giả (Ưu tiên artists, nếu không có thì lấy groups/nhóm sáng tác)
    tags_list = data.get("tags", [])
    artists = [t.get("name", "").strip() for t in tags_list if t.get("type") == "artist" and t.get("name")]
    groups = [t.get("name", "").strip() for t in tags_list if t.get("type") == "group" and t.get("name")]

    authors_list = artists if artists else groups
    if not authors_list:
        authors_list = ["Unknown"]

    author_str = ", ".join(authors_list)

    # Trích xuất thể loại
    genres = []
    for t in tags_list:
        t_type = t.get("type", "")
        t_name = t.get("name", "").strip()
        if t_type in ["tag", "category"] and t_name:
            genres.append(t_name.title())

    # Media ID và số trang
    media_id = str(data.get("media_id") or clean_id)
    num_pages = int(data.get("num_pages") or len(data.get("pages", [])) or 1)

    # Định dạng ảnh trang 1
    pages = data.get("pages", [])
    first_page_path = pages[0].get("path", "") if pages else ""
    ext_match = re.search(r'\.([a-zA-Z0-9]+)$', first_page_path)
    ext = ext_match.group(1).lower() if ext_match else "jpg"

    # Base URL cho trang 1
    base_url = f"https://i3.nhentai.net/galleries/{media_id}/1.{ext}"

    return {
        "id": clean_id,
        "title": clean_title,
        "author": author_str,
        "authors": authors_list,
        "genres": genres,
        "num_pages": num_pages,
        "media_id": media_id,
        "base_url": base_url,
        "cover_url": base_url,
        "ext": ext
    }


def fetch_nhentai_explore(page: int = 1, sort: str = "date", query: str = None) -> dict:
    """
    Lấy danh sách truyện từ NHentai (hỗ trợ phân trang, tìm kiếm, lọc theo tiêu chí sắp xếp).
    """
    clean_page = max(1, int(page or 1))
    valid_sorts = ["date", "popular", "popular-today", "popular-week", "popular-month"]
    clean_sort = sort if sort in valid_sorts else "date"

    if query and query.strip():
        clean_q = query.strip()
        encoded_q = urllib.parse.quote(clean_q)
        endpoint = f"/api/v2/search?query={encoded_q}&page={clean_page}&sort={clean_sort}"
    else:
        if clean_sort != "date":
            # Khi chọn sort mà không có query, dùng query phổ quát 'pages:>0'
            endpoint = f"/api/v2/search?query=pages%3A%3E0&page={clean_page}&sort={clean_sort}"
        else:
            endpoint = f"/api/v2/galleries?page={clean_page}"

    data = _execute_curl(endpoint)
    raw_results = data.get("result", []) if isinstance(data, dict) else []
    total_pages = int(data.get("num_pages") or 1) if isinstance(data, dict) else 1

    clean_results = []
    for item in raw_results:
        g_id = item.get("id")
        if not g_id:
            continue
        media_id = str(item.get("media_id") or g_id)
        title = item.get("english_title") or item.get("japanese_title") or f"Manga #{g_id}"

        # Ảnh thumbnail từ NHentai CDN
        thumb_path = item.get("thumbnail") or f"galleries/{media_id}/thumb.webp"
        cover_url = f"https://t3.nhentai.net/{thumb_path}" if not thumb_path.startswith("http") else thumb_path

        clean_results.append({
            "id": g_id,
            "media_id": media_id,
            "title": title.strip(),
            "cover_url": cover_url,
            "num_pages": int(item.get("num_pages") or 1),
            "num_favorites": int(item.get("num_favorites") or 0)
        })

    return {
        "page": clean_page,
        "total_pages": total_pages,
        "sort": clean_sort,
        "query": query or "",
        "result": clean_results
    }


def fetch_nhentai_online_pages(gallery_id: int) -> dict:
    """
    Lấy thông tin chi tiết và sinh danh sách đầy đủ tất cả các URL ảnh để đọc online trực tiếp.
    """
    info = fetch_nhentai_gallery(gallery_id)
    media_id = info["media_id"]
    ext = info["ext"]
    num_pages = info["num_pages"]

    # Sinh danh sách link ảnh trực tiếp từ CDN
    pages = [f"https://i3.nhentai.net/galleries/{media_id}/{i}.{ext}" for i in range(1, num_pages + 1)]

    return {
        "id": info["id"],
        "title": info["title"],
        "author": info["author"],
        "authors": info["authors"],
        "genres": info["genres"],
        "num_pages": num_pages,
        "media_id": media_id,
        "cover_url": info["cover_url"],
        "pages": pages
    }

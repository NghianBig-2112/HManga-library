"""
NHentai Integration
===================
Kết nối và trích xuất dữ liệu từ API NHentai theo mã ID truyện.
"""

import subprocess
import json
import re
from fastapi import HTTPException


def fetch_nhentai_gallery(gallery_id: int) -> dict:
    """
    Gọi API NHentai lấy toàn bộ thông tin truyện theo ID.
    Trả về dict: { id, title, author, genres, num_pages, media_id, base_url, cover_url, ext }
    """
    if not gallery_id or int(gallery_id) <= 0:
        raise HTTPException(status_code=400, detail="ID truyện không hợp lệ!")

    clean_id = int(gallery_id)

    cmd = [
        "curl.exe", "-s",
        "--resolve", "nhentai.net:443:172.67.74.203",
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "-H", "Accept: application/json",
        f"https://nhentai.net/api/v2/galleries/{clean_id}"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi kết nối tới NHentai: {str(e)}")

    if res.returncode != 0 or not res.stdout.strip():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy truyện với ID {clean_id} trên NHentai!")

    try:
        data = json.loads(res.stdout)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Không thể giải mã dữ liệu truyện từ ID {clean_id}!")

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

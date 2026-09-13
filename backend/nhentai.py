"""
NHentai Integration
===================
Kết nối và trích xuất dữ liệu từ API NHentai theo mã ID truyện.
"""

import subprocess
import json
import re
import urllib.parse
import urllib.request
import hashlib
import threading
import math
from pathlib import Path
from fastapi import HTTPException

# Số lượng truyện cố định trên 1 trang khám phá
PER_PAGE = 12


def _detect_media_type(data: bytes, fallback_url: str = "") -> str:
    """Xác định media_type của dữ liệu ảnh qua magic bytes."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if fallback_url.endswith(".webp"):
        return "image/webp"
    if fallback_url.endswith(".png"):
        return "image/png"
    return "image/jpeg"


def get_nhentai_image_proxy_data(image_url: str) -> tuple[bytes, str]:
    """
    Tải ảnh từ CDN NHentai trực tiếp vào bộ nhớ RAM (In-Memory Streaming).
    Không lưu bất kỳ file nào ra ổ đĩa (0 byte ổ đĩa).
    Trả về (data_bytes, media_type).
    """
    if not image_url:
        raise HTTPException(status_code=400, detail="Thiếu tham số url ảnh!")

    parsed = urllib.parse.urlparse(image_url)
    domain = parsed.netloc.lower()

    if not (domain.endswith("nhentai.net") or domain == "nhentai.net"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ proxy ảnh từ máy chủ nhentai.net!")

    # Danh sách các URL thử tải (thử đuôi thay thế nếu URL thumbnail gốc bị 404)
    urls_to_try = [image_url]
    if "thumb." in parsed.path:
        for alt_ext in ["webp", "jpg", "png", "jpeg"]:
            alt_url = re.sub(r'\.\w+(\?.*)?$', f'.{alt_ext}', image_url)
            if alt_url not in urls_to_try:
                urls_to_try.append(alt_url)

    # 1. Thử tải trực tiếp bằng urllib (nhanh và nhẹ nhất, ~0.1s/ảnh, nạp thẳng vào RAM)
    for target_url in urls_to_try:
        try:
            req = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": "https://nhentai.net/"
                }
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) >= 100:
                        media_type = resp.headers.get("Content-Type") or _detect_media_type(data, target_url)
                        if "image/" not in media_type:
                            media_type = _detect_media_type(data, target_url)
                        return data, media_type
        except Exception:
            pass

    # 2. Dự phòng: Tải bằng curl với IP Anycast Cloudflare vào thẳng RAM nếu mạng bị chặn DNS
    for target_url in urls_to_try:
        t_domain = urllib.parse.urlparse(target_url).netloc.lower()
        for ip in ["172.67.74.203", "213.152.165.53"]:
            cmd = [
                "curl.exe", "-s",
                "--connect-timeout", "3",
                "--max-time", "8",
                "--resolve", f"{t_domain}:443:{ip}",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "-H", "Referer: https://nhentai.net/",
                target_url
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, timeout=10)
                if res.returncode == 0 and len(res.stdout) >= 100:
                    media_type = _detect_media_type(res.stdout, target_url)
                    return res.stdout, media_type
            except Exception:
                pass

    raise HTTPException(status_code=502, detail="Không thể tải ảnh từ máy chủ NHentai (Lỗi kết nối CDN)!")


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
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
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
    Lấy danh sách truyện từ NHentai (cố định 12 bộ/trang, hỗ trợ tìm kiếm, lọc theo tiêu chí sắp xếp).
    """
    clean_page = max(1, int(page or 1))
    valid_sorts = ["date", "popular", "popular-today", "popular-week", "popular-month"]
    clean_sort = sort if sort in valid_sorts else "date"

    has_query = bool(query and query.strip())
    is_date_sort = (clean_sort == "date")

    if not has_query and is_date_sort:
        # Đường dẫn mặc định: NHentai v2 galleries hỗ trợ trực tiếp per_page=12
        endpoint = f"/api/v2/galleries?page={clean_page}&per_page={PER_PAGE}"
        data = _execute_curl(endpoint)
        raw_results = data.get("result", []) if isinstance(data, dict) else []
        total_pages = int(data.get("num_pages") or 1) if isinstance(data, dict) else 1
        total_items = int(data.get("total") or 0) if isinstance(data, dict) else 0
        if not total_items:
            total_items = total_pages * PER_PAGE
    else:
        # Khi có search hoặc sort khác 'date': NHentai search API chỉ trả về cố định 25 kết quả/trang
        # Dùng thuật toán phân trang ảo (Virtual Pagination) để trả về đúng 12 bộ/trang mà không bỏ sót truyện
        clean_q = query.strip() if has_query else "pages:>0"
        encoded_q = urllib.parse.quote(clean_q)

        start_idx = (clean_page - 1) * PER_PAGE
        end_idx = clean_page * PER_PAGE
        nh_p1 = (start_idx // 25) + 1
        nh_p2 = ((end_idx - 1) // 25) + 1

        endpoint1 = f"/api/v2/search?query={encoded_q}&page={nh_p1}&sort={clean_sort}"
        data1 = _execute_curl(endpoint1)

        total_items = int(data1.get("total") or 0) if isinstance(data1, dict) else 0
        nh_num_pages = int(data1.get("num_pages") or 1) if isinstance(data1, dict) else 1

        if total_items > 0:
            total_pages = math.ceil(total_items / PER_PAGE)
        else:
            total_pages = math.ceil((nh_num_pages * 25) / PER_PAGE)

        res1 = data1.get("result", []) if isinstance(data1, dict) else []

        if nh_p1 == nh_p2:
            off_start = start_idx % 25
            off_end = off_start + PER_PAGE
            raw_results = res1[off_start:off_end]
        else:
            off1_start = start_idx % 25
            off2_end = end_idx % 25
            slice1 = res1[off1_start:]

            # Gọi trang thứ 2 của NHentai để lấy phần còn thiếu
            endpoint2 = f"/api/v2/search?query={encoded_q}&page={nh_p2}&sort={clean_sort}"
            try:
                data2 = _execute_curl(endpoint2)
                res2 = data2.get("result", []) if isinstance(data2, dict) else []
            except Exception:
                res2 = []
            slice2 = res2[:off2_end]
            raw_results = slice1 + slice2

    clean_results = []
    for item in raw_results:
        g_id = item.get("id")
        if not g_id:
            continue
        media_id = str(item.get("media_id") or g_id)
        title = item.get("english_title") or item.get("japanese_title") or f"Manga #{g_id}"

        # Ảnh thumbnail từ NHentai CDN qua Image Proxy nội bộ (Bypass ISP chặn)
        thumb_path = item.get("thumbnail") or f"galleries/{media_id}/thumb.webp"
        raw_thumb_url = f"https://t3.nhentai.net/{thumb_path}" if not thumb_path.startswith("http") else thumb_path
        cover_url = f"/api/nhentai/image-proxy?url={urllib.parse.quote(raw_thumb_url)}"

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
        "total": total_items,
        "per_page": PER_PAGE,
        "sort": clean_sort,
        "query": query or "",
        "result": clean_results
    }


def fetch_nhentai_online_pages(gallery_id: int) -> dict:
    """
    Lấy thông tin chi tiết và sinh danh sách đầy đủ tất cả các URL ảnh để đọc online trực tiếp.
    Tất cả ảnh đều được định tuyến qua image-proxy để vượt qua bộ chặn của nhà mạng Việt Nam.
    """
    info = fetch_nhentai_gallery(gallery_id)
    media_id = info["media_id"]
    ext = info["ext"]
    num_pages = info["num_pages"]

    # Sinh danh sách link ảnh trực tiếp từ CDN qua Image Proxy
    raw_pages = [f"https://i3.nhentai.net/galleries/{media_id}/{i}.{ext}" for i in range(1, num_pages + 1)]
    pages = [f"/api/nhentai/image-proxy?url={urllib.parse.quote(u)}" for u in raw_pages]
    proxied_cover = f"/api/nhentai/image-proxy?url={urllib.parse.quote(info['cover_url'])}"

    return {
        "id": info["id"],
        "title": info["title"],
        "author": info["author"],
        "authors": info["authors"],
        "genres": info["genres"],
        "num_pages": num_pages,
        "media_id": media_id,
        "cover_url": proxied_cover,
        "pages": pages
    }

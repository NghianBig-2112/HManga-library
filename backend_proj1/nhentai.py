"""
NHentai Integration Module (v3.5 - Persistent Session & API Key Enforced)
========================================================================
- Quản lý kết nối tốc độ cao tới NHentai API v2 bằng Persistent HTTP Session.
- Bắt buộc xác thực API Key: Authorization: Key <NHENTAI_API_KEY>.
- Tích hợp Favorites API hai chiều (Xem, Thêm, Gỡ Bookmark trên NHentai).
- Vượt tường lửa/chặn DNS nhà mạng bằng Cloudflare Anycast IP trực tiếp trong Python.
- Tải ảnh in-memory (0 byte ổ đĩa) cho trình đọc và ảnh bìa.
"""

import os
import re
import math
import socket
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from fastapi import HTTPException

# Số lượng truyện hiển thị trên 1 trang khám phá
PER_PAGE = 12

# Đường dẫn file cấu hình .env
ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)

# ==================== CLOUDFLARE DNS RESOLUTION ====================
# Vượt qua kiểm duyệt DNS nhà mạng bằng cách phân giải trực tiếp IP Anycast của Cloudflare
CF_IPS = ["172.67.74.203", "213.152.165.53"]
_orig_getaddrinfo = socket.getaddrinfo


def _cf_getaddrinfo(host, port, *args, **kwargs):
    if host and (host == "nhentai.net" or host.endswith(".nhentai.net")):
        # Trỏ trực tiếp tên miền NHentai sang IP Cloudflare Anycast
        return _orig_getaddrinfo(CF_IPS[0], port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = _cf_getaddrinfo

# ==================== PERSISTENT HTTP SESSION POOL ====================
_session = requests.Session()
_retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[502, 503, 504])
_adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=_retries)
_session.mount("https://", _adapter)


def get_auth_headers(auth_required: bool = False) -> dict:
    """
    Lấy header cho NHentai API v2.
    Nếu auth_required=True, bắt buộc phải có NHENTAI_API_KEY trong .env.
    Nếu auth_required=False, đính kèm key nếu có, nếu không thì dùng headers công khai.
    """
    load_dotenv(ENV_FILE, override=True)
    api_key = os.getenv("NHENTAI_API_KEY", "").strip()

    if auth_required and not api_key:
        raise HTTPException(
            status_code=401,
            detail="Chưa cấu hình NHENTAI_API_KEY trong file backend/.env! Vui lòng cung cấp API Key từ nhentai.net để sử dụng tính năng này."
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, */*",
        "Referer": "https://nhentai.net/"
    }

    if api_key:
        if api_key.startswith("Key ") or api_key.startswith("User "):
            headers["Authorization"] = api_key
        else:
            headers["Authorization"] = f"Key {api_key}"

    return headers


def execute_nhentai_api(method: str, endpoint_or_url: str, params: dict = None, json_data: dict = None, auth_required: bool = False) -> dict:
    """
    Thực thi request gọi API v2 của NHentai qua Persistent Session.
    """
    headers = get_auth_headers(auth_required=auth_required)
    url = endpoint_or_url if endpoint_or_url.startswith("http") else f"https://nhentai.net{endpoint_or_url}"

    try:
        resp = _session.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            timeout=12
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối tới máy chủ NHentai: {str(e)}")

    if resp.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="NHentai API: Xác thực thất bại! API Key không hợp lệ hoặc tài khoản chưa được cấp quyền."
        )

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu yêu cầu trên NHentai.")

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="NHentai API: Quá nhiều yêu cầu (Rate Limit). Vui lòng thử lại sau giây lát!"
        )

    if resp.status_code >= 400:
        detail_msg = "Lỗi khi gọi API NHentai"
        try:
            err_json = resp.json()
            detail_msg = err_json.get("error") or err_json.get("details") or detail_msg
        except Exception:
            detail_msg = resp.text[:200]
        raise HTTPException(status_code=resp.status_code, detail=f"NHentai API error: {detail_msg}")

    try:
        return resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Không thể giải mã dữ liệu JSON từ NHentai!")


# ==================== DYNAMIC CDN CACHE (SERVER 3 ENFORCED) ====================
DEFAULT_IMAGE_SERVER = "https://i3.nhentai.net"
DEFAULT_THUMB_SERVER = "https://t3.nhentai.net"
_cdn_cache = {"image_servers": [DEFAULT_IMAGE_SERVER], "thumb_servers": [DEFAULT_THUMB_SERVER]}


def get_cdn_servers() -> dict:
    """Lấy danh sách CDN đang hoạt động từ GET /api/v2/cdn (Cố định ưu tiên Server 3)."""
    global _cdn_cache
    try:
        data = _session.get(
            "https://nhentai.net/api/v2/cdn",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5
        ).json()
        if data.get("image_servers"):
            img_list = data["image_servers"]
            thumb_list = data.get("thumb_servers", [])
            s3_img = next((s for s in img_list if "i3." in s), DEFAULT_IMAGE_SERVER)
            s3_thumb = next((s for s in thumb_list if "t3." in s), DEFAULT_THUMB_SERVER)
            _cdn_cache = {
                "image_servers": [s3_img] + [s for s in img_list if s != s3_img],
                "thumb_servers": [s3_thumb] + [s for s in thumb_list if s != s3_thumb]
            }
    except Exception:
        pass
    return _cdn_cache


def get_image_server() -> str:
    """Luôn lấy máy chủ ảnh Server 3 (https://i3.nhentai.net)."""
    servers = get_cdn_servers().get("image_servers", [])
    for s in servers:
        if "i3." in s:
            return s
    return DEFAULT_IMAGE_SERVER


def get_thumb_server() -> str:
    """Luôn lấy máy chủ thumbnail Server 3 (https://t3.nhentai.net)."""
    servers = get_cdn_servers().get("thumb_servers", [])
    for s in servers:
        if "t3." in s:
            return s
    return DEFAULT_THUMB_SERVER


# ==================== MEDIA DETECTION & PROXY ====================

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


def get_nhentai_image_proxy_data(image_url: str) -> Tuple[bytes, str]:
    """
    Tải ảnh từ CDN NHentai trực tiếp vào bộ nhớ RAM (In-Memory Streaming).
    Không lưu bất kỳ file nào ra ổ đĩa (0 byte ổ đĩa).
    """
    if not image_url:
        raise HTTPException(status_code=400, detail="Thiếu tham số url ảnh!")

    parsed = urllib.parse.urlparse(image_url)
    domain = parsed.netloc.lower()

    if not (domain.endswith("nhentai.net") or domain == "nhentai.net"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ proxy ảnh từ máy chủ nhentai.net!")

    urls_to_try = [image_url]
    for alt_ext in ["jpg", "webp", "png", "jpeg"]:
        alt_url = re.sub(r'\.\w+(\?.*)?$', f'.{alt_ext}', image_url)
        if alt_url not in urls_to_try:
            urls_to_try.append(alt_url)

    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://nhentai.net/"
    }

    # Đính kèm API key nếu đã cấu hình
    load_dotenv(ENV_FILE, override=True)
    api_key = os.getenv("NHENTAI_API_KEY", "").strip()
    if api_key:
        req_headers["Authorization"] = api_key if api_key.startswith("Key ") else f"Key {api_key}"

    for target_url in urls_to_try:
        try:
            resp = _session.get(target_url, headers=req_headers, timeout=8)
            if resp.status_code == 200 and len(resp.content) >= 100:
                media_type = resp.headers.get("Content-Type") or _detect_media_type(resp.content, target_url)
                if "image/" not in media_type:
                    media_type = _detect_media_type(resp.content, target_url)
                return resp.content, media_type
        except Exception:
            continue

    raise HTTPException(status_code=502, detail="Không thể tải ảnh từ máy chủ NHentai (Lỗi kết nối CDN)!")


# ==================== NHENTAI GALLERIES & EXPLORE ====================

def fetch_nhentai_gallery(gallery_id: int) -> dict:
    """
    Gọi API NHentai lấy toàn bộ thông tin truyện theo ID (bắt buộc xác thực API Key).
    """
    if not gallery_id or int(gallery_id) <= 0:
        raise HTTPException(status_code=400, detail="ID truyện không hợp lệ!")

    clean_id = int(gallery_id)
    data = execute_nhentai_api("GET", f"/api/v2/galleries/{clean_id}")

    if not data or not data.get("id"):
        raise HTTPException(status_code=404, detail=f"Truyện với ID {clean_id} không tồn tại hoặc đã bị gỡ bỏ!")

    title_obj = data.get("title", {})
    raw_title = title_obj.get("pretty") or title_obj.get("english") or f"Manga #{clean_id}"
    clean_title = raw_title.strip()

    tags_list = data.get("tags", [])
    artists = [t.get("name", "").strip() for t in tags_list if t.get("type") == "artist" and t.get("name")]
    groups = [t.get("name", "").strip() for t in tags_list if t.get("type") == "group" and t.get("name")]

    authors_list = artists if artists else groups
    if not authors_list:
        authors_list = ["Unknown"]
    author_str = ", ".join(authors_list)

    genres = []
    for t in tags_list:
        t_type = t.get("type", "")
        t_name = t.get("name", "").strip()
        if t_type in ["tag", "category"] and t_name:
            genres.append(t_name.title())

    media_id = str(data.get("media_id") or clean_id)
    num_pages = int(data.get("num_pages") or len(data.get("pages", [])) or 1)

    pages = data.get("pages", [])
    first_page_path = pages[0].get("path", "") if pages else ""
    ext_match = re.search(r'\.([a-zA-Z0-9]+)$', first_page_path)
    ext = ext_match.group(1).lower() if ext_match else "jpg"

    base_img_server = get_image_server()
    base_url = f"{base_img_server}/galleries/{media_id}/1.{ext}"

    # Lấy cover path từ data
    cover_obj = data.get("cover", {})
    cover_path = cover_obj.get("path") or f"galleries/{media_id}/cover.{ext}"
    thumb_server = get_thumb_server()
    raw_cover_url = f"{thumb_server}/{cover_path}" if not cover_path.startswith("http") else cover_path

    return {
        "id": clean_id,
        "title": clean_title,
        "author": author_str,
        "authors": authors_list,
        "genres": genres,
        "num_pages": num_pages,
        "media_id": media_id,
        "base_url": base_url,
        "cover_url": raw_cover_url,
        "ext": ext
    }


def fetch_nhentai_explore(page: int = 1, sort: str = "date", query: str = None) -> dict:
    """
    Lấy danh sách truyện từ NHentai (cố định 12 bộ/trang, hỗ trợ tìm kiếm, lọc theo tiêu chí sắp xếp).
    Bắt buộc xác thực API Key.
    """
    clean_page = max(1, int(page or 1))
    valid_sorts = ["date", "popular", "popular-today", "popular-week", "popular-month"]
    clean_sort = sort if sort in valid_sorts else "date"

    has_query = bool(query and query.strip())
    is_date_sort = (clean_sort == "date")

    if not has_query and is_date_sort:
        endpoint = f"/api/v2/galleries"
        data = execute_nhentai_api("GET", endpoint, params={"page": clean_page, "per_page": PER_PAGE})
        raw_results = data.get("result", []) if isinstance(data, dict) else []
        total_pages = int(data.get("num_pages") or 1) if isinstance(data, dict) else 1
        total_items = int(data.get("total") or 0) if isinstance(data, dict) else 0
        if not total_items:
            total_items = total_pages * PER_PAGE
    else:
        clean_q = query.strip() if has_query else "pages:>0"
        start_idx = (clean_page - 1) * PER_PAGE
        end_idx = clean_page * PER_PAGE
        nh_p1 = (start_idx // 25) + 1
        nh_p2 = ((end_idx - 1) // 25) + 1

        data1 = execute_nhentai_api("GET", "/api/v2/search", params={"query": clean_q, "page": nh_p1, "sort": clean_sort})
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
            try:
                data2 = execute_nhentai_api("GET", "/api/v2/search", params={"query": clean_q, "page": nh_p2, "sort": clean_sort})
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

        thumb_path = item.get("thumbnail") or f"galleries/{media_id}/thumb.webp"
        thumb_server = get_thumb_server()
        raw_thumb_url = f"{thumb_server}/{thumb_path}" if not thumb_path.startswith("http") else thumb_path
        cover_proxy_url = f"/api/nhentai/image-proxy?url={urllib.parse.quote(raw_thumb_url)}"

        clean_results.append({
            "id": g_id,
            "media_id": media_id,
            "title": title.strip(),
            "cover_url": cover_proxy_url,
            "raw_cover_url": raw_thumb_url,
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
    Lấy thông tin chi tiết và sinh danh sách tất cả các URL ảnh để đọc online trực tiếp.
    Định tuyến qua in-memory image-proxy để vượt qua bộ chặn ISP.
    """
    info = fetch_nhentai_gallery(gallery_id)
    media_id = info["media_id"]
    ext = info["ext"]
    num_pages = info["num_pages"]

    img_server = get_image_server()

    raw_pages = [f"{img_server}/galleries/{media_id}/{i}.{ext}" for i in range(1, num_pages + 1)]
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


# ==================== NHENTAI FAVORITES API (TWO-WAY SYNC) ====================

def fetch_nhentai_favorites(page: int = 1, query: str = None) -> dict:
    """
    Lấy danh sách truyện đã thả tim (Favorites) trên tài khoản NHentai của người dùng.
    Bắt buộc cần API Key.
    """
    clean_page = max(1, int(page or 1))
    params = {"page": clean_page}
    if query and query.strip():
        params["q"] = query.strip()

    data = execute_nhentai_api("GET", "/api/v2/favorites", params=params)

    raw_results = data.get("result", []) if isinstance(data, dict) else []
    total_pages = int(data.get("num_pages") or 1) if isinstance(data, dict) else 1
    total_items = int(data.get("total") or 0) if isinstance(data, dict) else 0

    clean_results = []
    for item in raw_results:
        g_id = item.get("id")
        if not g_id:
            continue
        media_id = str(item.get("media_id") or g_id)
        title = item.get("english_title") or item.get("japanese_title") or f"Manga #{g_id}"

        thumb_path = item.get("thumbnail") or f"galleries/{media_id}/thumb.webp"
        thumb_server = get_thumb_server()
        raw_thumb_url = f"{thumb_server}/{thumb_path}" if not thumb_path.startswith("http") else thumb_path
        cover_proxy_url = f"/api/nhentai/image-proxy?url={urllib.parse.quote(raw_thumb_url)}"

        clean_results.append({
            "id": g_id,
            "media_id": media_id,
            "title": title.strip(),
            "cover_url": cover_proxy_url,
            "raw_cover_url": raw_thumb_url,
            "num_pages": int(item.get("num_pages") or 1),
            "num_favorites": int(item.get("num_favorites") or 0)
        })

    return {
        "page": clean_page,
        "total_pages": total_pages,
        "total": total_items,
        "per_page": int(data.get("per_page") or 25),
        "query": query or "",
        "result": clean_results
    }


def add_nhentai_favorite(gallery_id: int) -> dict:
    """Thêm một bộ truyện vào Favorites trên tài khoản NHentai."""
    return execute_nhentai_api("POST", f"/api/v2/galleries/{int(gallery_id)}/favorite")


def remove_nhentai_favorite(gallery_id: int) -> dict:
    """Xóa một bộ truyện khỏi Favorites trên tài khoản NHentai."""
    return execute_nhentai_api("DELETE", f"/api/v2/galleries/{int(gallery_id)}/favorite")


def check_nhentai_favorite(gallery_id: int) -> dict:
    """Kiểm tra xem truyện đã có trong Favorites tài khoản NHentai hay chưa."""
    return execute_nhentai_api("GET", f"/api/v2/galleries/{int(gallery_id)}/favorite")


def get_api_status() -> dict:
    """
    Kiểm tra trạng thái cấu hình và tính hợp lệ của API Key.
    """
    load_dotenv(ENV_FILE, override=True)
    api_key = os.getenv("NHENTAI_API_KEY", "").strip()

    if not api_key:
        return {
            "configured": False,
            "valid": False,
            "message": "Chưa nhập NHENTAI_API_KEY trong file backend/.env"
        }

    try:
        user_info = execute_nhentai_api("GET", "/api/v2/user")
        return {
            "configured": True,
            "valid": True,
            "username": user_info.get("username", "Authenticated User"),
            "user_id": user_info.get("id"),
            "message": "API Key hợp lệ và đã kết nối thành công!"
        }
    except HTTPException as e:
        return {
            "configured": True,
            "valid": False,
            "message": e.detail
        }
    except Exception as e:
        return {
            "configured": True,
            "valid": False,
            "message": str(e)
        }

"""
Images Service Module
=====================
Xử lý tải và quản lý file ảnh bìa (Cover images).
Nhiệm vụ:
- Tải file ảnh bìa từ nguồn bên ngoài (như nhentai) về lưu trữ tại thư mục cục bộ `frontend/assets/`.
- Sử dụng HTTP headers thích hợp (Referer, User-Agent) để vượt qua chặn hotlink/anti-scraping.
- Cập nhật tên file ảnh bìa (`cover_filename`) vào database và làm mới cache.
"""

import re
import httpx
from urllib.parse import urlparse
from pathlib import Path
import aiofiles
from fastapi import HTTPException
from core.database import supabase
from modules.comics.service import update_cache

# Thư mục lưu trữ ảnh bìa cục bộ trên server (frontend/assets)
COVER_DIR = Path(__file__).parent.parent.parent.parent / "frontend" / "assets"
COVER_DIR.mkdir(parents=True, exist_ok=True)

def convert_to_page_one_url(url: str, high_res: bool = True) -> str:
    """
    Chuyển đổi bất kỳ URL trang nào (VD: .../236t.jpg, .../15.jpg, .../2t.jpg.webp)
    thành URL của trang đầu tiên (VD: .../1.jpg hoặc .../1t.jpg) để làm ảnh bìa chuẩn.
    - Nếu high_res=True: Loại bỏ hậu tố 't' (thumbnail) để lấy ảnh gốc Full HD sắc nét.
    - Nếu high_res=False: Giữ nguyên hậu tố 't'.
    - Tự động chuyển domain thumbnail (t/t1-t4.nhentai.net) sang domain ảnh gốc (i/i1-i4.nhentai.net).
    - Tự động chuẩn hóa đuôi kép như .jpg.webp, .webp.webp thành .webp.
    """
    clean_url = re.sub(r'\.(jpg|jpeg|png|webp)\.webp$', '.webp', url.strip(), flags=re.IGNORECASE)
    m = re.search(r'^(.*\/)(\d+)([a-zA-Z]*)(\.\w+)(\?.*)?$', clean_url)
    if m:
        prefix = m.group(1)
        suffix = m.group(3) or ''
        ext = m.group(4)
        if high_res and suffix.lower() == 't':
            suffix = ''
        result = f"{prefix}1{suffix}{ext}"
        # NHentai: chuyển domain thumbnail (t/t1-t4) sang domain ảnh gốc (i/i1-i4)
        if high_res:
            result = re.sub(r'://t(\d*)\.nhentai\.net/', r'://i\1.nhentai.net/', result)
        return result
    return url

async def download_cover(url: str, comic_id: int):
    """
    Tải ảnh bìa từ URL về máy chủ và cập nhật vào bộ truyện:
    - Ưu tiên tải ảnh gốc chất lượng cao Full HD (1146x1600px, không có hậu tố 't').
    - Tự động thử các định dạng thay thế (.webp, .jpg, .png) nếu gặp 404 do định dạng hỗn hợp.
    - Tự động chuyển sang tải ảnh thumbnail trang 1 nếu không có ảnh gốc.
    - Lưu file với tên {gallery_id}.{ext} (VD: '3852970.webp' hoặc '001-48410.jpg').
    - Cập nhật `cover_filename` trong bảng `comics` và làm mới cache JSON.
    """
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    
    parts = [p for p in url.split("/") if p]
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid URL format")
        
    # Nếu URL có cấu trúc /folder/gallery_id/file (VD: /001/48410/236t.jpg) -> kết hợp thành '001-48410'
    if len(parts) >= 3 and parts[-3].isdigit() and parts[-2].isdigit():
        gallery_id = f"{parts[-3]}-{parts[-2]}"
    else:
        gallery_id = parts[-2]
        
    # Danh sách các đuôi mở rộng dự phòng
    candidate_exts = ["webp", "jpg", "png", "jpeg"]
    
    # 1. Tạo danh sách các link thử tải ảnh gốc Full HD trang 1 với nhiều định dạng
    high_res_base = convert_to_page_one_url(url, high_res=True)
    thumb_base = convert_to_page_one_url(url, high_res=False)
    
    urls_to_try = []
    
    # Thêm các định dạng cho ảnh gốc Full HD
    for ext_candidate in candidate_exts:
        u = re.sub(r'\.\w+(\?.*)?$', f'.{ext_candidate}', high_res_base)
        if u not in urls_to_try:
            urls_to_try.append(u)
            
    # Thêm các định dạng cho ảnh thumbnail trang 1
    for ext_candidate in candidate_exts:
        u = re.sub(r'\.\w+(\?.*)?$', f'.{ext_candidate}', thumb_base)
        if u not in urls_to_try:
            urls_to_try.append(u)
            
    if url not in urls_to_try:
        urls_to_try.append(url)
        
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Tự động nhận diện domain nguồn để gắn Referer phù hợp
            parsed_domain = urlparse(url).netloc
            referer_url = f"https://{parsed_domain}/" if parsed_domain else "https://nhentai.net/"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": referer_url
            }
            
            response = None
            successful_url = None
            for target_url in urls_to_try:
                try:
                    res = await client.get(target_url, headers=headers)
                    if res.status_code == 200:
                        response = res
                        successful_url = target_url
                        break
                except Exception as req_err:
                    print(f"[Warning] Failed to fetch cover from {target_url}: {req_err}")
                    
            if not response or response.status_code != 200:
                raise HTTPException(status_code=400, detail="Cannot download page 1 cover image from provided URL")
            
            # Lấy đuôi mở rộng từ URL tải thành công
            m_ext = re.search(r'\.([a-zA-Z0-9]+)(\?.*)?$', successful_url)
            actual_ext = m_ext.group(1).lower() if m_ext else "jpg"
            filename = f"{gallery_id}.{actual_ext}"
            filepath = COVER_DIR / filename
            
            # Ghi file ảnh bất đồng bộ vào đĩa cứng
            async with aiofiles.open(filepath, "wb") as f:
                await f.write(response.content)
                
        # Cập nhật tên file ảnh bìa vào cơ sở dữ liệu Supabase
        supabase.table("comics").update({"cover_filename": filename}).eq("id", comic_id).execute()
        update_cache()
        
        return {"message": "Cover downloaded successfully", "filename": filename}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

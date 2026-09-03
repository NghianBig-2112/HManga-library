"""
Comics Service Module
=====================
Xử lý toàn bộ logic nghiệp vụ (CRUD) liên quan đến bộ truyện (Comics):
1. Lấy danh sách truyện (kèm thể loại, hỗ trợ lọc theo thể loại và tìm kiếm tên).
2. Lấy chi tiết một bộ truyện kèm danh sách các chương (chapters) và thể loại.
3. Tạo truyện mới và tự động liên kết các thể loại được chọn trong bảng `comic_genres`.
4. Cập nhật thông tin truyện và cập nhật lại danh sách thể loại liên kết.
5. Xóa truyện (tự động dọn dẹp chapters, liên kết thể loại và xóa file ảnh bìa local).
6. Kiểm tra truyện đã tồn tại theo gallery_id của nhentai.
7. Đồng bộ dữ liệu ra file cache JSON cục bộ.
"""

import json
from pathlib import Path
from core.database import supabase
from modules.comics.schemas import ComicCreate, ComicUpdate

# Đường dẫn đến file lưu trữ cache truyện cục bộ (ưu tiên backend/data_cache/comics_cache.json)
_backend_dir = Path(__file__).parent.parent.parent
_data_cache_dir = _backend_dir / "data_cache"
_data_cache_dir.mkdir(parents=True, exist_ok=True)
CACHE_FILE = _data_cache_dir / "comics_cache.json"

def extract_gallery_id_from_url(source_url: str = None, cover_filename: str = None) -> str:
    """
    Trích xuất mã Gallery ID (Media ID) từ URL hoặc tên file ảnh bìa (VD: '4126277' hoặc '001-48410').
    Ưu tiên bóc tách từ cover_filename hoặc từ source_url.
    """
    if cover_filename:
        name_without_ext = cover_filename.rsplit(".", 1)[0]
        if "-" in name_without_ext or name_without_ext.isdigit():
            return name_without_ext

    if source_url:
        parts = [p for p in source_url.split("/") if p]
        if len(parts) >= 3 and parts[-3].isdigit() and parts[-2].isdigit():
            return f"{parts[-3]}-{parts[-2]}"
        elif len(parts) >= 2 and parts[-2].isdigit():
            return parts[-2]
    return ""

def clean_comic_dict(comic: dict) -> dict:
    """
    Loại bỏ hoàn toàn các trường cũ (status, type, personal_note, timestamp) khỏi dictionary truyện.
    """
    if not comic:
        return comic
    for field in ["type", "status", "personal_note", "created_at", "updated_at"]:
        comic.pop(field, None)
    return comic

def clean_chapter_dict(chapter: dict) -> dict:
    """
    Loại bỏ các trường cũ (total_pages, created_at, updated_at) khỏi dictionary chương.
    """
    if not chapter:
        return chapter
    for field in ["total_pages", "created_at", "updated_at"]:
        chapter.pop(field, None)
    return chapter

def get_all_comics(genre: str = None, q: str = None):
    """
    Lấy danh sách tất cả các bộ truyện trong thư viện:
    - Hỗ trợ lọc theo từ khóa tiêu đề (q) không phân biệt hoa thường.
    - Tự động map danh sách thể loại từ bảng `comic_genres` cho từng bộ truyện.
    - Hỗ trợ lọc theo tên thể loại (genre).
    """
    # 1. Truy vấn danh sách truyện từ bảng comics
    query = supabase.table("comics").select("id, title, author, cover_filename, source_url, gallery_id").order("id", desc=False)
    if q:
        query = query.ilike("title", f"%{q}%")
    
    response = query.execute()
    comics = response.data or []
    
    comic_ids = [c["id"] for c in comics]
    if not comic_ids:
        return []
        
    # 2. Truy vấn danh sách thể loại tương ứng cho các bộ truyện theo lô (batch query)
    genres_map = {}
    try:
        genres_response = supabase.table("comic_genres").select("comic_id, genres(name)").in_("comic_id", comic_ids).execute()
        for item in genres_response.data or []:
            c_id = item["comic_id"]
            genre_name = item["genres"]["name"]
            if c_id not in genres_map:
                genres_map[c_id] = []
            genres_map[c_id].append(genre_name)
    except Exception as e:
        print(f"[Warning] Error fetching comic_genres: {e}")
        
    # 3. Gắn danh sách thể loại và gallery_id vào từng object truyện
    result = []
    for comic in comics:
        clean_comic_dict(comic)
        comic["genres"] = genres_map.get(comic["id"], [])
        comic["gallery_id"] = extract_gallery_id_from_url(comic.get("source_url"), comic.get("cover_filename"))
        # Nếu có lọc theo thể loại mà truyện không chứa thể loại đó thì bỏ qua
        if genre and genre not in comic["genres"]:
            continue
        result.append(comic)
        
    return result

def resolve_comic_id(comic_identifier) -> int:
    """
    Chuyển đổi tham số comic_identifier (ID số hoặc chuỗi gallery_id như '001-48410')
    thành ID số nguyên (int) thực tế trong database.
    """
    if comic_identifier is None:
        return None
    if isinstance(comic_identifier, int):
        return comic_identifier
    if isinstance(comic_identifier, str):
        if comic_identifier.isdigit():
            return int(comic_identifier)
        # Tra cứu theo gallery_id hoặc cover_filename hoặc source_url
        try:
            url_pattern = f"%/{comic_identifier.replace('-', '/')}/%"
            res = supabase.table("comics").select("id").or_(f"gallery_id.eq.{comic_identifier},cover_filename.ilike.{comic_identifier}.%,source_url.ilike.{url_pattern}").execute()
            if res.data:
                return res.data[0]["id"]
        except Exception:
            pass
    return None

def get_comic_detail(comic_id):
    """
    Lấy thông tin chi tiết của 1 bộ truyện theo ID (hoặc gallery_id):
    - Thông tin truyện cơ bản (id, gallery_id, title, author, cover_filename, source_url).
    - Danh sách thể loại (genres) của bộ truyện.
    - Danh sách các chương (chapters) đã sắp xếp theo thứ tự chapter_number tăng dần.
    """
    real_id = resolve_comic_id(comic_id)
    if real_id is None:
        return None

    # 1. Lấy thông tin cơ bản từ bảng comics
    response = supabase.table("comics").select("id, title, author, cover_filename, source_url, gallery_id").eq("id", real_id).execute()
    if not response.data:
        return None
    comic = response.data[0]
    clean_comic_dict(comic)
    comic["gallery_id"] = extract_gallery_id_from_url(comic.get("source_url"), comic.get("cover_filename"))
    
    # 2. Lấy danh sách thể loại từ bảng comic_genres
    comic["genres"] = []
    try:
        genres_response = supabase.table("comic_genres").select("genres(name)").eq("comic_id", real_id).execute()
        comic["genres"] = [item["genres"]["name"] for item in genres_response.data or []]
    except Exception as e:
        print(f"[Warning] Error fetching comic_genres: {e}")
    
    # 3. Lấy danh sách các chapters thuộc bộ truyện
    try:
        chapters_response = supabase.table("chapters").select("id, comic_id, chapter_number, title, base_url, start_page, end_page").eq("comic_id", real_id).order("chapter_number").execute()
        chapters = chapters_response.data or []
        for ch in chapters:
            clean_chapter_dict(ch)
            s_page = ch.get("start_page", 1) or 1
            e_page = ch.get("end_page", s_page) or s_page
            ch["start_page"] = s_page
            ch["end_page"] = e_page
            ch["total_pages"] = max(1, e_page - s_page + 1)
        comic["chapters"] = chapters
    except Exception as e:
        comic["chapters"] = []
    
    return comic

def create_comic(comic_data: ComicCreate):
    """
    Tạo mới một bộ truyện:
    1. Tìm hoặc tự động tạo các thể loại trong bảng `genres` để lấy `genre_id`.
    2. Chèn bản ghi truyện vào bảng `comics`.
    3. Tạo liên kết giữa truyện và thể loại trong bảng `comic_genres`.
    4. Cập nhật lại file cache JSON.
    """
    # Bước 1: Lấy danh sách ID của các thể loại đã chọn
    genre_ids = []
    for genre_name in comic_data.genres:
        clean_name = genre_name.strip()
        try:
            genre_res = supabase.table("genres").select("id").ilike("name", clean_name).execute()
            if genre_res.data:
                genre_ids.append(genre_res.data[0]["id"])
            else:
                # Nếu thể loại chưa có sẵn thì tự động tạo mới
                new_genre = supabase.table("genres").insert({"name": clean_name}).execute()
                if new_genre.data:
                    genre_ids.append(new_genre.data[0]["id"])
        except Exception as e:
            print(f"[Warning] Error finding/creating genre: {e}")
            
    # Bước 2: Thêm truyện vào bảng comics (loại bỏ trường genres dạng mảng trước khi insert vào table comics)
    comic_dict = comic_data.model_dump(exclude={"genres"})
    
    # Tự động gán gallery_id theo định dạng 'xxx-xxxxx' nếu chưa có
    if not comic_dict.get("gallery_id") and comic_dict.get("source_url"):
        comic_dict["gallery_id"] = extract_gallery_id_from_url(comic_dict.get("source_url"))
        
    try:
        response = supabase.table("comics").insert(comic_dict).execute()
    except Exception as e:
        # Nếu cột gallery_id chưa có trong bảng Supabase, bỏ qua và insert bình thường
        if "gallery_id" in str(e):
            comic_dict.pop("gallery_id", None)
            response = supabase.table("comics").insert(comic_dict).execute()
        else:
            raise e
            
    new_comic = response.data[0]
    
    # Bước 3: Thêm các bản ghi liên kết vào bảng trung gian comic_genres
    for g_id in genre_ids:
        try:
            supabase.table("comic_genres").insert({"comic_id": new_comic["id"], "genre_id": g_id}).execute()
        except Exception as e:
            print(f"[Warning] Error linking comic_genre: {e}")
        
    # Bước 4: Đồng bộ cache và trả về chi tiết bộ truyện vừa tạo
    update_cache()
    return get_comic_detail(new_comic["id"])

def update_comic(comic_id, comic_data: ComicUpdate):
    """
    Cập nhật thông tin của một bộ truyện:
    - Cập nhật các trường cơ bản (title, author, source_url, gallery_id) nếu có gửi lên.
    - Cập nhật lại danh sách thể loại trong bảng `comic_genres` nếu có truyền genres mới.
    - Đồng bộ lại cache JSON.
    """
    real_id = resolve_comic_id(comic_id)
    if real_id is None:
        return None

    # 1. Cập nhật các trường cơ bản trong bảng comics
    comic_dict = {k: v for k, v in comic_data.model_dump(exclude={"genres"}).items() if v is not None}
    if comic_dict:
        try:
            supabase.table("comics").update(comic_dict).eq("id", real_id).execute()
        except Exception as e:
            if "gallery_id" in str(e):
                comic_dict.pop("gallery_id", None)
                if comic_dict:
                    supabase.table("comics").update(comic_dict).eq("id", real_id).execute()
            else:
                raise e
    
    # 2. Cập nhật lại các liên kết thể loại nếu có
    if comic_data.genres is not None:
        try:
            # Xóa các liên kết thể loại cũ
            supabase.table("comic_genres").delete().eq("comic_id", real_id).execute()
            
            # Thêm các liên kết thể loại mới
            genre_ids = []
            for genre_name in comic_data.genres:
                clean_name = genre_name.strip()
                genre_res = supabase.table("genres").select("id").ilike("name", clean_name).execute()
                if genre_res.data:
                    genre_ids.append(genre_res.data[0]["id"])
                else:
                    new_genre = supabase.table("genres").insert({"name": clean_name}).execute()
                    if new_genre.data:
                        genre_ids.append(new_genre.data[0]["id"])
                    
            for g_id in genre_ids:
                supabase.table("comic_genres").insert({"comic_id": real_id, "genre_id": g_id}).execute()
        except Exception as e:
            print(f"[Warning] Error updating comic_genres: {e}")
        
    update_cache()
    return get_comic_detail(real_id)

def delete_comic(comic_id) -> bool:
    """
    Xóa vĩnh viễn một bộ truyện khỏi hệ thống:
    1. Lấy tên file ảnh bìa (cover_filename) để xóa file local.
    2. Xóa toàn bộ chapters thuộc bộ truyện.
    3. Xóa các liên kết thể loại trong `comic_genres`.
    4. Xóa bản ghi truyện trong bảng `comics`.
    5. Xóa file ảnh bìa vật lý trong thư mục `frontend/assets/`.
    6. Đồng bộ lại cache JSON.
    """
    real_id = resolve_comic_id(comic_id)
    if real_id is None:
        return False

    comic_res = supabase.table("comics").select("cover_filename").eq("id", real_id).execute()
    cover_filename = comic_res.data[0]["cover_filename"] if comic_res.data else None
    
    try:
        supabase.table("chapters").delete().eq("comic_id", real_id).execute()
    except Exception as e:
        print(f"[Warning] Error deleting chapters: {e}")
    try:
        supabase.table("comic_genres").delete().eq("comic_id", real_id).execute()
    except Exception as e:
        print(f"[Warning] Error deleting comic_genres: {e}")
        
    try:
        supabase.table("comics").delete().eq("id", real_id).execute()
    except Exception as e:
        print(f"[Error] Error deleting comic: {e}")
        raise e
    
    # Xóa file ảnh bìa trên đĩa cứng (không bao giờ xóa file rem.jpg hoặc background.jpg)
    if cover_filename and cover_filename.lower() not in ["rem.jpg", "background.jpg"]:
        cover_path = Path(__file__).parent.parent.parent.parent / "frontend" / "assets" / cover_filename
        if not cover_path.exists():
            cover_path = Path(__file__).parent.parent.parent / "frontend" / "assets" / cover_filename
        if not cover_path.exists():
            cover_path = Path("frontend/assets") / cover_filename
        if cover_path.exists():
            try:
                cover_path.unlink()
            except Exception as e:
                print(f"[Warning] Error unlinking cover: {e}")
    
    update_cache()
    return True

def check_comic_by_gallery_id(gallery_id: str):
    """
    Kiểm tra xem truyện tranh đã tồn tại trong thư viện chưa
    thông qua ID gallery (VD: '4126277' hoặc '001-48410').
    - Tra cứu chuỗi `/001/48410/` hoặc `/{gallery_id}/` trong cột source_url.
    - Nếu đã có, trả về object chi tiết truyện kèm danh sách chương để người dùng có thể thêm tiếp chương.
    """
    # Nếu gallery_id có dạng '001-48410' -> chuyển thành path '/001/48410/'
    url_pattern = f"%/{gallery_id.replace('-', '/')}/%"
    response = supabase.table("comics").select("*").ilike("source_url", url_pattern).execute()
    if not response.data and "-" not in gallery_id:
        response = supabase.table("comics").select("*").ilike("source_url", f"%/{gallery_id}/%").execute()
    if response.data:
        comic = response.data[0]
        comic["gallery_id"] = extract_gallery_id_from_url(comic.get("source_url"), comic.get("cover_filename"))
        comic["genres"] = []
        try:
            genres_response = supabase.table("comic_genres").select("genres(name)").eq("comic_id", comic["id"]).execute()
            comic["genres"] = [item["genres"]["name"] for item in genres_response.data or []]
        except Exception:
            pass
        try:
            chapters_response = supabase.table("chapters").select("*").eq("comic_id", comic["id"]).order("chapter_number").execute()
            chapters = chapters_response.data or []
            for ch in chapters:
                s_page = ch.get("start_page", 1) or 1
                e_page = ch.get("end_page", ch.get("total_pages", s_page)) or s_page
                ch["start_page"] = s_page
                ch["end_page"] = e_page
                ch["total_pages"] = max(1, e_page - s_page + 1)
            comic["chapters"] = chapters
        except Exception:
            comic["chapters"] = []
        return comic
    return None

def update_cache():
    """
    Tạo hoặc cập nhật file JSON cache (`comics_cache.json` ở thư mục gốc).
    Lưu trữ danh sách toàn bộ truyện và chương chuẩn, loại bỏ hoàn toàn các trường cũ (status, type...).
    """
    try:
        comics = get_all_comics()
        for comic in comics:
            clean_comic_dict(comic)
            try:
                chapters = supabase.table("chapters").select("id, comic_id, chapter_number, title, base_url, start_page, end_page").eq("comic_id", comic["id"]).order("chapter_number").execute()
                ch_list = chapters.data or []
                for ch in ch_list:
                    clean_chapter_dict(ch)
                    s_page = ch.get("start_page", 1) or 1
                    e_page = ch.get("end_page", s_page) or s_page
                    ch["start_page"] = s_page
                    ch["end_page"] = e_page
                comic["chapters"] = ch_list
            except Exception:
                comic["chapters"] = []
            
        from datetime import datetime
        cache_data = {
            "comics": comics,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Warning] Error update_cache: {e}")

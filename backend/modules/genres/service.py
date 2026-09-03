"""
Genres Service Module
=====================
Xử lý toàn bộ nghiệp vụ quản lý Thể loại (Genres):
1. Lấy danh sách thể loại kèm tính toán số lượng bộ truyện của từng thể loại (`comic_count`).
2. Thêm thể loại mới (chuẩn hóa tên, tránh trùng lặp).
3. Đổi tên thể loại (cập nhật bảng `genres` và đồng bộ cache).
4. Xóa thể loại (xóa khỏi bảng `genres` và bảng trung gian `comic_genres`).
5. Lấy danh sách các bộ truyện thuộc về một thể loại cụ thể.
"""

from fastapi import HTTPException
from core.database import supabase
from modules.comics.service import update_cache

def get_all_genres():
    """
    Lấy danh sách tất cả các thể loại trong cơ sở dữ liệu:
    - Truy vấn bảng `genres`, sắp xếp tên theo thứ tự bảng chữ cái A-Z.
    - Đếm số lần mỗi thể loại xuất hiện trong bảng liên kết `comic_genres` để tính trường `comic_count`.
    - Gán `comic_count` động vào từng thể loại trước khi trả về cho client.
    """
    try:
        # 1. Truy vấn toàn bộ thể loại từ bảng genres
        genres_res = supabase.table("genres").select("*").order("name").execute()
        genres = genres_res.data or []
    except Exception as e:
        print(f"[Warning] Error querying genres: {e}")
        return []
    
    if not genres:
        return []
        
    try:
        # 2. Đếm số lượng truyện thuộc từng thể loại qua bảng trung gian comic_genres
        comic_genres_res = supabase.table("comic_genres").select("genre_id").execute()
        count_map = {}
        for item in comic_genres_res.data or []:
            g_id = item["genre_id"]
            count_map[g_id] = count_map.get(g_id, 0) + 1
            
        # 3. Gán trường tính toán động comic_count vào object thể loại
        for genre in genres:
            genre["comic_count"] = count_map.get(genre["id"], 0)
    except Exception as e:
        print(f"[Warning] Error querying comic_genres: {e}")
        for genre in genres:
            genre["comic_count"] = 0
        
    return genres

def create_genre(name: str):
    """
    Tạo một thể loại mới:
    1. Chuẩn hóa tên (cắt bỏ khoảng trắng thừa).
    2. Kiểm tra xem thể loại đã tồn tại chưa (không phân biệt hoa thường).
       -> Nếu ĐÃ CÓ: Trả về thông báo lỗi thể loại đã tồn tại (HTTP 400).
    3. Chèn bản ghi mới vào bảng `genres`.
    4. Gán `comic_count = 0` (vì thể loại mới tạo chưa gắn với truyện nào) và cập nhật cache.
    """
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Genre name cannot be empty!")

    try:
        # 2. Check if genre exists
        existing = supabase.table("genres").select("*").ilike("name", clean_name).execute()
        if existing.data:
            existing_name = existing.data[0]["name"]
            raise HTTPException(
                status_code=400, 
                detail=f"Genre '{existing_name}' already exists in system!"
            )
            
        # 3. Insert new genre
        res = supabase.table("genres").insert({"name": clean_name}).execute()
        if res.data:
            genre = res.data[0]
            genre["comic_count"] = 0
            update_cache()
            return genre
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Error] Error creating genre: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating genre: {str(e)}")

def update_genre(genre_id: int, new_name: str):
    """
    Rename genre by `genre_id`
    """
    clean_name = new_name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Genre name cannot be empty!")

    try:
        existing = supabase.table("genres").select("*").ilike("name", clean_name).neq("id", genre_id).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail=f"Genre '{existing.data[0]['name']}' already exists!")

        res = supabase.table("genres").update({"name": clean_name}).eq("id", genre_id).execute()
        if res.data:
            update_cache()
            genre = res.data[0]
            try:
                comic_genres_res = supabase.table("comic_genres").select("comic_id").eq("genre_id", genre_id).execute()
                genre["comic_count"] = len(comic_genres_res.data or [])
            except Exception:
                genre["comic_count"] = 0
            return genre
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Error] Error updating genre: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating genre: {str(e)}")

def delete_genre(genre_id: int):
    """
    Xóa một thể loại khỏi hệ thống:
    1. Xóa các liên kết của thể loại này trong bảng trung gian `comic_genres`.
    2. Xóa bản ghi thể loại trong bảng `genres`.
    3. Cập nhật lại cache JSON.
    """
    try:
        # Xóa các liên kết trong bảng trung gian
        supabase.table("comic_genres").delete().eq("genre_id", genre_id).execute()
        # Xóa thể loại trong bảng genres
        supabase.table("genres").delete().eq("id", genre_id).execute()
        update_cache()
    except Exception as e:
        print(f"[Error] Error deleting genre: {e}")
    return True

def get_comics_by_genre_id(genre_id: int):
    """
    Lấy danh sách toàn bộ các bộ truyện thuộc về một thể loại (`genre_id`):
    1. Tìm tất cả `comic_id` có liên kết với `genre_id` trong bảng `comic_genres`.
    2. Lấy thông tin các bộ truyện tương ứng từ bảng `comics`.
    3. Map toàn bộ các thể loại đi kèm của từng bộ truyện và trả về kết quả.
    """
    try:
        # 1. Lấy danh sách comic_id liên kết với thể loại này
        cg_res = supabase.table("comic_genres").select("comic_id").eq("genre_id", genre_id).execute()
        comic_ids = [item["comic_id"] for item in cg_res.data or []]
        if not comic_ids:
            return []
            
        # 2. Lấy thông tin truyện
        comics_res = supabase.table("comics").select("*").in_("id", comic_ids).order("id", desc=False).execute()
        comics = comics_res.data or []
        
        # 3. Lấy tất cả các thể loại của các bộ truyện này để hiển thị đầy đủ trên thẻ truyện
        all_cg_res = supabase.table("comic_genres").select("comic_id, genres(name)").in_("comic_id", comic_ids).execute()
        genres_map = {}
        for item in all_cg_res.data or []:
            c_id = item["comic_id"]
            g_name = item["genres"]["name"]
            if c_id not in genres_map:
                genres_map[c_id] = []
            genres_map[c_id].append(g_name)
            
        for c in comics:
            c["genres"] = genres_map.get(c["id"], [])
            
        return comics
    except Exception as e:
        print(f"[Error] Error get_comics_by_genre_id: {e}")
        return []

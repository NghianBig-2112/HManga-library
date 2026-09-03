r"""
Script Khôi Phục Dữ Liệu Tự Động Từ File comics_cache.json
==========================================================
Chức năng:
1. Đọc toàn bộ dữ liệu truyện, thể loại, và các chapter từ file `comics_cache.json`.
2. Tự động phục hồi bảng `genres`, `comics`, `comic_genres`, `chapters` trên Supabase Database mới.
3. Tự động kiểm tra và tải lại các ảnh bìa (cover images) bị thiếu về thư mục `frontend/assets/`.
4. Đồng bộ hoàn chỉnh cơ sở dữ liệu mà không cần phải nhập lại bằng tay.

Cách sử dụng:
  cd D:\AI_My_Project\HManga-library\backend
  python restore_from_cache.py
"""

import sys
import json
import asyncio
from pathlib import Path

# Đảm bảo in tiếng Việt và Emoji trên Windows không bị lỗi encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo đường dẫn import hoạt động đúng
sys.path.insert(0, str(Path(__file__).parent))

from core.database import supabase
from modules.comics.service import update_cache
from modules.images.service import download_cover

# Đường dẫn file cache JSON và thư mục ảnh bìa
ROOT_DIR = Path(__file__).parent.parent
CACHE_FILE = ROOT_DIR / "backend" / "data_cache" / "comics_cache.json"
if not CACHE_FILE.exists():
    CACHE_FILE = ROOT_DIR / "comics_cache.json"
COVER_DIR = ROOT_DIR / "frontend" / "assets"

async def restore_database():
    print("================================================================")
    print("🚀 BẮT ĐẦU QUÁ TRÌNH PHỤC HỒI DỮ LIỆU TỪ COMICS_CACHE.JSON")
    print("================================================================")

    if not CACHE_FILE.exists():
        print(f"❌ LỖI: Không tìm thấy file cache tại '{CACHE_FILE}'!")
        return

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
    except Exception as e:
        print(f"❌ LỖI: Không thể đọc file JSON cache: {e}")
        return

    comics_list = cache_data.get("comics", [])
    print(f"📦 Đã tìm thấy {len(comics_list)} bộ truyện trong file cache.")

    if not comics_list:
        print("⚠️ File cache không có dữ liệu truyện nào để phục hồi.")
        return

    # Tạo thư mục frontend/assets nếu chưa có
    COVER_DIR.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # BƯỚC 1: Thu thập và phục hồi toàn bộ Thể loại (Genres)
    # -------------------------------------------------------------------------
    print("\n--- [1/3] Đang phục hồi danh mục Thể loại (Genres) ---")
    all_genre_names = set()
    for comic in comics_list:
        for g in comic.get("genres", []):
            if g and g.strip():
                all_genre_names.add(g.strip())

    # Lấy danh sách thể loại hiện có trên Database
    existing_genres_res = supabase.table("genres").select("*").execute()
    existing_genres = {item["name"].lower(): item["id"] for item in (existing_genres_res.data or [])}

    genre_name_to_id = {}
    for g_name in all_genre_names:
        lower_name = g_name.lower()
        if lower_name in existing_genres:
            genre_name_to_id[g_name] = existing_genres[lower_name]
        else:
            try:
                insert_res = supabase.table("genres").insert({"name": g_name}).execute()
                if insert_res.data:
                    new_id = insert_res.data[0]["id"]
                    genre_name_to_id[g_name] = new_id
                    existing_genres[lower_name] = new_id
                    print(f"  + Tạo mới thể loại: '{g_name}' (ID: {new_id})")
            except Exception as ge:
                print(f"  ⚠️ Cảnh báo tạo thể loại '{g_name}': {ge}")

    print(f"✅ Đã đồng bộ {len(genre_name_to_id)} thể loại vào Database.")

    # -------------------------------------------------------------------------
    # BƯỚC 2: Phục hồi từng bộ truyện (Comics) và các Chương (Chapters)
    # -------------------------------------------------------------------------
    print("\n--- [2/3] Đang phục hồi danh sách Truyện & Chương ---")
    restored_comics_count = 0
    restored_chapters_count = 0

    for comic in comics_list:
        c_id = comic.get("id")
        title = comic.get("title", "Không có tiêu đề")
        author = comic.get("author")
        cover_filename = comic.get("cover_filename")
        source_url = comic.get("source_url")
        gallery_id = comic.get("gallery_id")
        genres = comic.get("genres", [])
        chapters = comic.get("chapters", [])

        # 1. Chèn bộ truyện vào bảng comics
        comic_payload = {
            "title": title,
            "author": author,
            "cover_filename": cover_filename,
            "source_url": source_url,
            "gallery_id": gallery_id
        }
        if c_id:
            comic_payload["id"] = c_id

        try:
            # Kiểm tra xem bộ truyện đã có trên DB chưa
            check_exist = None
            if c_id:
                check_exist = supabase.table("comics").select("id").eq("id", c_id).execute()
            if not check_exist or not check_exist.data:
                # Chèn mới
                res = supabase.table("comics").insert(comic_payload).execute()
                real_comic_id = res.data[0]["id"]
            else:
                real_comic_id = check_exist.data[0]["id"]
                # Cập nhật thông tin
                supabase.table("comics").update(comic_payload).eq("id", real_comic_id).execute()

            restored_comics_count += 1
            print(f"\n📚 [{restored_comics_count}/{len(comics_list)}] Phục hồi truyện: '{title}' (ID: {real_comic_id})")

            # 2. Phục hồi liên kết Thể loại (comic_genres)
            # Xóa liên kết cũ nếu có
            supabase.table("comic_genres").delete().eq("comic_id", real_comic_id).execute()
            for g_name in genres:
                g_id = genre_name_to_id.get(g_name)
                if g_id:
                    try:
                        supabase.table("comic_genres").insert({
                            "comic_id": real_comic_id,
                            "genre_id": g_id
                        }).execute()
                    except Exception:
                        pass

            # 3. Phục hồi các Chapter
            for ch in chapters:
                ch_id = ch.get("id")
                ch_num = ch.get("chapter_number", 1)
                ch_title = ch.get("title")
                base_url = ch.get("base_url")
                s_page = ch.get("start_page", 1)
                e_page = ch.get("end_page", ch.get("total_pages", 1))

                chap_payload = {
                    "comic_id": real_comic_id,
                    "chapter_number": ch_num,
                    "title": ch_title,
                    "base_url": base_url,
                    "start_page": s_page,
                    "end_page": e_page
                }
                if ch_id:
                    chap_payload["id"] = ch_id

                try:
                    # Xóa chapter cũ có cùng comic_id & chapter_number nếu đã tồn tại
                    supabase.table("chapters").delete().eq("comic_id", real_comic_id).eq("chapter_number", ch_num).execute()
                    supabase.table("chapters").insert(chap_payload).execute()
                    restored_chapters_count += 1
                    print(f"   ↳ Phục hồi Ch.{ch_num}: {ch_title or ''} ({e_page - s_page + 1} trang)")
                except Exception as che:
                    print(f"   ⚠️ Lỗi phục hồi Chapter {ch_num}: {che}")

            # 4. Tự động kiểm tra và tải lại ảnh bìa nếu chưa có local
            if cover_filename:
                cover_file_path = COVER_DIR / cover_filename
                if not cover_file_path.exists() and source_url:
                    print(f"   📥 Đang tải lại ảnh bìa '{cover_filename}' từ nguồn...")
                    try:
                        await download_cover(source_url, real_comic_id)
                        print(f"   ✅ Đã tải ảnh bìa '{cover_filename}' thành công.")
                    except Exception as img_err:
                        print(f"   ⚠️ Không thể tải ảnh bìa: {img_err}")

        except Exception as ce:
            print(f"❌ Lỗi khi phục hồi bộ truyện '{title}': {ce}")

    # -------------------------------------------------------------------------
    # BƯỚC 3: Reset Auto-Increment Sequences (tránh lỗi trùng ID khi thêm mới)
    # -------------------------------------------------------------------------
    print("\n--- [3/4] Đồng bộ lại Auto-Increment Sequences ---")
    try:
        # Khi insert với ID cụ thể, PostgreSQL sequence không tự cập nhật.
        # Cần reset sequence để ID tiếp theo = MAX(id) + 1, tránh lỗi duplicate key.
        sequence_reset_sql = """
            SELECT setval('comics_id_seq', COALESCE((SELECT MAX(id) FROM comics), 0) + 1, false);
            SELECT setval('chapters_id_seq', COALESCE((SELECT MAX(id) FROM chapters), 0) + 1, false);
            SELECT setval('genres_id_seq', COALESCE((SELECT MAX(id) FROM genres), 0) + 1, false);
        """
        supabase.rpc('exec_sql', {'query': sequence_reset_sql}).execute()
        print("✅ Đã reset sequences thành công (comics, chapters, genres).")
    except Exception as seq_err:
        print(f"⚠️ Không thể tự động reset sequence qua RPC: {seq_err}")
        print("   💡 Nếu gặp lỗi trùng ID khi thêm truyện mới, hãy chạy SQL sau trong Supabase SQL Editor:")
        print("      SELECT setval('comics_id_seq', COALESCE((SELECT MAX(id) FROM comics), 0) + 1, false);")
        print("      SELECT setval('chapters_id_seq', COALESCE((SELECT MAX(id) FROM chapters), 0) + 1, false);")
        print("      SELECT setval('genres_id_seq', COALESCE((SELECT MAX(id) FROM genres), 0) + 1, false);")

    # -------------------------------------------------------------------------
    # BƯỚC 4: Đồng bộ lại Cache
    # -------------------------------------------------------------------------
    print("\n--- [4/4] Đồng bộ lại Cache JSON ---")
    update_cache()
    print("✅ Đã cập nhật lại file 'comics_cache.json'!")

    print("\n================================================================")
    print("🎉 HOÀN TẤT PHỤC HỒI TOÀN BỘ CƠ SỞ DỮ LIỆU THÀNH CÔNG!")
    print(f"📊 Tổng kết: {restored_comics_count} bộ truyện | {restored_chapters_count} chương truyện")
    print("================================================================")

if __name__ == "__main__":
    asyncio.run(restore_database())

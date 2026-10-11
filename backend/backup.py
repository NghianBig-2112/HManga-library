"""
HManga Library - Module Sao Lưu & Khôi Phục Dữ Liệu (Backup & Restore)
======================================================================
Chịu trách nhiệm:
1. Sao lưu (Export): Trích xuất toàn bộ dữ liệu từ 7 bảng trên Supabase ra file `backup.json` ở thư mục gốc.
2. Khôi phục (Restore): Đọc dữ liệu từ file `backup.json` và đồng bộ ngược lại lên Supabase.
"""

import sys
import json
from pathlib import Path
from database import get_connection

# Thiết lập bảng mã UTF-8 cho console Windows để in tiếng Việt không bị lỗi font
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đường dẫn mặc định tới file backup.json nằm ở thư mục gốc của dự án
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKUP_FILE = ROOT_DIR / "backup.json"


# ==================== 1. SAO LƯU DỮ LIỆU (EXPORT) ====================

def export_library_data() -> dict:
    """
    Trích xuất toàn bộ dữ liệu từ 7 bảng trên Supabase và đóng gói thành 1 Dictionary:
    - folders : Danh sách thư mục
    - artists : Danh sách tác giả
    - genres  : Danh sách thể loại
    - comics  : Danh sách bộ truyện (đã lồng sẵn danh sách chapters, artist_ids và genre_ids của từng truyện)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 1: Lấy danh sách toàn bộ thư mục
            cur.execute("SELECT id, name, description FROM folders ORDER BY id ASC;")
            folders = [dict(r) for r in cur.fetchall()]

            # Bước 2: Lấy danh sách toàn bộ tác giả
            cur.execute("SELECT id, name, slug FROM artists ORDER BY id ASC;")
            artists = [dict(r) for r in cur.fetchall()]

            # Bước 3: Lấy danh sách toàn bộ thể loại
            cur.execute("SELECT id, name, slug FROM genres ORDER BY id ASC;")
            genres = [dict(r) for r in cur.fetchall()]

            # Bước 4: Lấy danh sách các bộ truyện (sắp xếp theo thứ tự thêm từ cũ đến mới)
            cur.execute("""
                SELECT id, folder_id, media_id, title, artist, language, category,
                       cover_url, num_pages, page_exts, created_at
                FROM comics
                ORDER BY created_at ASC;
            """)
            comics_rows = cur.fetchall()

            # Bước 5: Gom nhóm danh sách artist_id theo từng comic_id từ bảng nối `comic_artists`
            cur.execute("SELECT comic_id, artist_id FROM comic_artists;")
            comic_artists_map = {}
            for row in cur.fetchall():
                comic_artists_map.setdefault(row["comic_id"], []).append(row["artist_id"])

            # Bước 6: Gom nhóm danh sách genre_id theo từng comic_id từ bảng nối `comic_genres`
            cur.execute("SELECT comic_id, genre_id FROM comic_genres;")
            comic_genres_map = {}
            for row in cur.fetchall():
                comic_genres_map.setdefault(row["comic_id"], []).append(row["genre_id"])

            # Bước 7: Gom nhóm danh sách các tập/chương (chapters) theo từng comic_id
            cur.execute("""
                SELECT comic_id, chapter_number, title, media_id, start_page, end_page, page_exts
                FROM chapters
                ORDER BY comic_id ASC, chapter_number ASC;
            """)
            chapters_map = {}
            for ch in cur.fetchall():
                c_id = ch["comic_id"]
                chapters_map.setdefault(c_id, []).append({
                    "chapter_number": float(ch["chapter_number"]),
                    "title": ch["title"],
                    "media_id": str(ch["media_id"]),
                    "start_page": int(ch["start_page"]),
                    "end_page": int(ch["end_page"]),
                    "page_exts": ch.get("page_exts") or ""
                })

            # Bước 8: Ghép toàn bộ thông tin liên quan vào từng đối tượng truyện
            comics_list = []
            for c in comics_rows:
                c_id = c["id"]
                comics_list.append({
                    "id": c_id,
                    "folder_id": c["folder_id"],
                    "media_id": str(c["media_id"]),
                    "title": c["title"],
                    "artist": c["artist"],
                    "language": c["language"],
                    "category": c["category"],
                    "cover_url": c["cover_url"],
                    "num_pages": int(c["num_pages"]),
                    "page_exts": c.get("page_exts") or "",
                    "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
                    "artist_ids": comic_artists_map.get(c_id, []),
                    "genre_ids": comic_genres_map.get(c_id, []),
                    "chapters": chapters_map.get(c_id, [])
                })

            return {
                "folders": folders,
                "artists": artists,
                "genres": genres,
                "comics": comics_list
            }


def save_backup_file(filepath: Path = None) -> str:
    """
    Gọi `export_library_data()` và ghi kết quả ra file `backup.json` với định dạng UTF-8 đẹp mắt (indent=2).
    """
    target_path = filepath or BACKUP_FILE
    data = export_library_data()

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(
        f"[BACKUP THÀNH CÔNG] Đã lưu {len(data['comics'])} bộ truyện, "
        f"{len(data['folders'])} thư mục vào: {target_path}"
    )
    return str(target_path)


# ==================== 2. KHÔI PHỤC DỮ LIỆU (RESTORE) ====================

def restore_backup_from_file(filepath: Path = None) -> dict:
    """
    Đọc file `backup.json` và khôi phục toàn bộ dữ liệu lên lại Supabase theo đúng thứ tự khóa ngoại:
    1. Bảng `folders` (kèm đồng bộ lại bộ đếm tự tăng ID)
    2. Bảng `artists` & `genres`
    3. Bảng `comics`, bảng nối `comic_artists` / `comic_genres`, và bảng `chapters`
    """
    target_path = filepath or BACKUP_FILE
    if not target_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file sao lưu tại: {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    folders = data.get("folders", [])
    artists = data.get("artists", [])
    genres = data.get("genres", [])
    comics = data.get("comics", [])

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 1: Khôi phục bảng `folders` (giữ nguyên ID gốc của từng thư mục)
            for folder in folders:
                cur.execute("""
                    INSERT INTO folders (id, name, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description;
                """, (folder["id"], folder["name"], folder.get("description", "")))

            # Đồng bộ lại bộ đếm tự tăng (sequence) của cột `folders.id` để tránh lỗi trùng ID khi tạo thư mục mới sau này
            cur.execute("""
                SELECT setval(
                    pg_get_serial_sequence('folders', 'id'),
                    COALESCE((SELECT MAX(id) FROM folders), 1),
                    true
                );
            """)

            # Bước 2: Khôi phục bảng `artists`
            for artist in artists:
                cur.execute("""
                    INSERT INTO artists (id, name, slug)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        slug = EXCLUDED.slug;
                """, (artist["id"], artist["name"], artist["slug"]))

            # Bước 3: Khôi phục bảng `genres`
            for genre in genres:
                cur.execute("""
                    INSERT INTO genres (id, name, slug)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        slug = EXCLUDED.slug;
                """, (genre["id"], genre["name"], genre["slug"]))

            # Bước 4: Khôi phục từng bộ truyện trong bảng `comics` kèm các bảng liên kết và `chapters`
            for c in comics:
                c_id = c["id"]
                page_exts = c.get("page_exts") or ""

                # Nếu bản sao lưu có sẵn mốc thời gian `created_at` thì khôi phục đúng thời gian đó
                if c.get("created_at"):
                    cur.execute("""
                        INSERT INTO comics (
                            id, folder_id, media_id, title, artist, language,
                            category, cover_url, num_pages, page_exts, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            folder_id = EXCLUDED.folder_id,
                            media_id = EXCLUDED.media_id,
                            title = EXCLUDED.title,
                            artist = EXCLUDED.artist,
                            language = EXCLUDED.language,
                            category = EXCLUDED.category,
                            cover_url = EXCLUDED.cover_url,
                            num_pages = EXCLUDED.num_pages,
                            page_exts = EXCLUDED.page_exts,
                            created_at = EXCLUDED.created_at;
                    """, (
                        c_id, c.get("folder_id", 1), str(c["media_id"]), c["title"],
                        c.get("artist", "Unknown"), c.get("language", "Unknown"),
                        c.get("category", "Unknown"), c["cover_url"],
                        int(c["num_pages"]), page_exts, c["created_at"]
                    ))
                else:
                    cur.execute("""
                        INSERT INTO comics (
                            id, folder_id, media_id, title, artist, language,
                            category, cover_url, num_pages, page_exts
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            folder_id = EXCLUDED.folder_id,
                            media_id = EXCLUDED.media_id,
                            title = EXCLUDED.title,
                            artist = EXCLUDED.artist,
                            language = EXCLUDED.language,
                            category = EXCLUDED.category,
                            cover_url = EXCLUDED.cover_url,
                            num_pages = EXCLUDED.num_pages,
                            page_exts = EXCLUDED.page_exts;
                    """, (
                        c_id, c.get("folder_id", 1), str(c["media_id"]), c["title"],
                        c.get("artist", "Unknown"), c.get("language", "Unknown"),
                        c.get("category", "Unknown"), c["cover_url"],
                        int(c["num_pages"]), page_exts
                    ))

                # 4a. Khôi phục liên kết Truyện - Tác giả (`comic_artists`)
                for a_id in c.get("artist_ids", []):
                    cur.execute("""
                        INSERT INTO comic_artists (comic_id, artist_id)
                        VALUES (%s, %s)
                        ON CONFLICT (comic_id, artist_id) DO NOTHING;
                    """, (c_id, a_id))

                # 4b. Khôi phục liên kết Truyện - Thể loại (`comic_genres`)
                for g_id in c.get("genre_ids", []):
                    cur.execute("""
                        INSERT INTO comic_genres (comic_id, genre_id)
                        VALUES (%s, %s)
                        ON CONFLICT (comic_id, genre_id) DO NOTHING;
                    """, (c_id, g_id))

                # 4c. Làm mới và khôi phục danh sách `chapters` của bộ truyện
                cur.execute("DELETE FROM chapters WHERE comic_id = %s;", (c_id,))
                chaps = c.get("chapters", [])
                if chaps:
                    for ch in chaps:
                        cur.execute("""
                            INSERT INTO chapters (
                                comic_id, chapter_number, title, media_id,
                                start_page, end_page, page_exts
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """, (
                            c_id,
                            ch["chapter_number"],
                            ch.get("title", "Toàn bộ"),
                            str(ch.get("media_id", c["media_id"])),
                            int(ch.get("start_page", 1)),
                            int(ch.get("end_page", c["num_pages"])),
                            ch.get("page_exts") or page_exts
                        ))
                else:
                    # Nếu bản sao lưu cũ không có trường chapters thì tự tạo Chapter 1 ("Toàn bộ")
                    cur.execute("""
                        INSERT INTO chapters (
                            comic_id, chapter_number, title, media_id,
                            start_page, end_page, page_exts
                        )
                        VALUES (%s, 1, 'Toàn bộ', %s, 1, %s, %s);
                    """, (c_id, str(c["media_id"]), int(c["num_pages"]), page_exts))

        conn.commit()

    print(f"[KHÔI PHỤC THÀNH CÔNG] Đã nạp {len(comics)} bộ truyện từ {target_path.name} lên Supabase!")
    return {
        "success": True,
        "restored_comics": len(comics),
        "restored_folders": len(folders)
    }


# ==================== 3. GIAO DIỆN DÒNG LỆNH (CLI) ====================
if __name__ == "__main__":
    print("=" * 55)
    print(" CÔNG CỤ SAO LƯU & KHÔI PHỤC DỮ LIỆU (BACKUP.JSON)")
    print("=" * 55)
    print(f"Đường dẫn file sao lưu: {BACKUP_FILE}")
    print("1. Sao lưu dữ liệu từ Supabase ra file backup.json (Export)")
    print("2. Khôi phục dữ liệu từ file backup.json lên Supabase (Restore)")
    print("0. Thoát")
    print("-" * 55)

    choice = input("Nhập lựa chọn của bạn (1 / 2 / 0): ").strip()
    if choice == "1":
        save_backup_file()
    elif choice == "2":
        restore_backup_from_file()
    else:
        print("Đã thoát.")
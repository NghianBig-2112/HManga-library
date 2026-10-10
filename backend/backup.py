"""
HManga Library - Backup & Restore Module (PostgreSQL / Supabase)
================================================================
Dùng để:
1. Sao lưu (Export) toàn bộ dữ liệu từ Supabase ra file 'backup.json' (để push lên GitHub).
2. Khôi phục (Restore) toàn bộ dữ liệu từ file 'backup.json' lên lại Supabase.
"""

import sys
import json
from pathlib import Path
from database import get_connection

# Thiết lập encoding utf-8 cho console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKUP_FILE = ROOT_DIR / "backup.json"


def export_library_data() -> dict:
    """
    Trích xuất toàn bộ dữ liệu từ 7 bảng trên Supabase sang dict để lưu ra JSON:
    - folders
    - artists
    - genres
    - comics (kèm chapters, artist_ids, genre_ids)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Lấy danh sách thư mục
            cur.execute("SELECT id, name, description FROM folders ORDER BY id ASC;")
            folders = [dict(r) for r in cur.fetchall()]

            # 2. Lấy danh sách tác giả
            cur.execute("SELECT id, name, slug FROM artists ORDER BY id ASC;")
            artists = [dict(r) for r in cur.fetchall()]

            # 3. Lấy danh sách thể loại
            cur.execute("SELECT id, name, slug FROM genres ORDER BY id ASC;")
            genres = [dict(r) for r in cur.fetchall()]

            # 4. Lấy danh sách truyện
            cur.execute("""
                SELECT id, folder_id, media_id, title, artist, language, category,
                       cover_url, num_pages, page_exts, created_at
                FROM comics
                ORDER BY created_at ASC;
            """)
            comics_rows = cur.fetchall()

            # 5. Lấy bảng nối comic_artists
            cur.execute("SELECT comic_id, artist_id FROM comic_artists;")
            comic_artists_map = {}
            for row in cur.fetchall():
                comic_artists_map.setdefault(row["comic_id"], []).append(row["artist_id"])

            # 6. Lấy bảng nối comic_genres
            cur.execute("SELECT comic_id, genre_id FROM comic_genres;")
            comic_genres_map = {}
            for row in cur.fetchall():
                comic_genres_map.setdefault(row["comic_id"], []).append(row["genre_id"])

            # 7. Lấy danh sách chapters
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
    """Xuất toàn bộ dữ liệu từ Supabase và lưu vào file backup.json."""
    target_path = filepath or BACKUP_FILE
    data = export_library_data()

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(
        f"[BACKUP THÀNH CÔNG] Đã lưu {len(data['comics'])} bộ truyện, "
        f"{len(data['folders'])} thư mục vào: {target_path}"
    )
    return str(target_path)


def restore_backup_from_file(filepath: Path = None) -> dict:
    """Đọc file backup.json và khôi phục toàn bộ dữ liệu lên lại Supabase."""
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
            # 1. Khôi phục bảng folders
            for folder in folders:
                cur.execute("""
                    INSERT INTO folders (id, name, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description;
                """, (folder["id"], folder["name"], folder.get("description", "")))

            # Đồng bộ lại bộ đếm tự tăng (sequence) của bảng folders
            cur.execute("""
                SELECT setval(
                    pg_get_serial_sequence('folders', 'id'),
                    COALESCE((SELECT MAX(id) FROM folders), 1),
                    true
                );
            """)

            # 2. Khôi phục bảng artists
            for artist in artists:
                cur.execute("""
                    INSERT INTO artists (id, name, slug)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        slug = EXCLUDED.slug;
                """, (artist["id"], artist["name"], artist["slug"]))

            # 3. Khôi phục bảng genres
            for genre in genres:
                cur.execute("""
                    INSERT INTO genres (id, name, slug)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        slug = EXCLUDED.slug;
                """, (genre["id"], genre["name"], genre["slug"]))

            # 4. Khôi phục bảng comics, chapters, comic_artists, comic_genres
            for c in comics:
                c_id = c["id"]
                page_exts = c.get("page_exts") or ""

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

                # Liên kết comic_artists
                for a_id in c.get("artist_ids", []):
                    cur.execute("""
                        INSERT INTO comic_artists (comic_id, artist_id)
                        VALUES (%s, %s)
                        ON CONFLICT (comic_id, artist_id) DO NOTHING;
                    """, (c_id, a_id))

                # Liên kết comic_genres
                for g_id in c.get("genre_ids", []):
                    cur.execute("""
                        INSERT INTO comic_genres (comic_id, genre_id)
                        VALUES (%s, %s)
                        ON CONFLICT (comic_id, genre_id) DO NOTHING;
                    """, (c_id, g_id))

                # Khôi phục chapters của bộ truyện
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
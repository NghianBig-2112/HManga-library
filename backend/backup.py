"""
Backup Module
=============
Xuất dữ liệu thư viện truyện ra file JSON và khôi phục dữ liệu vào SQLite.
Hỗ trợ sao lưu tự động, đồng bộ Git, tải lại ảnh bìa và CLI.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
import sys
import asyncio
# Hỗ trợ in tiếng Việt trên console Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import httpx
import aiofiles

from database import get_db as get_db_connection

# Đường dẫn file
DATA_CACHE_DIR = Path(__file__).parent / "data_cache"
BACKUP_FILE = DATA_CACHE_DIR / "backup.json"
COVER_DIR = Path(__file__).parent.parent / "frontend" / "assets"


def export_library_data() -> dict:
    """
    Trích xuất toàn bộ dữ liệu từ SQLite sang cấu trúc từ điển (dict).
    Bao gồm danh sách thể loại, danh sách truyện và các chương tương ứng.
    """
    conn = get_db_connection()
    try:
        # 1. Danh sách thể loại & Danh sách tác giả (chỉ lấy các mục đang có truyện)
        genre_rows = conn.execute("""
            SELECT DISTINCT g.name FROM genres g
            JOIN comic_genres cg ON g.id = cg.genre_id
            ORDER BY g.name ASC
        """).fetchall()
        genres_list = [r["name"] for r in genre_rows]

        author_rows = conn.execute("SELECT name FROM authors ORDER BY name ASC").fetchall()
        authors_list = [r["name"] for r in author_rows]

        # 2. Danh sách truyện
        comic_rows = conn.execute(
            "SELECT id, gallery_id, title, author, cover_filename, source_url FROM comics ORDER BY id ASC"
        ).fetchall()

        comics_data = []
        for c in comic_rows:
            c_id = c["id"]

            # Lấy thể loại của từng truyện
            cg_rows = conn.execute(
                """
                SELECT g.name FROM comic_genres cg
                JOIN genres g ON cg.genre_id = g.id
                WHERE cg.comic_id = ?
                ORDER BY g.name ASC
                """,
                (c_id,)
            ).fetchall()
            comic_genres = [g["name"] for g in cg_rows]

            # Lấy tác giả của từng truyện
            ca_rows = conn.execute(
                """
                SELECT a.name FROM comic_authors ca
                JOIN authors a ON ca.author_id = a.id
                WHERE ca.comic_id = ?
                ORDER BY a.name ASC
                """,
                (c_id,)
            ).fetchall()
            comic_authors = [a["name"] for a in ca_rows]
            if not comic_authors and c["author"]:
                comic_authors = [a.strip() for a in c["author"].split(",") if a.strip()]

            # Lấy các chương của từng truyện
            ch_rows = conn.execute(
                """
                SELECT chapter_number, title, base_url, start_page, end_page
                FROM chapters
                WHERE comic_id = ?
                ORDER BY chapter_number ASC
                """,
                (c_id,)
            ).fetchall()
            chapters_data = [
                {
                    "chapter_number": ch["chapter_number"],
                    "title": ch["title"],
                    "base_url": ch["base_url"],
                    "start_page": ch["start_page"],
                    "end_page": ch["end_page"]
                }
                for ch in ch_rows
            ]

            comics_data.append({
                "gallery_id": c["gallery_id"],
                "title": c["title"],
                "author": c["author"],
                "authors": comic_authors,
                "cover_filename": c["cover_filename"],
                "source_url": c["source_url"],
                "genres": comic_genres,
                "chapters": chapters_data
            })

        return {
            "thoi_gian_sao_luu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "phien_ban": "1.1",
            "tong_so_truyen": len(comics_data),
            "danh_sach_the_loai": genres_list,
            "danh_sach_tac_gia": authors_list,
            "danh_sach_truyen": comics_data
        }
    finally:
        conn.close()


def save_backup_file(filepath: Path = BACKUP_FILE) -> str:
    """
    Xuất dữ liệu và lưu vào file backup.json trên đĩa.
    """
    DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = export_library_data()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(filepath)


async def _download_cover_if_missing(cover_filename: str, base_url: str):
    """Tải lại ảnh bìa nếu file ảnh chưa tồn tại trên máy."""
    if not cover_filename or not base_url:
        return
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = COVER_DIR / cover_filename
    if cover_path.exists():
        return

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://nhentai.net/"
            }
            res = await client.get(base_url, headers=headers)
            if res.status_code == 200:
                async with aiofiles.open(cover_path, "wb") as f:
                    await f.write(res.content)
    except Exception as e:
        print(f"[Backup] Khong the tai lai anh bia {cover_filename}: {e}")


def restore_backup_data(data: dict, redownload_covers: bool = True) -> dict:
    """
    Khôi phục dữ liệu từ từ điển dữ liệu sao lưu vào cơ sở dữ liệu SQLite.
    Nếu chưa có thể loại, tự động thêm thể loại.
    Nếu chưa có truyện, tự động thêm truyện và các chương.
    """
    comics = data.get("danh_sach_truyen", [])
    genres = data.get("danh_sach_the_loai", [])

    conn = get_db_connection()
    restored_comics = 0
    restored_chapters = 0
    covers_to_download = []

    try:
        # 1. Khôi phục thể loại
        for genre_name in genres:
            clean = genre_name.strip()
            if clean:
                conn.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (clean,))

        # 2. Khôi phục từng bộ truyện
        for c in comics:
            title = c.get("title")
            if not title:
                continue

            gallery_id = str(c.get("gallery_id") or "")
            source_url = c.get("source_url") or (f"https://nhentai.net/g/{gallery_id}/" if gallery_id else "")
            author = c.get("author") or "Unknown"
            cover_filename = c.get("cover_filename") or (f"{gallery_id}.jpg" if gallery_id else "")

            # Kiểm tra xem truyện đã có trong DB chưa
            existing = None
            if gallery_id:
                existing = conn.execute(
                    "SELECT id FROM comics WHERE gallery_id = ? OR source_url = ?",
                    (gallery_id, source_url)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM comics WHERE title = ?",
                    (title,)
                ).fetchone()

            if existing:
                comic_id = existing["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO comics (gallery_id, title, author, cover_filename, source_url) VALUES (?, ?, ?, ?, ?)",
                    (gallery_id, title, author, cover_filename, source_url)
                )
                comic_id = cur.lastrowid
                restored_comics += 1

            # Gắn thể loại cho truyện
            comic_genres = c.get("genres", [])
            for g_name in comic_genres:
                clean_g = g_name.strip()
                if not clean_g:
                    continue
                g_row = conn.execute("SELECT id FROM genres WHERE name = ? COLLATE NOCASE", (clean_g,)).fetchone()
                if g_row:
                    g_id = g_row["id"]
                else:
                    g_cur = conn.execute("INSERT INTO genres (name) VALUES (?)", (clean_g,))
                    g_id = g_cur.lastrowid
                conn.execute("INSERT OR IGNORE INTO comic_genres (comic_id, genre_id) VALUES (?, ?)", (comic_id, g_id))

            # Gắn tác giả cho truyện
            comic_authors = c.get("authors")
            if not comic_authors and author:
                comic_authors = [a.strip() for a in author.split(",") if a.strip()]
            if not comic_authors:
                comic_authors = ["Unknown"]

            for a_name in comic_authors:
                clean_a = a_name.strip()
                if not clean_a:
                    continue
                a_row = conn.execute("SELECT id FROM authors WHERE name = ? COLLATE NOCASE", (clean_a,)).fetchone()
                if a_row:
                    a_id = a_row["id"]
                else:
                    a_cur = conn.execute("INSERT INTO authors (name) VALUES (?)", (clean_a,))
                    a_id = a_cur.lastrowid
                conn.execute("INSERT OR IGNORE INTO comic_authors (comic_id, author_id) VALUES (?, ?)", (comic_id, a_id))

            # Khôi phục các chương
            chapters = c.get("chapters", [])
            for ch in chapters:
                ch_num = float(ch.get("chapter_number", 1.0))
                ch_title = ch.get("title") or f"Chương {int(ch_num) if ch_num == int(ch_num) else ch_num}"
                base_url = ch.get("base_url") or ""
                start_p = int(ch.get("start_page", 1))
                end_p = int(ch.get("end_page", 1))

                # Kiểm tra chương trùng
                ch_exists = conn.execute(
                    "SELECT id FROM chapters WHERE comic_id = ? AND chapter_number = ?",
                    (comic_id, ch_num)
                ).fetchone()

                if not ch_exists:
                    conn.execute(
                        "INSERT INTO chapters (comic_id, chapter_number, title, base_url, start_page, end_page) VALUES (?, ?, ?, ?, ?, ?)",
                        (comic_id, ch_num, ch_title, base_url, start_p, end_p)
                    )
                    restored_chapters += 1

                # Chuẩn bị danh sách ảnh bìa cần tải
                if redownload_covers and cover_filename and base_url:
                    covers_to_download.append((cover_filename, base_url))

        conn.commit()
    finally:
        conn.close()

    # Tải lại ảnh bìa nếu thiếu (chạy ngầm bất đồng bộ)
    if redownload_covers and covers_to_download:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for c_file, b_url in covers_to_download:
                    asyncio.create_task(_download_cover_if_missing(c_file, b_url))
            else:
                async def _download_all():
                    tasks = [_download_cover_if_missing(cf, bu) for cf, bu in covers_to_download]
                    await asyncio.gather(*tasks, return_exceptions=True)
                asyncio.run(_download_all())
        except Exception as e:
            print(f"[Backup] Khong the kich hoat tai anh bia: {e}")

    return {
        "so_truyen_khoi_phuc": restored_comics,
        "so_chuong_khoi_phuc": restored_chapters,
        "tong_so_truyen": len(comics)
    }


def restore_backup_from_file(filepath: Path = BACKUP_FILE, redownload_covers: bool = True) -> dict:
    """Đọc file JSON và khôi phục vào SQLite."""
    if not filepath.exists():
        return {"error": f"Không tìm thấy file sao lưu tại {filepath}"}
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return restore_backup_data(data, redownload_covers=redownload_covers)


def get_backup_info(filepath: Path = BACKUP_FILE) -> dict:
    """Lấy thông tin trạng thái file sao lưu hiện tại."""
    if not filepath.exists():
        return {
            "exists": False,
            "filename": filepath.name,
            "updated_at": None,
            "size_bytes": 0,
            "total_comics": 0
        }

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        stat = filepath.stat()
        return {
            "exists": True,
            "filename": filepath.name,
            "updated_at": data.get("thoi_gian_sao_luu") or datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": stat.st_size,
            "total_comics": len(data.get("danh_sach_truyen", []))
        }
    except Exception:
        stat = filepath.stat()
        return {
            "exists": True,
            "filename": filepath.name,
            "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": stat.st_size,
            "total_comics": 0
        }


# ==================== CLI USAGE ====================
if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if not args or args[0] == "export":
        print("[INFO] Đang trích xuất dữ liệu ra file backup.json...")
        p = save_backup_file()
        info = get_backup_info()
        print(f"[THÀNH CÔNG] Đã lưu sao lưu tại: {p}")
        print(f"Tổng số truyện sao lưu: {info['total_comics']} (Dung lượng: {info['size_bytes']} bytes)")
    elif args[0] == "import":
        print(f"[INFO] Đang khôi phục dữ liệu từ {BACKUP_FILE}...")
        res = restore_backup_from_file()
        print(f"[THÀNH CÔNG] Đã khôi phục {res.get('so_truyen_khoi_phuc', 0)} truyện và {res.get('so_chuong_khoi_phuc', 0)} chương.")
    else:
        print("Cách sử dụng:")
        print("  python backend/backup.py export  -> Xuất dữ liệu ra file backup.json")
        print("  python backend/backup.py import  -> Khôi phục dữ liệu từ file backup.json")

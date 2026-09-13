"""
Services Module
================
Toàn bộ business logic cho Comics, Chapters, Genres, Authors, Images.
"""

import re
import urllib.parse
from pathlib import Path
from fastapi import HTTPException

import sqlite3
from database import get_db
from nhentai import (
    fetch_nhentai_gallery,
    fetch_nhentai_explore,
    fetch_nhentai_online_pages,
    get_nhentai_image_proxy_data,
)
from backup import (
    save_backup_file,
    restore_backup_from_file,
    BACKUP_FILE,
)

# Thư mục lưu ảnh bìa
COVER_DIR = Path(__file__).parent.parent / "frontend" / "assets"
COVER_DIR.mkdir(parents=True, exist_ok=True)


# ==================== BACKUP & RESTORE HELPERS ====================

def trigger_auto_backup():
    """Tự động lưu bản sao lưu mới nhất ra file backup.json."""
    try:
        save_backup_file()
    except Exception as e:
        print(f"[Warning] Auto backup failed: {e}")


def auto_restore_if_empty() -> bool:
    """Nếu cơ sở dữ liệu SQLite chưa có truyện nào và file backup.json tồn tại, tự động khôi phục."""
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) as cnt FROM comics").fetchone()["cnt"]
        if count == 0 and BACKUP_FILE.exists():
            print("[INFO] Cơ sở dữ liệu trống, tìm thấy backup.json. Đang tự động khôi phục...")
            res = restore_backup_from_file(BACKUP_FILE, redownload_covers=True)
            print(f"[THÀNH CÔNG] Đã tự động khôi phục {res.get('so_truyen_khoi_phuc', 0)} truyện từ backup.json!")
            return True
        return False
    except Exception as e:
        print(f"[Warning] Auto restore failed: {e}")
        return False
    finally:
        conn.close()


# ==================== HELPER ====================

def _attach_genres(conn, comics: list) -> list:
    """Batch query và gắn danh sách thể loại vào danh sách truyện."""
    comic_ids = [c["id"] for c in comics]
    if not comic_ids:
        return comics
    placeholders = ",".join("?" * len(comic_ids))
    rows = conn.execute(
        f"""
        SELECT cg.comic_id, g.name
        FROM comic_genres cg
        JOIN genres g ON cg.genre_id = g.id
        WHERE cg.comic_id IN ({placeholders})
        """,
        comic_ids
    ).fetchall()
    genres_map = {}
    for r in rows:
        genres_map.setdefault(r["comic_id"], []).append(r["name"])
    for c in comics:
        c["genres"] = genres_map.get(c["id"], [])
    return comics


def _attach_authors(conn, comics: list) -> list:
    """Gắn danh sách authors vào từng comic dict."""
    if not comics:
        return comics
    comic_ids = [c["id"] for c in comics]
    placeholders = ",".join("?" * len(comic_ids))
    rows = conn.execute(
        f"""
        SELECT ca.comic_id, a.name
        FROM comic_authors ca
        JOIN authors a ON ca.author_id = a.id
        WHERE ca.comic_id IN ({placeholders})
        ORDER BY a.name ASC
        """,
        comic_ids
    ).fetchall()
    authors_map = {}
    for r in rows:
        authors_map.setdefault(r["comic_id"], []).append(r["name"])
    for c in comics:
        attached = authors_map.get(c["id"], [])
        if not attached and c.get("author"):
            attached = [a.strip() for a in c["author"].split(",") if a.strip()]
        c["authors"] = attached
        if not c.get("author") and attached:
            c["author"] = ", ".join(attached)
    return comics


def _find_or_create_genres(conn, genre_names: list) -> list:
    """Tìm hoặc tạo mới genres, trả về danh sách genre_id."""
    genre_ids = []
    for name in genre_names:
        clean = name.strip()
        if not clean:
            continue
        row = conn.execute("SELECT id FROM genres WHERE name = ? COLLATE NOCASE", (clean,)).fetchone()
        if row:
            genre_ids.append(row["id"])
        else:
            cur = conn.execute("INSERT INTO genres (name) VALUES (?)", (clean,))
            genre_ids.append(cur.lastrowid)
    return genre_ids


def _find_or_create_authors(conn, author_names: list) -> list:
    """Tìm hoặc tạo mới authors, trả về danh sách author_id."""
    author_ids = []
    for name in author_names:
        clean = name.strip()
        if not clean:
            continue
        row = conn.execute("SELECT id FROM authors WHERE name = ? COLLATE NOCASE", (clean,)).fetchone()
        if row:
            author_ids.append(row["id"])
        else:
            cur = conn.execute("INSERT INTO authors (name) VALUES (?)", (clean,))
            author_ids.append(cur.lastrowid)
    return author_ids


def _chapter_with_total(ch: dict) -> dict:
    """Tính toán total_pages cho chapter dict."""
    s = ch.get("start_page", 1) or 1
    e = ch.get("end_page", s) or s
    ch["start_page"] = s
    ch["end_page"] = e
    ch["total_pages"] = max(1, e - s + 1)
    return ch


# ==================== COMICS ====================

def get_all_comics(genre: str = None, q: str = None, author: str = None):
    """Lấy danh sách truyện, hỗ trợ tìm kiếm theo tên, lọc theo thể loại và tác giả."""
    if q or genre or author:
        return search_comics(q=q, genre=genre, author=author)

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, title, author, cover_filename, source_url, gallery_id FROM comics ORDER BY id ASC"
        ).fetchall()
        comics = [dict(r) for r in rows]
        if not comics:
            return []

        _attach_genres(conn, comics)
        _attach_authors(conn, comics)
        return comics
    finally:
        conn.close()


def get_comic_detail(comic_id: int):
    """Lấy chi tiết truyện kèm genres, authors và chapters."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, title, author, cover_filename, source_url, gallery_id FROM comics WHERE id = ?",
            (comic_id,)
        ).fetchone()
        if not row:
            return None
        comic = dict(row)

        # Authors
        author_rows = conn.execute(
            "SELECT a.name FROM comic_authors ca JOIN authors a ON ca.author_id = a.id WHERE ca.comic_id = ? ORDER BY a.name",
            (comic_id,)
        ).fetchall()
        authors_list = [r["name"] for r in author_rows]
        if not authors_list and comic.get("author"):
            authors_list = [a.strip() for a in comic["author"].split(",") if a.strip()]
        comic["authors"] = authors_list
        if not comic.get("author") and authors_list:
            comic["author"] = ", ".join(authors_list)

        # Genres
        genre_rows = conn.execute(
            "SELECT g.name FROM comic_genres cg JOIN genres g ON cg.genre_id = g.id WHERE cg.comic_id = ? ORDER BY g.name",
            (comic_id,)
        ).fetchall()
        comic["genres"] = [r["name"] for r in genre_rows]

        # Chapters
        ch_rows = conn.execute(
            "SELECT id, comic_id, chapter_number, title, base_url, start_page, end_page FROM chapters WHERE comic_id = ? ORDER BY chapter_number ASC",
            (comic_id,)
        ).fetchall()
        comic["chapters"] = [_chapter_with_total(dict(r)) for r in ch_rows]

        return comic
    finally:
        conn.close()


def preview_comic_by_id(gallery_id: int) -> dict:
    """Lấy thông tin xem trước của bộ truyện từ NHentai (kiểm tra trạng thái đã có trong DB hay chưa)."""
    clean_id = int(gallery_id)

    # 1. Kiểm tra xem truyện đã có trong thư viện chưa
    conn = get_db()
    existing_comic = None
    try:
        row = conn.execute(
            "SELECT id, title, author, cover_filename FROM comics WHERE gallery_id = ? OR source_url LIKE ?",
            (str(clean_id), f"%/{clean_id}/%")
        ).fetchone()
        if row:
            existing_comic = dict(row)
            first_ch = conn.execute(
                "SELECT id FROM chapters WHERE comic_id = ? ORDER BY chapter_number ASC LIMIT 1",
                (existing_comic["id"],)
            ).fetchone()
            existing_comic["first_chapter_id"] = first_ch["id"] if first_ch else None
    finally:
        conn.close()

    # 2. Lấy thông tin chi tiết từ NHentai
    info = fetch_nhentai_gallery(clean_id)

    return {
        "id": clean_id,
        "title": info["title"],
        "author": info["author"],
        "authors": info.get("authors") or [info["author"]],
        "genres": info["genres"],
        "num_pages": info["num_pages"],
        "media_id": info["media_id"],
        "cover_url": info["cover_url"],
        "is_already_added": existing_comic is not None,
        "existing_comic_id": existing_comic["id"] if existing_comic else None,
        "first_chapter_id": existing_comic.get("first_chapter_id") if existing_comic else None,
        "local_cover_filename": existing_comic["cover_filename"] if existing_comic else None,
    }


async def create_comic_by_id(gallery_id: int):
    """Tạo truyện mới chỉ bằng NHentai ID: tự động lấy thông tin, tải bìa, tạo Chapter 1."""
    clean_id = int(gallery_id)

    # Kiểm tra trùng
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM comics WHERE gallery_id = ? OR source_url LIKE ?",
            (str(clean_id), f"%/{clean_id}/%")
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Truyện với ID {clean_id} đã tồn tại trong thư viện (ID: {existing['id']})!"
            )
    finally:
        conn.close()

    # Lấy thông tin từ NHentai
    info = fetch_nhentai_gallery(clean_id)
    title = info["title"]
    author = info["author"]
    authors_list = info.get("authors") or ([a.strip() for a in author.split(",") if a.strip()] if author else ["Unknown"])
    genres = info["genres"]
    num_pages = info["num_pages"]
    base_url = info["base_url"]
    ext = info["ext"]
    source_url = f"https://nhentai.net/g/{clean_id}/"
    cover_filename = f"{clean_id}.{ext}"

    # Lưu vào DB
    conn = get_db()
    try:
        genre_ids = _find_or_create_genres(conn, genres)
        author_ids = _find_or_create_authors(conn, authors_list)

        cur = conn.execute(
            "INSERT INTO comics (title, author, cover_filename, source_url, gallery_id) VALUES (?, ?, ?, ?, ?)",
            (title, author, cover_filename, source_url, str(clean_id))
        )
        new_id = cur.lastrowid

        for g_id in genre_ids:
            conn.execute("INSERT OR IGNORE INTO comic_genres (comic_id, genre_id) VALUES (?, ?)", (new_id, g_id))

        for a_id in author_ids:
            conn.execute("INSERT OR IGNORE INTO comic_authors (comic_id, author_id) VALUES (?, ?)", (new_id, a_id))

        # Tạo Chapter 1
        conn.execute(
            "INSERT INTO chapters (comic_id, chapter_number, title, base_url, start_page, end_page) VALUES (?, ?, ?, ?, ?, ?)",
            (new_id, 1.0, "Chương 1", base_url, 1, num_pages)
        )
        conn.commit()
    finally:
        conn.close()

    # Tải ảnh bìa
    try:
        await download_cover(base_url, new_id)
    except Exception as e:
        print(f"[Warning] Failed to download cover for comic {new_id}: {e}")

    # Tự động sao lưu
    trigger_auto_backup()

    return get_comic_detail(new_id)


def delete_comic(comic_id: int) -> bool:
    """Xóa truyện và file ảnh bìa."""
    conn = get_db()
    try:
        row = conn.execute("SELECT cover_filename FROM comics WHERE id = ?", (comic_id,)).fetchone()
        if not row:
            return False
        cover_filename = row["cover_filename"]

        conn.execute("DELETE FROM comics WHERE id = ?", (comic_id,))
        # Dọn dẹp thể loại và tác giả không còn truyện nào
        conn.execute("DELETE FROM genres WHERE id NOT IN (SELECT DISTINCT genre_id FROM comic_genres)")
        conn.execute("DELETE FROM authors WHERE id NOT IN (SELECT DISTINCT author_id FROM comic_authors)")
        conn.commit()
    finally:
        conn.close()

    # Xóa file ảnh bìa
    if cover_filename and cover_filename.lower() not in ["rem.jpg", "background.jpg"]:
        cover_path = COVER_DIR / cover_filename
        if cover_path.exists():
            try:
                cover_path.unlink()
            except Exception as e:
                print(f"[Warning] Error unlinking cover: {e}")

    # Tự động sao lưu
    trigger_auto_backup()

    return True


# ==================== CHAPTERS ====================

def get_chapter_by_id(chapter_id: int):
    """Lấy thông tin chapter theo ID."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if not row:
            return None
        return _chapter_with_total(dict(row))
    finally:
        conn.close()


def create_chapter_by_id(comic_id: int, gallery_id: int, chapter_number: float = None, title: str = None):
    """Tạo chapter mới bằng NHentai ID."""
    conn = get_db()
    try:
        check = conn.execute("SELECT id FROM comics WHERE id = ?", (comic_id,)).fetchone()
        if not check:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy bộ truyện với ID: {comic_id}")
    finally:
        conn.close()

    info = fetch_nhentai_gallery(int(gallery_id))
    num_pages = info["num_pages"]
    base_url = info["base_url"]

    conn = get_db()
    try:
        if chapter_number is None:
            max_row = conn.execute("SELECT MAX(chapter_number) as max_num FROM chapters WHERE comic_id = ?", (comic_id,)).fetchone()
            if max_row and max_row["max_num"] is not None:
                chapter_number = float(max_row["max_num"]) + 1.0
            else:
                chapter_number = 1.0

        if not title:
            title = f"Chương {int(chapter_number) if chapter_number == int(chapter_number) else chapter_number}"

        try:
            cur = conn.execute(
                "INSERT INTO chapters (comic_id, chapter_number, title, base_url, start_page, end_page) VALUES (?, ?, ?, ?, ?, ?)",
                (comic_id, float(chapter_number), title, base_url, 1, num_pages)
            )
            new_id = cur.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail=f"Chương số {chapter_number} đã tồn tại trong bộ truyện này!")

        row = conn.execute("SELECT * FROM chapters WHERE id = ?", (new_id,)).fetchone()
        ch = dict(row)
    finally:
        conn.close()

    # Tự động sao lưu
    trigger_auto_backup()

    ch["total_pages"] = num_pages
    return ch


def create_chapter_from_comic(comic_id: int, data):
    """Tạo chapter mới tách từ chính bộ truyện hiện tại (kế thừa base_url đã có)."""
    start_page = int(data.start_page or 1)
    end_page = int(data.end_page or start_page)
    if start_page < 1:
        raise HTTPException(status_code=400, detail="Trang bắt đầu phải lớn hơn hoặc bằng 1!")
    if end_page < start_page:
        raise HTTPException(status_code=400, detail="Trang kết thúc phải lớn hơn hoặc bằng trang bắt đầu!")

    conn = get_db()
    try:
        check = conn.execute("SELECT id FROM comics WHERE id = ?", (comic_id,)).fetchone()
        if not check:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy bộ truyện với ID: {comic_id}")

        ch_row = conn.execute(
            "SELECT base_url FROM chapters WHERE comic_id = ? AND base_url IS NOT NULL AND base_url != '' ORDER BY id ASC LIMIT 1",
            (comic_id,)
        ).fetchone()

        if not ch_row:
            raise HTTPException(status_code=400, detail="Bộ truyện này chưa có chapter nào để kế thừa đường dẫn ảnh!")

        base_url = ch_row["base_url"]
        chapter_number = float(data.chapter_number)
        title = data.title.strip() if data.title and data.title.strip() else f"Chương {int(chapter_number) if chapter_number == int(chapter_number) else chapter_number}"

        try:
            cur = conn.execute(
                "INSERT INTO chapters (comic_id, chapter_number, title, base_url, start_page, end_page) VALUES (?, ?, ?, ?, ?, ?)",
                (comic_id, chapter_number, title, base_url, start_page, end_page)
            )
            new_id = cur.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail=f"Chương số {chapter_number} đã tồn tại trong bộ truyện này!")

        row = conn.execute("SELECT * FROM chapters WHERE id = ?", (new_id,)).fetchone()
        ch = _chapter_with_total(dict(row))
    finally:
        conn.close()

    # Tự động sao lưu
    trigger_auto_backup()

    return ch


def update_chapter(chapter_id: int, chapter_data):
    """Cập nhật thông tin chapter."""
    update_dict = {k: v for k, v in chapter_data.model_dump().items() if v is not None}
    conn = get_db()
    try:
        if update_dict:
            clauses = [f"{k} = ?" for k in update_dict]
            values = list(update_dict.values()) + [chapter_id]
            try:
                conn.execute(f"UPDATE chapters SET {', '.join(clauses)} WHERE id = ?", values)
                conn.commit()
            except sqlite3.IntegrityError:
                raise HTTPException(status_code=400, detail="Số thứ tự chapter này đã bị trùng trong bộ truyện!")

        row = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if not row:
            return None
        res = _chapter_with_total(dict(row))
    finally:
        conn.close()

    # Tự động sao lưu
    trigger_auto_backup()

    return res


def delete_chapter(chapter_id: int):
    """Xóa chapter."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
        conn.commit()
    finally:
        conn.close()

    # Tự động sao lưu
    trigger_auto_backup()


def generate_pages(chapter_id: int):
    """Sinh danh sách URL ảnh từ start_page đến end_page."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if not row:
            return []
        chapter = dict(row)
    finally:
        conn.close()

    base_url = chapter.get("base_url", "")
    start_page = int(chapter.get("start_page") or 1)
    end_page = int(chapter.get("end_page") or start_page)
    if end_page < start_page:
        end_page = start_page
    total = end_page - start_page + 1

    match = re.search(r'/(\d+)([^/]*\.\w+)$', base_url)
    if not match:
        return [base_url] * total

    prefix = base_url[:match.start(1)]
    suffix = match.group(2)

    # Loại bỏ 't' trong đuôi file thumbnail
    clean_suffix = re.sub(r'^t\.', '.', suffix, flags=re.IGNORECASE)
    # Chuyển domain thumbnail sang domain ảnh gốc
    clean_prefix = re.sub(r'://t(\d*)\.nhentai\.net/', r'://i\1.nhentai.net/', prefix)

    return [f"{clean_prefix}{i}{clean_suffix}" for i in range(start_page, end_page + 1)]


# ==================== GENRES ====================

def get_all_genres():
    """Lấy danh sách thể loại có truyện kèm comic_count."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT g.id, g.name, COUNT(cg.comic_id) as comic_count
            FROM genres g
            JOIN comic_genres cg ON g.id = cg.genre_id
            GROUP BY g.id, g.name
            HAVING comic_count > 0
            ORDER BY g.name COLLATE NOCASE ASC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_comics_by_genre_id(genre_id: int):
    """Lấy danh sách truyện theo thể loại."""
    conn = get_db()
    try:
        cg_rows = conn.execute("SELECT comic_id FROM comic_genres WHERE genre_id = ?", (genre_id,)).fetchall()
        comic_ids = [r["comic_id"] for r in cg_rows]
        if not comic_ids:
            return []

        placeholders = ",".join("?" * len(comic_ids))
        rows = conn.execute(
            f"SELECT * FROM comics WHERE id IN ({placeholders}) ORDER BY id ASC",
            comic_ids
        ).fetchall()
        comics = [dict(r) for r in rows]
        _attach_genres(conn, comics)
        _attach_authors(conn, comics)
        return comics
    finally:
        conn.close()


# ==================== AUTHORS ====================

def get_all_authors():
    """Lấy danh sách tác giả kèm số lượng truyện."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT a.name, COUNT(ca.comic_id) as comic_count
            FROM authors a
            JOIN comic_authors ca ON a.id = ca.author_id
            GROUP BY a.id, a.name
            HAVING comic_count > 0
            ORDER BY a.name COLLATE NOCASE ASC
        """).fetchall()
        if not rows:
            rows = conn.execute(
                "SELECT author as name, COUNT(*) as comic_count FROM comics WHERE author IS NOT NULL AND TRIM(author) != '' GROUP BY author ORDER BY author ASC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_comics_by_author(author_name: str):
    """Lấy danh sách truyện của tác giả (hỗ trợ cả solo và đồng tác giả)."""
    conn = get_db()
    try:
        clean_author = author_name.strip()
        rows = conn.execute("""
            SELECT DISTINCT c.id, c.title, c.author, c.cover_filename, c.source_url, c.gallery_id
            FROM comics c
            JOIN comic_authors ca ON c.id = ca.comic_id
            JOIN authors a ON ca.author_id = a.id
            WHERE a.name = ? COLLATE NOCASE
            ORDER BY c.id ASC
        """, (clean_author,)).fetchall()
        if not rows:
            rows = conn.execute(
                "SELECT id, title, author, cover_filename, source_url, gallery_id FROM comics WHERE author LIKE ? ORDER BY id ASC",
                (f"%{clean_author}%",)
            ).fetchall()
        comics = [dict(r) for r in rows]
        _attach_genres(conn, comics)
        _attach_authors(conn, comics)
        return comics
    finally:
        conn.close()


# ==================== SEARCH ====================

def search_comics(q: str = None, genre: str = None, author: str = None):
    """Tìm kiếm nâng cao kết hợp tên, tác giả, thể loại."""
    conn = get_db()
    try:
        where = []
        params = []

        if q:
            clean_q = q.strip()
            where.append("(c.title LIKE ? OR c.cover_filename LIKE ? OR c.source_url LIKE ? OR c.gallery_id LIKE ?)")
            p = f"%{clean_q}%"
            params.extend([p, p, p, p])

        if author:
            clean_author = author.strip()
            where.append("""
                (c.id IN (
                    SELECT ca.comic_id FROM comic_authors ca
                    JOIN authors a ON ca.author_id = a.id
                    WHERE a.name LIKE ?
                ) OR c.author LIKE ?)
            """)
            p_author = f"%{clean_author}%"
            params.extend([p_author, p_author])

        sql = "SELECT DISTINCT c.id, c.title, c.author, c.cover_filename, c.source_url, c.gallery_id FROM comics c"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.id ASC"

        rows = conn.execute(sql, params).fetchall()
        comics = [dict(r) for r in rows]
        if not comics:
            return []

        _attach_genres(conn, comics)
        _attach_authors(conn, comics)

        if genre:
            if isinstance(genre, list):
                genre_list = [g.strip().lower() for g in genre if g and g.strip()]
            else:
                genre_list = [g.strip().lower() for g in str(genre).split(",") if g.strip()]
            if genre_list:
                comics = [
                    c for c in comics
                    if all(
                        any(g == cg.lower() for cg in c.get("genres", []))
                        for g in genre_list
                    )
                ]

        return comics
    finally:
        conn.close()


# ==================== IMAGES (NỘI BỘ) ====================

def get_nhentai_image_proxy_service(url: str) -> tuple[bytes, str]:
    """Tải ảnh proxy từ NHentai trực tiếp vào bộ nhớ RAM (0 byte ổ đĩa)."""
    return get_nhentai_image_proxy_data(url)


async def download_cover(url: str, comic_id: int):
    """Tải ảnh bìa từ URL về frontend/assets/ và cập nhật DB (bỏ qua chặn ISP)."""
    COVER_DIR.mkdir(parents=True, exist_ok=True)

    # Nếu URL là proxy nội bộ, trích xuất URL gốc
    clean_url = url
    if "image-proxy" in url:
        parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "url" in parsed_q:
            clean_url = parsed_q["url"][0]

    parts = [p for p in clean_url.split("/") if p]
    gallery_id = parts[-2] if len(parts) >= 2 else str(comic_id)

    try:
        data, media_type = get_nhentai_image_proxy_data(clean_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể tải ảnh bìa: {e}")

    actual_ext = "webp" if "webp" in media_type else ("png" if "png" in media_type else "jpg")
    filename = f"{gallery_id}.{actual_ext}"
    filepath = COVER_DIR / filename
    filepath.write_bytes(data)

    conn = get_db()
    try:
        conn.execute("UPDATE comics SET cover_filename = ? WHERE id = ?", (filename, comic_id))
        conn.commit()
    finally:
        conn.close()

    return {"message": "Cover downloaded", "filename": filename}


# ==================== NHENTAI EXPLORE & ONLINE READER ====================

def get_nhentai_explore_service(page: int = 1, sort: str = "date", q: str = None) -> dict:
    """Lấy danh sách truyện khám phá từ NHentai và đối chiếu với database SQLite."""
    data = fetch_nhentai_explore(page=page, sort=sort, query=q)

    # Lấy danh sách ID đã lưu trong SQLite
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, gallery_id FROM comics WHERE gallery_id IS NOT NULL").fetchall()
        saved_map = {str(r["gallery_id"]): r["id"] for r in rows if r["gallery_id"]}
    finally:
        conn.close()

    for item in data.get("result", []):
        str_id = str(item.get("id"))
        item["is_already_added"] = str_id in saved_map
        item["existing_comic_id"] = saved_map.get(str_id)

    return data


def get_nhentai_online_gallery_service(gallery_id: int) -> dict:
    """Lấy dữ liệu truyện để đọc online trực tiếp không cần lưu vào máy."""
    data = fetch_nhentai_online_pages(gallery_id)

    conn = get_db()
    try:
        row = conn.execute("SELECT id FROM comics WHERE gallery_id = ?", (str(gallery_id),)).fetchone()
        data["is_already_added"] = row is not None
        data["existing_comic_id"] = row["id"] if row else None
    finally:
        conn.close()

    return data

"""
Chuyên lo kết nối CSDL và các hàm Thêm / Đọc / Sửa / Xóa (CRUD - create, read, update, delete)
- Tương tác với supabase để:
	- Lấy data từ supabase: read
	- Thêm data vào supabase: Add
	- Sửa data trong supabase: update
	- Xóa data trong supabase: remove

- Get data from supabase
	- Get 1 comic
	- Get comics
	- Get 1 chapter
	- Get folder

- Add data to supabase
	- Add 1 comic
	- Add 1 chapter
	- Add 1 folder

- Remove data
	- Remove 1 comic
	- Remove 1 chapter

- Update data
	- Update 1 chapter


note: sau này sẽ thêm:
- get_all_genres()
"""

import math
from database import get_connection
from nhentai import fetch_comic_from_nhentai

EXT_MAP = {"j": "jpg", "p": "png", "w": "webp", "g": "gif"}

def build_page_url(media_id, page_num, page_exts):
    """Sinh link ảnh chính xác theo đuôi từng trang từ chuỗi page_exts."""
    ext = "jpg"
    if page_exts and 1 <= page_num <= len(page_exts):
        ext = EXT_MAP.get(page_exts[page_num - 1], "jpg")
    return f"https://i3.nhentai.net/galleries/{media_id}/{page_num}.{ext}"


def add_comic_by_gallery_id(gallery_id, folder_id = 1):
    """
    Thêm một bộ truyện mới vào thư viện bằng Gallery ID của NHentai.
    Quy trình:
    1. Cào dữ liệu từ NHentai.
    2. Lưu thông tin vào bảng 'comics'.
    3. Tự động tạo Tập 1 (toàn bộ các trang) vào bảng 'chapters'.
    4. Lưu tags vào bảng 'tags' và liên kết trong 'comic_tags'.
    """
    # Bước 1: Lấy dữ liệu truyện từ NHentai
    comic_data = fetch_comic_from_nhentai(gallery_id)

    comic_id = comic_data["id"]
    media_id = comic_data["media_id"]
    title = comic_data["title"]
    artists = comic_data["artists"]
    artist_str = ", ".join(artists) if artists else "Unknown"
    cover_url = comic_data["cover_url"]
    language = comic_data["language"]
    category = comic_data["category"]
    num_pages = comic_data["num_pages"]
    page_exts = comic_data.get("page_exts", "")
    raw_tags = comic_data.get("tags", [])
    genres_list = []

    # Kết nối CSDL và thực thi Transaction
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 2: Lưu vào bảng comics
            cur.execute("""
                INSERT INTO comics (id, folder_id, media_id, title, artist, language, category, cover_url, num_pages, page_exts)
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
            """, (comic_id, folder_id, media_id, title, artist_str, language, category, cover_url, num_pages, page_exts))

            # Bước 3: Tạo Chapter 1 mặc định (gồm toàn bộ các trang từ 1 đến num_pages)
            # Xóa chapter cũ nếu đã tồn tại để tránh trùng lặp
            cur.execute("DELETE FROM chapters WHERE comic_id = %s;", (comic_id,))

            cur.execute("""
                INSERT INTO chapters (comic_id, chapter_number, title, media_id, start_page, end_page, page_exts)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (comic_id, 1, "Toàn bộ", media_id, 1, num_pages, page_exts))

            # Bước 4: Lưu tags vào bảng 'tags' và tạo liên kết trong 'comic_tags'
            for tag in raw_tags:
                t_id = tag.get("id")
                t_type = tag.get("type")
                t_name = tag.get("name")
                t_slug = tag.get("slug")

                if not t_id or not t_name:
                    continue

                # 1. Nếu là tác giả -> Lưu vào artists và comic_artists
                if t_type == "artist":
                    cur.execute("""
                        INSERT INTO artists (id, name, slug)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """, (t_id, t_name, t_slug))

                    cur.execute("""
                        INSERT INTO comic_artists (comic_id, artist_id)
                        VALUES (%s, %s)
                        ON CONFLICT (comic_id, artist_id) DO NOTHING;
                    """, (comic_id, t_id))

                # 2. Nếu là thể loại -> Lưu vào genres và comic_genres
                elif t_type == "tag":
                    cur.execute("""
                        INSERT INTO genres (id, name, slug)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """, (t_id, t_name, t_slug))
                    cur.execute("""
                        INSERT INTO comic_genres (comic_id, genre_id)
                        VALUES (%s, %s)
                        ON CONFLICT (comic_id, genre_id) DO NOTHING;
                    """, (comic_id, t_id))

                    genres_list.append({
                        "id": t_id,
                        "type": t_type,
                        "name": t_name,
                        "slug": t_slug
                    })

    print(f"[INFO] Da them thanh cong truyen: {title} (ID: {comic_id})")
    return {
        "id": comic_id,
        "title": title,
        "folder_id": folder_id,
        "language": language,
        "category": category,
        "artists": artists,
        "genres": genres_list,
        "num_pages": num_pages
    }

# ==================== CÁC HÀM ĐỌC & KIỂM TRA DỮ LIỆU (READ) ====================
def get_all_comics(folder_id = None, artist_id = None, page = 1, limit = 12):
    """
    Lấy danh sách truyện có phân trang (mặc định 12 bộ truyện mới nhất mỗi trang).
    Hỗ trợ lọc theo Thư mục (folder_id) và Tác giả (artist_id).
    """
    if page < 1:
        page = 1
    if limit < 1:
        limit = 12

    with get_connection() as conn:
        with conn.cursor() as cur:
            base_from = """
                FROM comics c
                LEFT JOIN folders f ON c.folder_id = f.id
            """
            conditions = []
            params = []

            # Hỗ trợ lọc theo Thư mục
            if folder_id:
                conditions.append("c.folder_id = %s")
                params.append(folder_id)

            # Hỗ trợ lọc theo Tác giả (dùng bảng nối comic_artists)
            if artist_id:
                base_from += " JOIN comic_artists ca ON c.id = ca.comic_id "
                conditions.append("ca.artist_id = %s")
                params.append(artist_id)

            where_clause = ""
            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)

            # 1. Đếm tổng số bộ truyện thỏa điều kiện lọc
            count_query = f"SELECT COUNT(DISTINCT c.id) AS total {base_from} {where_clause};"
            cur.execute(count_query, params)
            total_comics = cur.fetchone()["total"]
            total_pages = math.ceil(total_comics / limit) if total_comics > 0 else 1

            # Tự động lùi về trang cuối cùng nếu trang hiện tại vừa bị xóa hết truyện
            if page > total_pages:
                page = total_pages
            offset = (page - 1) * limit

            # 2. Lấy đúng 12 bộ truyện mới nhất của trang hiện tại
            data_query = f"""
                SELECT
                    c.id,
                    c.title,
                    c.artist AS author,
                    c.language,
                    c.category,
                    c.cover_url,
                    c.num_pages,
                    c.folder_id,
                    f.name AS folder_name
                {base_from}
                {where_clause}
                ORDER BY c.created_at DESC
                LIMIT %s OFFSET %s;
            """
            cur.execute(data_query, params + [limit, offset])
            items = cur.fetchall()

            return {
                "items": items,
                "total_comics": total_comics,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            }


def check_comic_before_add(gallery_id):
    """
    Kiểm tra truyện khi người dùng bấm nút 'Tìm' ở Trang chủ:
    1. Tìm trong Supabase theo ID trước. Nếu có -> trả về bộ truyện đó.
    2. Nếu chưa có ID trong Supabase -> lấy thông tin từ NHentai, sau đó so sánh
       title (title_pretty) xem có trùng với bộ truyện nào trong Supabase không:
       - Nếu trùng tên -> trả về bộ truyện bị trùng tên trong Supabase.
       - Nếu không trùng -> báo là truyện mới để người dùng bấm 'Thêm vào thư viện'.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 1: Kiểm tra trùng ID trong Supabase
            cur.execute("""
                SELECT
                    c.id,
                    c.title,
                    c.artist AS author,
                    c.language,
                    c.category,
                    c.cover_url,
                    c.num_pages,
                    c.folder_id,
                    f.name AS folder_name
                FROM comics c
                LEFT JOIN folders f ON c.folder_id = f.id
                WHERE c.id = %s;
            """, (gallery_id,))
            existing_by_id = cur.fetchone()

            if existing_by_id:
                return {
                    "status": "exists_id",
                    "message": f"Truyện ID {gallery_id} đã có sẵn trong thư viện!",
                    "comic": existing_by_id,
                    "nhentai_data": None
                }

            # Bước 2: Chưa có ID trong Supabase -> Tìm trên NHentai
            nhentai_data = fetch_comic_from_nhentai(gallery_id)
            title_pretty = nhentai_data["title"].strip()

            # Bước 3: Kiểm tra xem title_pretty có trùng với bộ truyện nào trong Supabase không
            cur.execute("""
                SELECT
                    c.id,
                    c.title,
                    c.artist AS author,
                    c.language,
                    c.category,
                    c.cover_url,
                    c.num_pages,
                    c.folder_id,
                    f.name AS folder_name
                FROM comics c
                LEFT JOIN folders f ON c.folder_id = f.id
                WHERE LOWER(TRIM(c.title)) = LOWER(TRIM(%s))
                LIMIT 1;
            """, (title_pretty,))
            existing_by_title = cur.fetchone()

            if existing_by_title:
                return {
                    "status": "exists_title",
                    "message": (
                        f"Phát hiện trùng tên '{title_pretty}' với bộ truyện đã có trong thư viện "
                        f"(ID gốc: {existing_by_title['id']}). Nếu ID {gallery_id} là phần tiếp theo, "
                        f"hãy bấm vào 'Chi tiết' của bộ truyện bên dưới để thêm làm Chapter mới!"
                    ),
                    "comic": existing_by_title,
                    "nhentai_data": nhentai_data
                }

            # Bước 4: Hoàn toàn chưa có trong thư viện
            artists_str = ", ".join(nhentai_data.get("artists", [])) or "Unknown"
            return {
                "status": "new",
                "message": (
                    f"Truyện mới hợp lệ: '{title_pretty}' — Tác giả: {artists_str} "
                    f"({nhentai_data['num_pages']} trang). Hãy chọn thư mục và bấm 'Thêm vào thư viện'!"
                ),
                "comic": None,
                "nhentai_data": nhentai_data
            }

def get_comic_detail(comic_id):
    """
    Lấy thông tin chi tiết của 1 bộ truyện:
    - Thông tin truyện (tiêu đề, ảnh bìa, ngôn ngữ, thể loại chính...)
    - Danh sách các thể loại chi tiết (genres)
    - Danh sách tác giả (artists)
    - Danh sách các tập/hồi (chapters) để người dùng bấm vào đọc
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Lấy thông tin cơ bản của truyện kèm tên thư mục
            cur.execute("""
                SELECT c.*, f.name AS folder_name
                FROM comics c
                LEFT JOIN folders f ON c.folder_id = f.id
                WHERE c.id = %s;
            """, (comic_id,))
            comic = cur.fetchone()

            # Nếu không tìm thấy truyện trong CSDL
            if not comic:
                return None

            # 2. Lấy danh sách thể loại từ bảng 'genres' (qua bảng nối 'comic_genres')
            cur.execute("""
                SELECT g.id, g.name, g.slug
                FROM genres g
                JOIN comic_genres cg ON g.id = cg.genre_id
                WHERE cg.comic_id = %s
                ORDER BY g.name ASC;
            """, (comic_id,))
            genres_rows = cur.fetchall()

            # 3. Lấy danh sách tác giả từ bảng 'artists' (qua bảng nối 'comic_artists')
            cur.execute("""
                SELECT a.id, a.name, a.slug
                FROM artists a
                JOIN comic_artists ca ON a.id = ca.artist_id
                WHERE ca.comic_id = %s
                ORDER BY a.name ASC;
            """, (comic_id,))
            artists_rows = cur.fetchall()

            # Chuẩn hóa dữ liệu trả về cho Frontend dễ đọc
            comic["genres"] = [g["name"] for g in genres_rows]
            comic["genres_detail"] = genres_rows  # Lưu đầy đủ id, name, slug (tiện để làm link bấm vào thể loại sau này)
            comic["authors"] = [a["name"] for a in artists_rows]
            # Ưu tiên lấy từ cột artist đã có sẵn trong bảng comics, nếu chưa có thì lấy từ danh sách tác giả
            comic["author"] = comic.get("artist") or (", ".join(comic["authors"]) if comic["authors"] else "Unknown")

            # 4. Lấy danh sách chapters của truyện này
            cur.execute("""
                SELECT id, chapter_number, title, media_id, start_page, end_page
                FROM chapters
                WHERE comic_id = %s
                ORDER BY chapter_number ASC;
            """, (comic_id,))
            comic["chapters"] = cur.fetchall()

             # 5. Tạo danh sách link ảnh xem trước chính xác theo đuôi từng trang
            c_exts = comic.get("page_exts") or ""
            comic["pages"] = [
                {
                    "page_number": p,
                    "url": build_page_url(comic["media_id"], p, c_exts)
                }
                for p in range(1, comic["num_pages"] + 1)
            ]

            return comic

def get_chapter_pages(chapter_id):
    """
    Lấy danh sách link ảnh trực tiếp để đọc online một chapter.
    Tự động sinh link từ start_page đến end_page với đúng đuôi ảnh từ page_exts.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ch.media_id, ch.start_page, ch.end_page, ch.page_exts, c.page_exts AS comic_page_exts
                FROM chapters ch
                LEFT JOIN comics c ON ch.comic_id = c.id
                WHERE ch.id = %s;
            """, (chapter_id,))
            ch = cur.fetchone()
            if not ch:
                return []
            media_id = ch["media_id"]
            start_p = ch["start_page"]
            end_p = ch["end_page"]
            page_exts = ch.get("page_exts") or ch.get("comic_page_exts") or ""
            pages = []
            for page_num in range(start_p, end_p + 1):
                pages.append({
                    "page_number": page_num,
                    "url": build_page_url(media_id, page_num, page_exts)
                })
            return pages

# ==================== CÁC HÀM XỬ LÝ CHAPTER & XÓA ====================

def split_comic_into_chapters(comic_id, chapters_data):
    """
    Chia chapter theo đúng cấu hình thủ công mà người dùng nhập vào.
    chapters_data là danh sách do người dùng gửi lên, ví dụ:
    [
        {"title": "Hồi 1: Khởi đầu", "start_page": 1, "end_page": 50},
        {"title": "Hồi 2: Biến cố",  "start_page": 51, "end_page": 130},
        {"title": "Hồi 3: Kết thúc", "start_page": 131, "end_page": 236}
    ]
    """
    if not chapters_data:
        raise ValueError("Danh sách chapter không được để trống!")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Lấy thông tin truyện để kiểm tra giới hạn số trang
            cur.execute("SELECT id, media_id, num_pages, page_exts FROM comics WHERE id = %s;", (comic_id,))

            comic = cur.fetchone()
            if not comic:
                raise ValueError(f"Không tìm thấy bộ truyện với ID: {comic_id}")

            media_id = comic["media_id"]
            num_pages = comic["num_pages"]
            page_exts = comic.get("page_exts") or ""

            # 2. Kiểm tra tính hợp lệ của từng chapter người dùng nhập
            for index, item in enumerate(chapters_data, start=1):
                start_p = item.get("start_page")
                end_p = item.get("end_page")
                title = item.get("title")

                if not title or not title.strip():
                    raise ValueError(f"Chapter thứ {index} chưa nhập tên!")
                if start_p is None or end_p is None:
                    raise ValueError(f"Chapter '{title}' thiếu start_page hoặc end_page!")
                if start_p < 1:
                    raise ValueError(f"Chapter '{title}': trang bắt đầu ({start_p}) không được nhỏ hơn 1!")
                if end_p > num_pages:
                    raise ValueError(f"Chapter '{title}': trang kết thúc ({end_p}) vượt quá tổng số trang của truyện ({num_pages})!")
                if start_p > end_p:
                    raise ValueError(f"Chapter '{title}': trang bắt đầu ({start_p}) không được lớn hơn trang kết thúc ({end_p})!")

            # 3. Xóa các chapter cũ của truyện này để áp dụng danh sách mới
            cur.execute("DELETE FROM chapters WHERE comic_id = %s AND media_id = %s;", (comic_id, str(media_id)))

            # 4. Lưu từng chapter do người dùng tự đặt vào CSDL
            created_chapters = []
            for index, item in enumerate(chapters_data, start=1):
                cur.execute("""
                    INSERT INTO chapters (comic_id, chapter_number, title, media_id, start_page, end_page, page_exts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, chapter_number, title, start_page, end_page;
                """, (
                    comic_id,
                    item.get("chapter_number", index),
                    item["title"].strip(),
                    media_id,
                    item["start_page"],
                    item["end_page"],
                    page_exts
                ))
                created_chapters.append(cur.fetchone())

            # 5. Đẩy số thứ tự của các chapter từ ID khác (nếu có) nối tiếp ngay sau các chapter vừa chia
            cur.execute("""
                SELECT id FROM chapters
                WHERE comic_id = %s AND media_id != %s
                ORDER BY chapter_number ASC, id ASC;
            """, (comic_id, str(media_id)))
            external_chapters = cur.fetchall()
            next_num = len(created_chapters) + 1
            for ext_ch in external_chapters:
                cur.execute("""
                    UPDATE chapters SET chapter_number = %s WHERE id = %s;
                """, (next_num, ext_ch["id"]))
                next_num += 1

    print(f"[INFO] Da chia thu cong truyen {comic_id} thanh {len(created_chapters)} chapters theo y nguoi dung.")
    return created_chapters


def add_chapter_from_gallery_id(comic_id, gallery_id, chapter_number = None, title = None):
    """
    Thêm một chapter mới vào bộ truyện có sẵn từ một Gallery ID NHentai khác.
    Phục vụ cho các bộ truyện nhiều phần (Part 1, Part 2...).
    """
    # 1. Cào dữ liệu của tập mới từ NHentai
    new_gallery = fetch_comic_from_nhentai(gallery_id)
    new_media_id = str(new_gallery["media_id"])
    new_num_pages = new_gallery["num_pages"]
    new_page_exts = new_gallery.get("page_exts", "")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 2. Kiểm tra bộ truyện cha có tồn tại không
            cur.execute("SELECT id FROM comics WHERE id = %s;", (comic_id,))
            if not cur.fetchone():
                raise ValueError(f"Bộ truyện cha ID {comic_id} không tồn tại!")

            # 3. Tự động tính số thứ tự tập tiếp theo nếu không truyền vào
            if chapter_number is None:
                cur.execute("""
                    SELECT COALESCE(MAX(chapter_number), 0) + 1 AS next_num
                    FROM chapters
                    WHERE comic_id = %s;
                """, (comic_id,))
                chapter_number = cur.fetchone()["next_num"]

            # 4. Tên chapter mặc định nếu không truyền
            if not title:
                title = f"Tập {int(chapter_number) if float(chapter_number).is_integer() else chapter_number}"

            # 5. Lưu chapter mới vào CSDL
            cur.execute("""
                INSERT INTO chapters (comic_id, chapter_number, title, media_id, start_page, end_page, page_exts)
                VALUES (%s, %s, %s, %s, 1, %s, %s)
                RETURNING id, comic_id, chapter_number, title, media_id, start_page, end_page;
            """, (comic_id, chapter_number, title, new_media_id, new_num_pages, new_page_exts))

            created_chapter = cur.fetchone()

    print(f"[INFO] Da them {title} (ID NHentai: {gallery_id}) vao bo truyen {comic_id}.")
    return created_chapter


def delete_comic(comic_id):
    """
    Xóa 1 bộ truyện khỏi thư viện.
    Nhờ 'ON DELETE CASCADE', toàn bộ chapters và liên kết tags sẽ tự động bị xóa theo.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM comics WHERE id = %s;", (comic_id,))
            deleted = cur.rowcount > 0

    if deleted:
        print(f"[INFO] Da xoa bo truyen ID: {comic_id}")
    return deleted

def get_all_folders():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM folders ORDER BY id ASC;")
            return cur.fetchall()

def create_folder(name, description = ""):
    """
    Tạo một thư mục mới để phân loại truyện.
    Nếu tên thư mục đã tồn tại thì cập nhật lại phần mô tả (description).
    """
    if not name or not name.strip():
        raise ValueError("Tên thư mục không được để trống!")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO folders (name, description)
                VALUES (%s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description
                RETURNING id, name, description;
            """, (name.strip(), description.strip()))
            new_folder = cur.fetchone()

    print(f"[INFO] Da tao thu muc: '{new_folder['name']}' (ID: {new_folder['id']})")
    return new_folder

def rename_folder(folder_id: int, new_name: str, description: str = "") -> dict:
    """
    Đổi tên một thư mục (không cho phép đổi tên thư mục Mặc định ID = 1).
    """
    if folder_id == 1:
        raise ValueError("Không thể đổi tên thư mục 'Mặc định'!")
    if not new_name or not new_name.strip():
        raise ValueError("Tên thư mục mới không được để trống!")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE folders
                SET name = %s, description = %s
                WHERE id = %s
                RETURNING id, name, description;
            """, (new_name.strip(), description.strip(), folder_id))
            updated = cur.fetchone()
            if not updated:
                raise ValueError(f"Thư mục ID {folder_id} không tồn tại!")

    print(f"[INFO] Da doi ten thu muc ID {folder_id} thanh: '{updated['name']}'")
    return updated


def delete_folder(folder_id: int) -> bool:
    """
    Xóa một thư mục (không cho phép xóa thư mục Mặc định ID = 1).
    Các truyện trong thư mục bị xóa sẽ tự động chuyển về thư mục Mặc định (ID = 1).
    """
    if folder_id == 1:
        raise ValueError("Không thể xóa thư mục 'Mặc định'!")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Chuyển các bộ truyện trong thư mục này về thư mục Mặc định (id = 1)
            cur.execute("UPDATE comics SET folder_id = 1 WHERE folder_id = %s;", (folder_id,))

            # Xóa thư mục
            cur.execute("DELETE FROM folders WHERE id = %s;", (folder_id,))
            deleted = cur.rowcount > 0
            if not deleted:
                raise ValueError(f"Thư mục ID {folder_id} không tồn tại!")

    print(f"[INFO] Da xoa thu muc ID: {folder_id}")
    return True

def update_comic_folder(comic_id, folder_id):
    """
    Chuyển một bộ truyện sang thư mục khác.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Kiểm tra thư mục đích có tồn tại không
            cur.execute("SELECT id, name FROM folders WHERE id = %s;", (folder_id,))
            folder = cur.fetchone()
            if not folder:
                raise ValueError(f"Thư mục ID {folder_id} không tồn tại!")

            # Cập nhật folder_id cho bộ truyện
            cur.execute("""
                UPDATE comics
                SET folder_id = %s
                WHERE id = %s
                RETURNING id, title, folder_id;
            """, (folder_id, comic_id))
            updated = cur.fetchone()
            if not updated:
                raise ValueError(f"Không tìm thấy truyện ID {comic_id}!")

            updated["folder_name"] = folder["name"]
            return updated

def get_all_authors():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT a.id, a.name, a.slug
                FROM artists a
                JOIN comic_artists ca ON a.id = ca.artist_id
                ORDER BY a.name ASC;
            """)
            return cur.fetchall()


def test_use_case(choice):
    TEST_COMIC_ID = 686045

    match choice:
        case 1:
            # -------------------------------------------------------------
            # 1. TEST: Thêm truyện từ NHentai vào CSDL
            # -------------------------------------------------------------
            print(f"\n--- 1. TEST: Thêm truyện ID {TEST_COMIC_ID} từ NHentai vào CSDL ---")
            try:
                new_comic = add_comic_by_gallery_id(TEST_COMIC_ID, folder_id=1)
                print(f"-> Thêm thành công: '{new_comic['title']}' (ID: {new_comic['id']}) vào folder: {new_comic['folder_id']}")
                print("Info: ")
                print(new_comic["language"])
                print(new_comic["category"])
                print(new_comic["artists"])
                print(new_comic["genres"])
                print(new_comic["num_pages"])
            except Exception as e:
                print(f"-> Gặp lỗi khi thêm truyện: {e}")

        case 2:
            # -------------------------------------------------------------
            # 2. TEST: Lấy danh sách truyện ở trang chủ
            # -------------------------------------------------------------
            print("\n--- 2. TEST: Lấy danh sách truyện ở trang chủ (get_all_comics) ---")
            comics_list = get_all_comics()
            print(f"-> Tổng số truyện trong thư viện: {len(comics_list)} bộ")
            for c in comics_list:
                print(f"   [ID: {c['id']}] {c['title']} | Tác giả: {c.get('author')} | Ngôn ngữ: {c.get('language')} | Thư mục: {c.get('folder_name')}")

        case 3:
            # -------------------------------------------------------------
            # 3. TEST: Lấy thông tin chi tiết của 1 bộ truyện
            # -------------------------------------------------------------
            print(f"\n--- 3. TEST: Lấy chi tiết bộ truyện ID {TEST_COMIC_ID} (get_comic_detail) ---")
            detail = get_comic_detail(TEST_COMIC_ID)
            if detail:
                print(f"-> Tên truyện : {detail['title']}")
                print(f"-> Tác giả    : {detail['author']}")
                print(f"-> Ngôn ngữ   : {detail['language']}")
                print(f"-> Thể loại   : {', '.join(detail['genres'])}")
                print(f"-> Số tập     : {len(detail['chapters'])} chapter")
                print(f"-> Ảnh bìa    : {detail['cover_url']}")
            else:
                print(f"-> Không tìm thấy chi tiết truyện ID {TEST_COMIC_ID}!")

        case 4:
            # -------------------------------------------------------------
            # 4. TEST: Lấy danh sách link ảnh để đọc online của Chapter 1
            # -------------------------------------------------------------
            detail = get_comic_detail(TEST_COMIC_ID)
            if detail and detail.get("chapters"):
                first_chapter_id = detail["chapters"][0]["id"]
                print(f"\n--- 4. TEST: Lấy link ảnh đọc Chapter ID {first_chapter_id} (get_chapter_pages) ---")
                pages = get_chapter_pages(first_chapter_id)
                print(f"-> Tổng số trang ảnh: {len(pages)} trang")
                if pages:
                    print(f"   + Trang đầu: {pages[0]['url']}")
                    print(f"   + Trang cuối: {pages[-1]['url']}")
        case 5:
            # -------------------------------------------------------------
            # 5. TEST: Lấy danh sách tất cả tác giả từ bảng artists
            # -------------------------------------------------------------
            print("\n--- 5. TEST: Danh sách tất cả tác giả (get_all_authors) ---")
            authors = get_all_authors()
            print(f"-> Tìm thấy {len(authors)} tác giả trong CSDL:")
            for a in authors:
                print(f"   - [ID: {a['id']}] {a['name']} (slug: {a['slug']})")

        case 6:
            # -------------------------------------------------------------
            # 6. TEST: Thử lọc truyện theo tác giả đầu tiên
            # -------------------------------------------------------------
            authors = get_all_authors()
            if authors:
                first_author_id = authors[0]["id"]
                author_name = authors[0]["name"]
                print(f"\n--- 6. TEST: Lọc truyện theo tác giả '{author_name}' (ID: {first_author_id}) ---")
                filtered_comics = get_all_comics(artist_id=first_author_id)
                print(f"-> Tìm thấy {len(filtered_comics)} truyện của tác giả '{author_name}':")
                for fc in filtered_comics:
                    print(f"   * [ID: {fc['id']}] {fc['title']}")

        
        case 7:
            # -------------------------------------------------------------
            # 7. TEST: Lấy danh sách Folder và lọc truyện theo Folder
            # -------------------------------------------------------------
            print("\n--- 7. TEST: Danh sách Thư mục & Lọc truyện theo Thư mục ---")
            folders = get_all_folders()
            print(f"-> Có {len(folders)} thư mục trong CSDL:")
            for f in folders:
                print(f"   - [ID: {f['id']}] {f['name']} ({f['description']})")

            if folders:
                target_folder_id = folders[0]["id"]
                target_folder_name = folders[0]["name"]
                print(f"\n-> Đang lọc truyện trong thư mục '{target_folder_name}' (ID: {target_folder_id}):")
                folder_comics = get_all_comics(folder_id=target_folder_id)
                print(f"-> Tìm thấy {len(folder_comics)} bộ truyện:")
                for fc in folder_comics:
                    print(f"   * [ID: {fc['id']}] {fc['title']} | Tác giả: {fc['author']}")
        case 8:
            # -------------------------------------------------------------
            # 8. TEST: Tạo thư mục mới
            # -------------------------------------------------------------
            print("\n--- 8. TEST: Tạo thư mục mới (create_folder) ---")
            folder_name = input("Nhập tên thư mục mới: ")
            folder_desc = input("Nhập mô tả thư mục: ")
            try:
                created = create_folder(name=folder_name, description=folder_desc)
                print(f"-> Tạo thành công: [ID: {created['id']}] {created['name']} - {created['description']}")
            except Exception as e:
                print(f"-> Lỗi khi tạo thư mục: {e}")

                





if __name__ == "__main__":
    import sys
    # Tránh lỗi font tiếng Việt trên terminal Windows
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    TEST_COMIC_ID = 14414

    print("=" * 60)
    print(" BẮT ĐẦU KIỂM THỬ TOÀN DIỆN CÁC HÀM TRONG SERVICES.PY")
    print("=" * 60)
    is_active = True
    while is_active:
        choice = int(input("Enter your choice: "))
        if choice == 0:
            print("\n" + "=" * 60)
            print(" HOÀN THÀNH KIỂM THỬ TẤT CẢ CÁC HÀM CỐT LÕI!")
            print("=" * 60)
            is_active = False
        test_use_case(choice)
        


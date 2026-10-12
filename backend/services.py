"""
HManga Library - Module Nghiệp Vụ & Tương Tác CSDL (Services / CRUD)
====================================================================
Chứa toàn bộ các hàm xử lý nghiệp vụ cốt lõi nối giữa API (main.py) và Supabase (database.py):

1. Tiện ích xử lý ảnh:
   - build_page_url                  : Giải mã chuỗi `page_exts` để ghép đúng link ảnh từng trang (.jpg, .png, .webp, .gif).

2. Nghiệp vụ Truyện (Comics):
   - add_comic_by_gallery_id         : Cào dữ liệu từ NHentai và lưu vào các bảng comics, chapters, artists, genres.
   - get_all_comics                  : Lấy danh sách truyện phân trang (12 bộ/trang), hỗ trợ lọc theo Thư mục & Tác giả.
   - check_comic_before_add          : Kiểm tra trùng ID hoặc trùng tên truyện (`title_pretty`) trước khi thêm.
   - get_comic_detail                : Lấy thông tin chi tiết 1 bộ truyện kèm danh sách tác giả, thể loại, chapters và trang xem trước.
   - delete_comic                    : Xóa truyện khỏi thư viện (tự động dọn dẹp dữ liệu liên quan nhờ CASCADE).
   - update_comic_folder             : Chuyển bộ truyện sang thư mục khác.

3. Nghiệp vụ Chương/Tập (Chapters):
   - get_chapter_pages               : Sinh danh sách link ảnh của 1 chapter để hiển thị trên trình đọc.
   - split_comic_into_chapters       : Chia nhỏ bộ truyện dài thành nhiều chapter theo mốc trang tùy chọn.
   - add_chapter_from_gallery_id     : Gộp thêm 1 phần mới (từ Gallery ID khác) làm chapter tiếp theo của bộ truyện hiện tại.

4. Nghiệp vụ Thư mục & Tác giả (Folders & Artists):
   - get_all_folders, create_folder, rename_folder, delete_folder
   - get_all_authors                 : Lấy danh sách các tác giả đang có truyện trong thư viện.
"""

import math
from database import get_connection
from nhentai import fetch_comic_from_nhentai


# ==================== 1. HÀM TIỆN ÍCH SINH LINK ẢNH ====================

# Bảng ánh xạ ký tự đầu trong chuỗi `page_exts` sang đuôi file ảnh thực tế
EXT_MAP = {"j": "jpg", "p": "png", "w": "webp", "g": "gif"}

def build_page_url(media_id, page_num, page_exts):
    """
    Sinh đường dẫn ảnh trên CDN NHentai cho một trang cụ thể.
    Dựa vào vị trí `page_num - 1` trong chuỗi `page_exts` để lấy đúng định dạng ảnh (.jpg, .png, .webp, .gif).
    """
    ext = "jpg"
    if page_exts and 1 <= page_num <= len(page_exts):
        ext = EXT_MAP.get(page_exts[page_num - 1], "jpg")
    return f"https://i3.nhentai.net/galleries/{media_id}/{page_num}.{ext}"


# ==================== 2. HÀM THÊM TRUYỆN MỚI VÀO THƯ VIỆN ====================

def add_comic_by_gallery_id(gallery_id, folder_id = 1):
    """
    Thêm một bộ truyện mới vào thư viện bằng Gallery ID của NHentai.
    Quy trình thực hiện trong 1 Transaction:
    1. Gọi NHentai API lấy toàn bộ thông tin truyện.
    2. Lưu thông tin tổng quan vào bảng `comics`.
    3. Tạo mặc định Chapter 1 ("Toàn bộ", từ trang 1 đến trang cuối) trong bảng `chapters`.
    4. Tách và lưu danh sách Tác giả vào `artists` / `comic_artists`, Thể loại vào `genres` / `comic_genres`.
    """
    # Bước 1: Thu thập và bóc tách dữ liệu từ NHentai
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

    # Mở kết nối CSDL và thực thi toàn bộ thao tác trong cùng 1 Transaction
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 2: Lưu (hoặc cập nhật nếu đã tồn tại ID) vào bảng `comics`
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

            # Bước 3: Khởi tạo Chapter 1 mặc định (chứa toàn bộ trang từ 1 đến num_pages)
            # Xóa chapter cũ của truyện này (nếu có) để tránh bị nhân đôi khi thêm lại
            cur.execute("DELETE FROM chapters WHERE comic_id = %s;", (comic_id,))

            cur.execute("""
                INSERT INTO chapters (comic_id, chapter_number, title, media_id, start_page, end_page, page_exts)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (comic_id, 1, "Toàn bộ", media_id, 1, num_pages, page_exts))

            # Bước 4: Lưu thông tin Tác giả (artist) và Thể loại (tag) vào các bảng chuẩn hóa
            for tag in raw_tags:
                t_id = tag.get("id")
                t_type = tag.get("type")
                t_name = tag.get("name")
                t_slug = tag.get("slug")

                if not t_id or not t_name:
                    continue

                # 4a. Nếu tag là tác giả -> Lưu vào bảng `artists` và bảng nối `comic_artists`
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

                # 4b. Nếu tag là thể loại chi tiết -> Lưu vào bảng `genres` và bảng nối `comic_genres`
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


# ==================== 3. CÁC HÀM ĐỌC & KIỂM TRA DỮ LIỆU (READ) ====================

def get_all_comics(folder_id = None, artist_id = None, page = 1, limit = 12):
    """
    Lấy danh sách truyện ở Trang chủ có phân trang (mặc định 12 bộ mới nhất mỗi trang).
    Hỗ trợ lọc kết hợp theo Thư mục (`folder_id`) và Tác giả (`artist_id`).
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

            # Điều kiện lọc 1: Lọc theo Thư mục
            if folder_id:
                conditions.append("c.folder_id = %s")
                params.append(folder_id)

            # Điều kiện lọc 2: Lọc theo Tác giả (JOIN qua bảng trung gian `comic_artists`)
            if artist_id:
                base_from += " JOIN comic_artists ca ON c.id = ca.comic_id "
                conditions.append("ca.artist_id = %s")
                params.append(artist_id)

            where_clause = ""
            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)

            # Bước 1: Đếm tổng số bộ truyện thỏa điều kiện để tính tổng số trang (total_pages)
            count_query = f"SELECT COUNT(DISTINCT c.id) AS total {base_from} {where_clause};"
            cur.execute(count_query, params)
            total_comics = cur.fetchone()["total"]
            total_pages = math.ceil(total_comics / limit) if total_comics > 0 else 1

            # Nếu trang yêu cầu vượt quá tổng số trang (ví dụ sau khi xóa bớt truyện), tự động lùi về trang cuối
            if page > total_pages:
                page = total_pages
            offset = (page - 1) * limit

            # Bước 2: Truy vấn danh sách truyện của trang hiện tại, sắp xếp theo thời gian thêm mới nhất
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
    Kiểm tra một Gallery ID khi người dùng bấm nút 'Tìm' ở Trang chủ:
    - Bước 1 (`exists_id`)   : Kiểm tra xem ID này đã có trong bảng `comics` chưa.
    - Bước 2 (`exists_title`): Nếu chưa có ID, gọi NHentai lấy `title_pretty` rồi đối chiếu xem
                               có trùng tên với bộ truyện nào đã lưu trong thư viện không (để gợi ý gộp Chapter).
    - Bước 3 (`new`)         : Nếu hoàn toàn chưa có, trả về thông tin xem trước để người dùng thêm mới.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 1: Kiểm tra trùng ID trực tiếp trong Supabase
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

            # Bước 2: Nếu chưa có ID trong CSDL -> Gọi NHentai API để lấy thông tin truyện
            nhentai_data = fetch_comic_from_nhentai(gallery_id)
            title_pretty = nhentai_data["title"].strip()

            # Bước 2.5: Kiểm tra xem media_id của truyện này đã từng được gộp làm Chapter của bộ truyện nào chưa
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
                    f.name AS folder_name,
                    ch.chapter_number
                FROM chapters ch
                JOIN comics c ON ch.comic_id = c.id
                LEFT JOIN folders f ON c.folder_id = f.id
                WHERE ch.media_id = %s
                LIMIT 1;
            """, (str(nhentai_data["media_id"]),))
            existing_by_chapter = cur.fetchone()

            if existing_by_chapter:
                return {
                    "status": "exists_chapter",
                    "message": (
                        f"Truyện ID {gallery_id} đã tồn tại trong thư viện (đang là Chapter {existing_by_chapter['chapter_number']} "
                        f"của bộ '{existing_by_chapter['title']}' - ID gốc: {existing_by_chapter['id']})!"
                    ),
                    "comic": existing_by_chapter,
                    "nhentai_data": nhentai_data
                }

            # Bước 3: So sánh tên truyện (không phân biệt hoa thường) với các bộ đã có trong CSDL
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

            # Bước 4: Truyện hoàn toàn mới và hợp lệ để thêm vào thư viện
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
    Lấy đầy đủ thông tin chi tiết của 1 bộ truyện cho trang Chi tiết (`detail.html`):
    - Thông tin cơ bản + Tên thư mục hiện tại
    - Danh sách thể loại chi tiết (`genres`) và tác giả (`artists`)
    - Danh sách các chương/tập (`chapters`)
    - Danh sách đường dẫn toàn bộ trang ảnh (`pages`) của bộ gốc để hiển thị lưới xem trước
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Lấy thông tin cơ bản của bộ truyện kèm tên thư mục
            cur.execute("""
                SELECT c.*, f.name AS folder_name
                FROM comics c
                LEFT JOIN folders f ON c.folder_id = f.id
                WHERE c.id = %s;
            """, (comic_id,))
            comic = cur.fetchone()

            if not comic:
                return None

            # 2. Lấy danh sách thể loại của truyện từ bảng `genres`
            cur.execute("""
                SELECT g.id, g.name, g.slug
                FROM genres g
                JOIN comic_genres cg ON g.id = cg.genre_id
                WHERE cg.comic_id = %s
                ORDER BY g.name ASC;
            """, (comic_id,))
            genres_rows = cur.fetchall()

            # 3. Lấy danh sách tác giả của truyện từ bảng `artists`
            cur.execute("""
                SELECT a.id, a.name, a.slug
                FROM artists a
                JOIN comic_artists ca ON a.id = ca.artist_id
                WHERE ca.comic_id = %s
                ORDER BY a.name ASC;
            """, (comic_id,))
            artists_rows = cur.fetchall()

            # Gắn thông tin thể loại và tác giả vào đối tượng kết quả
            comic["genres"] = [g["name"] for g in genres_rows]
            comic["genres_detail"] = genres_rows
            comic["authors"] = [a["name"] for a in artists_rows]
            comic["author"] = comic.get("artist") or (", ".join(comic["authors"]) if comic["authors"] else "Unknown")

            # 4. Lấy danh sách các tập/chương (chapters) theo thứ tự tăng dần
            cur.execute("""
                SELECT id, chapter_number, title, media_id, start_page, end_page
                FROM chapters
                WHERE comic_id = %s
                ORDER BY chapter_number ASC;
            """, (comic_id,))
            comic["chapters"] = cur.fetchall()

            # 5. Tạo danh sách link ảnh xem trước cho toàn bộ trang của bộ truyện gốc
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
    Sinh danh sách các trang ảnh (từ `start_page` đến `end_page`) của 1 Chapter
    để hiển thị trong Trình đọc truyện (`reader.html`).
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
            # Ưu tiên lấy chuỗi đuôi ảnh riêng của chapter (nếu là phần gộp từ ID khác), nếu trống thì dùng của truyện gốc
            page_exts = ch.get("page_exts") or ch.get("comic_page_exts") or ""

            pages = []
            for page_num in range(start_p, end_p + 1):
                pages.append({
                    "page_number": page_num,
                    "url": build_page_url(media_id, page_num, page_exts)
                })
            return pages


# ==================== 4. CÁC HÀM QUẢN LÝ CHAPTER & XÓA TRUYỆN ====================

def split_comic_into_chapters(comic_id, chapters_data):
    """
    Chia nhỏ bộ truyện gốc thành nhiều Chapter dựa trên mốc trang (`start_page` -> `end_page`) do người dùng nhập.
    Lưu ý:
    - Chỉ thay thế các chapter thuộc cùng `media_id` của bộ truyện gốc.
    - Các chapter ngoại truyện / phần tiếp theo (thêm từ Gallery ID khác) sẽ được giữ nguyên
      và tự động đánh lại số thứ tự nối tiếp phía sau.
    """
    if not chapters_data:
        raise ValueError("Danh sách chapter không được để trống!")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 1: Kiểm tra bộ truyện có tồn tại không và lấy tổng số trang giới hạn
            cur.execute("SELECT id, media_id, num_pages, page_exts FROM comics WHERE id = %s;", (comic_id,))

            comic = cur.fetchone()
            if not comic:
                raise ValueError(f"Không tìm thấy bộ truyện với ID: {comic_id}")

            media_id = comic["media_id"]
            num_pages = comic["num_pages"]
            page_exts = comic.get("page_exts") or ""

            # Bước 2: Kiểm tra tính hợp lệ của từng khoảng trang người dùng gửi lên
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

            # Bước 3: Xóa các chapter cũ thuộc bộ truyện gốc (cùng media_id) trước khi lưu danh sách chia mới
            cur.execute("DELETE FROM chapters WHERE comic_id = %s AND media_id = %s;", (comic_id, str(media_id)))

            # Bước 4: Thêm các chapter vừa chia vào bảng `chapters`
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

            # Bước 5: Cập nhật lại số thứ tự (`chapter_number`) của các phần thêm từ ID khác (nếu có) nối tiếp theo sau
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
    Gộp một bộ truyện từ Gallery ID NHentai khác vào làm Chapter mới của bộ truyện `comic_id` hiện tại.
    Dùng cho các series có nhiều phần (Part 1, Part 2, Ngoại truyện...) có ID riêng trên NHentai.
    """
    # Bước 1: Cào thông tin media_id, tổng số trang và đuôi ảnh của phần mới từ NHentai
    new_gallery = fetch_comic_from_nhentai(gallery_id)
    new_media_id = str(new_gallery["media_id"])
    new_num_pages = new_gallery["num_pages"]
    new_page_exts = new_gallery.get("page_exts", "")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 2: Kiểm tra bộ truyện gốc có tồn tại trong thư viện không
            cur.execute("SELECT id FROM comics WHERE id = %s;", (comic_id,))
            if not cur.fetchone():
                raise ValueError(f"Bộ truyện cha ID {comic_id} không tồn tại!")

            # Bước 3: Nếu người dùng không nhập số thứ tự chapter, tự động lấy (số lớn nhất hiện tại + 1)
            if chapter_number is None:
                cur.execute("""
                    SELECT COALESCE(MAX(chapter_number), 0) + 1 AS next_num
                    FROM chapters
                    WHERE comic_id = %s;
                """, (comic_id,))
                chapter_number = cur.fetchone()["next_num"]

            # Bước 4: Đặt tên mặc định (vd: "Tập 2") nếu người dùng để trống tên chapter
            if not title:
                title = f"Tập {int(chapter_number) if float(chapter_number).is_integer() else chapter_number}"

            # Bước 5: Lưu chapter mới với `media_id` và `page_exts` riêng của phần đó
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
    Xóa một bộ truyện khỏi thư viện theo ID.
    Nhờ ràng buộc `ON DELETE CASCADE` trong CSDL, toàn bộ chapters và liên kết tác giả/thể loại của truyện sẽ tự động được xóa sạch.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM comics WHERE id = %s;", (comic_id,))
            deleted = cur.rowcount > 0

    if deleted:
        print(f"[INFO] Da xoa bo truyen ID: {comic_id}")
    return deleted


# ==================== 5. CÁC HÀM QUẢN LÝ THƯ MỤC & TÁC GIẢ ====================

def get_all_folders():
    """Lấy danh sách tất cả thư mục, sắp xếp theo ID tăng dần (thư mục Mặc định luôn ở đầu)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM folders ORDER BY id ASC;")
            return cur.fetchall()


def create_folder(name, description = ""):
    """
    Tạo một thư mục phân loại truyện mới.
    Nếu tên thư mục đã tồn tại thì chỉ cập nhật lại phần mô tả.
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
    Đổi tên một thư mục hiện có (bảo vệ thư mục 'Mặc định' có ID = 1 không bị đổi tên).
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
    Xóa một thư mục (không cho phép xóa thư mục 'Mặc định' ID = 1).
    Trước khi xóa, tất cả truyện đang nằm trong thư mục đó sẽ được chuyển về thư mục 'Mặc định' (ID = 1).
    """
    if folder_id == 1:
        raise ValueError("Không thể xóa thư mục 'Mặc định'!")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Bước 1: Chuyển các bộ truyện thuộc thư mục sắp xóa về thư mục Mặc định (ID = 1)
            cur.execute("UPDATE comics SET folder_id = 1 WHERE folder_id = %s;", (folder_id,))

            # Bước 2: Xóa thư mục khỏi bảng `folders`
            cur.execute("DELETE FROM folders WHERE id = %s;", (folder_id,))
            deleted = cur.rowcount > 0
            if not deleted:
                raise ValueError(f"Thư mục ID {folder_id} không tồn tại!")

    print(f"[INFO] Da xoa thu muc ID: {folder_id}")
    return True


def update_comic_folder(comic_id, folder_id):
    """
    Cập nhật thư mục chứa bộ truyện (dùng khi người dùng đổi thư mục trong trang Chi tiết).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Kiểm tra thư mục đích có tồn tại không
            cur.execute("SELECT id, name FROM folders WHERE id = %s;", (folder_id,))
            folder = cur.fetchone()
            if not folder:
                raise ValueError(f"Thư mục ID {folder_id} không tồn tại!")

            # Cập nhật `folder_id` mới cho bộ truyện
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
    """
    Lấy danh sách các tác giả hiện đang có ít nhất 1 bộ truyện trong thư viện (nhờ JOIN với `comic_artists`).
    Giúp ô lọc Tác giả ở Trang chủ không bị hiển thị các tác giả rỗng sau khi xóa truyện.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT a.id, a.name, a.slug
                FROM artists a
                JOIN comic_artists ca ON a.id = ca.artist_id
                ORDER BY a.name ASC;
            """)
            return cur.fetchall()


# ==================== 6. BỘ CÔNG CỤ KIỂM THỬ TRÊN TERMINAL ====================


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
            comics_data = get_all_comics()
            comics_list = comics_data["items"]
            print(f"-> Tổng số truyện trong thư viện: {comics_data['total_comics']} bộ (Trang {comics_data['page']}/{comics_data['total_pages']})")
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
                filtered_data = get_all_comics(artist_id=first_author_id)
                filtered_comics = filtered_data["items"]
                print(f"-> Tìm thấy {filtered_data['total_comics']} truyện của tác giả '{author_name}':")
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
                folder_data = get_all_comics(folder_id=target_folder_id)
                folder_comics = folder_data["items"]
                print(f"-> Tìm thấy {folder_data['total_comics']} bộ truyện:")
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
        


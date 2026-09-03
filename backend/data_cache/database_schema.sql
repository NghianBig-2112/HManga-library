-- =========================================================================
-- HManga Library — Database Schema (Cấu trúc Cơ Sở Dữ Liệu Supabase)
-- =========================================================================
-- Hướng dẫn: Copy toàn bộ nội dung file này và chạy trong Supabase SQL Editor.
-- Cấu trúc: Tối giản, không lưu timestamp, không phân loại multi/oneshot, không tag.
-- =========================================================================

-- 1. BẢNG TRUYỆN TRANH (comics)
-- Lưu thông tin cơ bản của từng bộ truyện trong thư viện:
-- - id: Khóa chính tự động tăng theo thứ tự thêm vào (1, 2, 3...)
-- - gallery_id: Mã ID định dạng 'xxx-xxxxx' (VD: '001-48410')
-- - title: Tên bộ truyện
-- - author: Tên tác giả
-- - cover_filename: Tên file ảnh bìa lưu tại local (VD: 001-48410.jpg)
-- - source_url: Đường link gốc tham khảo từ nhentai
CREATE TABLE IF NOT EXISTS public.comics (
    id SERIAL PRIMARY KEY,
    gallery_id VARCHAR(50),
    title VARCHAR(255) NOT NULL,
    author VARCHAR(255),
    cover_filename VARCHAR(100),
    source_url TEXT
);

-- MIGRATION MỚI NHẤT: Thêm cột gallery_id vào bảng comics nếu chưa có
ALTER TABLE public.comics ADD COLUMN IF NOT EXISTS gallery_id VARCHAR(50);
UPDATE public.comics 
SET gallery_id = SPLIT_PART(cover_filename, '.', 1) 
WHERE gallery_id IS NULL AND cover_filename IS NOT NULL AND cover_filename != '';

-- Dọn dẹp các cột cũ không sử dụng (nếu database đã tồn tại từ trước)
ALTER TABLE public.comics DROP COLUMN IF EXISTS type;
ALTER TABLE public.comics DROP COLUMN IF EXISTS status;
ALTER TABLE public.comics DROP COLUMN IF EXISTS personal_note;
ALTER TABLE public.comics DROP COLUMN IF EXISTS created_at;
ALTER TABLE public.comics DROP COLUMN IF EXISTS updated_at;

-- 2. XÓA BỎ HỆ THỐNG TAGS CŨ (NẾU CÓ)
-- Xóa bảng liên kết và bảng tags cũ để chuyển hẳn sang thể loại (genres)
DROP TABLE IF EXISTS public.comic_tags CASCADE;
DROP TABLE IF EXISTS public.tags CASCADE;
DROP INDEX IF EXISTS idx_tags_name;

-- 3. BẢNG THỂ LOẠI (genres)
-- Lưu danh mục các thể loại truyện (Action, Romance, Comedy...):
-- - id: Khóa chính
-- - name: Tên thể loại (DUY NHẤT - UNIQUE, không trùng lặp)
CREATE TABLE IF NOT EXISTS public.genres (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

-- Gỡ bỏ cột timestamp nếu có từ phiên bản trước
ALTER TABLE public.genres DROP COLUMN IF EXISTS created_at;

-- 4. BẢNG LIÊN KẾT TRUYỆN & THỂ LOẠI (comic_genres)
-- Bảng trung gian giải quyết quan hệ Nhiều - Nhiều (Many-to-Many):
-- - 1 truyện có thể có nhiều thể loại.
-- - 1 thể loại có thể gắn cho nhiều truyện.
-- - ON DELETE CASCADE: Khi xóa truyện hoặc xóa thể loại, liên kết sẽ tự động bị xóa.
CREATE TABLE IF NOT EXISTS public.comic_genres (
    comic_id INT REFERENCES public.comics(id) ON DELETE CASCADE,
    genre_id INT REFERENCES public.genres(id) ON DELETE CASCADE,
    PRIMARY KEY (comic_id, genre_id)
);

-- 5. BẢNG CHƯƠNG TRUYỆN (chapters)
-- Lưu thông tin từng chương/tập của bộ truyện:
-- - id: Khóa chính
-- - comic_id: Khóa ngoại liên kết tới bộ truyện trong bảng comics
-- - chapter_number: Số thứ tự chương (VD: 1, 1.5, 2...)
-- - title: Tên chương tùy chọn
-- - base_url: Link ảnh mẫu (trang 1) dùng để sinh URL các trang ảnh khi đọc
-- - start_page: Số trang bắt đầu (VD: 1)
-- - end_page: Số trang kết thúc (VD: 25)
-- - UNIQUE (comic_id, chapter_number): Không cho phép trùng số chương trong cùng 1 truyện
CREATE TABLE IF NOT EXISTS public.chapters (
    id SERIAL PRIMARY KEY,
    comic_id INT NOT NULL REFERENCES public.comics(id) ON DELETE CASCADE,
    chapter_number NUMERIC(6,1) NOT NULL,
    title VARCHAR(255),
    base_url TEXT NOT NULL,
    start_page INT NOT NULL DEFAULT 1,
    end_page INT NOT NULL,
    UNIQUE (comic_id, chapter_number)
);

-- Migration cập nhật bảng chapters (nếu database đã tồn tại cột total_pages cũ)
ALTER TABLE public.chapters ADD COLUMN IF NOT EXISTS start_page INT NOT NULL DEFAULT 1;
ALTER TABLE public.chapters ADD COLUMN IF NOT EXISTS end_page INT;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chapters' AND column_name='total_pages') THEN
        UPDATE public.chapters SET end_page = total_pages WHERE end_page IS NULL;
        ALTER TABLE public.chapters ALTER COLUMN end_page SET NOT NULL;
        ALTER TABLE public.chapters DROP COLUMN total_pages;
    END IF;
END $$;

-- Gỡ bỏ cột timestamp khỏi bảng chapters nếu có
ALTER TABLE public.chapters DROP COLUMN IF EXISTS created_at;
ALTER TABLE public.chapters DROP COLUMN IF EXISTS updated_at;

-- Gỡ bỏ trigger tự động cập nhật timestamp (nếu có)
DROP TRIGGER IF EXISTS update_comics_modtime ON public.comics;
DROP TRIGGER IF EXISTS update_chapters_modtime ON public.chapters;
DROP FUNCTION IF EXISTS update_modified_column CASCADE;

-- 6. INDEXES TỐI ƯU HÓA TỐC ĐỘ TÌM KIẾM
CREATE INDEX IF NOT EXISTS idx_comics_title ON public.comics(title);
CREATE INDEX IF NOT EXISTS idx_comics_author ON public.comics(author);
CREATE INDEX IF NOT EXISTS idx_chapters_comic_id ON public.chapters(comic_id);
CREATE INDEX IF NOT EXISTS idx_chapters_number ON public.chapters(comic_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_genres_name ON public.genres(name);

-- Gỡ index cũ không còn dùng
DROP INDEX IF EXISTS idx_comics_status;
DROP INDEX IF EXISTS idx_comics_type;

-- 7. NẠP SẴN DANH SÁCH CÁC THỂ LOẠI MẪU PHỔ BIẾN
INSERT INTO public.genres (name) VALUES
    ('Action'),
    ('Adventure'),
    ('Comedy'),
    ('Drama'),
    ('Fantasy'),
    ('Harem'),
    ('Horror'),
    ('Mystery'),
    ('Romance'),
    ('School Life'),
    ('Sci-Fi'),
    ('Slice of Life'),
    ('Supernatural'),
    ('Ecchi'),
    ('Doujinshi'),
    ('Manga'),
    ('Manhwa'),
    ('Manhua')
ON CONFLICT (name) DO NOTHING;

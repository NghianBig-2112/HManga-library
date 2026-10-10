"""
Backup Module (Supabase & Minimal JSON Format)
==============================================
Quản lý kết xuất bản sao lưu ra file backup.json và tự động phục hồi lên Supabase khi database trống.
"""

import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from database import get_supabase

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent

def get_backup_filepath() -> Path:
    """Xác định đường dẫn file backup.json (ưu tiên root/backup.json, sau đó backend/data/backup.json)."""
    root_backup = ROOT_DIR / "backup.json"
    backend_backup = BACKEND_DIR / "data" / "backup.json"
    if root_backup.exists():
        return root_backup
    if backend_backup.exists():
        return backend_backup
    return root_backup

BACKUP_FILE = get_backup_filepath()


def export_library_data() -> dict:
    """
    Trích xuất toàn bộ dữ liệu từ Supabase sang từ điển (dict) theo định dạng tối giản:
    {
      "folders": [...],
      "comics": [...]
    }
    """
    sb = get_supabase()

    # 1. Danh sách thư mục
    f_res = sb.table("folders").select("id, name, description").order("id", desc=False).execute()
    folders_list = f_res.data or []

    # 2. Danh sách truyện
    c_res = sb.table("comics").select("id, media_id, title_pretty, cover_path, num_pages").order("created_at", desc=False).execute()
    comics_raw = c_res.data or []

    if not comics_raw:
        return {"folders": folders_list, "comics": []}

    # 3. Lấy quan hệ tags, folders, chapters
    fc_res = sb.table("folder_comics").select("folder_id, comic_id").execute()
    folder_map = {}
    for fc in (fc_res.data or []):
        folder_map.setdefault(fc["comic_id"], []).append(fc["folder_id"])

    ct_res = sb.table("comic_tags").select("comic_id, tags(id, type, name, slug)").execute()
    tags_map = {}
    for row in (ct_res.data or []):
        c_id = row.get("comic_id")
        t_data = row.get("tags")
        if c_id and t_data:
            tags_map.setdefault(c_id, []).append(t_data)

    ch_res = sb.table("chapters").select("comic_id, chapter_number, title, media_id, start_page, end_page").order("chapter_number", desc=False).execute()
    ch_map = {}
    for ch in (ch_res.data or []):
        c_id = ch["comic_id"]
        ch_map.setdefault(c_id, []).append({
            "chap": ch["chapter_number"],
            "title": ch.get("title") or f"Chapter {ch['chapter_number']}",
            "media_id": ch.get("media_id", ""),
            "start": ch.get("start_page", 1),
            "end": ch.get("end_page", 1)
        })

    formatted_comics = []
    for c in comics_raw:
        c_id = c["id"]
        formatted_comics.append({
            "id": c_id,
            "media_id": str(c["media_id"]),
            "title": c["title_pretty"],
            "cover": c["cover_path"],
            "pages": int(c["num_pages"]),
            "folders": folder_map.get(c_id, [1]),
            "tags": tags_map.get(c_id, []),
            "chapters": ch_map.get(c_id, [])
        })

    return {
        "folders": folders_list,
        "comics": formatted_comics
    }


def save_backup_file(filepath: Path = None) -> str:
    """Xuất dữ liệu và lưu vào file backup.json trên đĩa."""
    target_path = filepath or get_backup_filepath()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    data = export_library_data()
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(target_path)


def restore_backup_from_file(filepath: Path = None) -> dict:
    """
    Nạp dữ liệu từ backup.json lên Supabase bằng Batch Upsert.
    """
    target_path = filepath or get_backup_filepath()
    if not target_path.exists():
        return {"success": False, "message": "Không tìm thấy file backup"}

    sb = get_supabase()
    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Folders
    folders = data.get("folders", [])
    if folders:
        sb.table("folders").upsert(folders).execute()

    # 2. Gom dữ liệu theo bảng
    comics_batch = []
    tags_batch = {}
    comic_tags_batch = []
    folder_comics_batch = []
    chapters_batch = []

    for c in data.get("comics", []):
        c_id = c["id"]
        m_id = str(c.get("media_id", c_id))

        comics_batch.append({
            "id": c_id,
            "media_id": m_id,
            "title_pretty": c["title"],
            "cover_path": c["cover"],
            "num_pages": int(c["pages"])
        })

        for f_id in c.get("folders", [1]):
            folder_comics_batch.append({"folder_id": f_id, "comic_id": c_id})

        for t in c.get("tags", []):
            tags_batch[t["id"]] = t
            comic_tags_batch.append({"comic_id": c_id, "tag_id": t["id"]})

        chaps = c.get("chapters", [])
        if chaps:
            for ch in chaps:
                chapters_batch.append({
                    "comic_id": c_id,
                    "chapter_number": ch["chap"],
                    "title": ch.get("title", f"Chapter {ch['chap']}"),
                    "media_id": str(ch.get("media_id", m_id)),
                    "start_page": ch["start"],
                    "end_page": ch["end"]
                })
        else:
            chapters_batch.append({
                "comic_id": c_id,
                "chapter_number": 1.0,
                "title": "Full",
                "media_id": m_id,
                "start_page": 1,
                "end_page": int(c["pages"])
            })

    # 3. Batch Upsert lên Supabase
    if comics_batch:
        sb.table("comics").upsert(comics_batch).execute()
    if tags_batch:
        sb.table("tags").upsert(list(tags_batch.values())).execute()
    if folder_comics_batch:
        sb.table("folder_comics").upsert(folder_comics_batch).execute()
    if comic_tags_batch:
        sb.table("comic_tags").upsert(comic_tags_batch).execute()
    if chapters_batch:
        sb.table("chapters").upsert(chapters_batch).execute()

    print(f"[HOÀN TẤT] Đã khôi phục {len(comics_batch)} bộ truyện lên Supabase!")
    return {
        "success": True,
        "so_truyen_khoi_phuc": len(comics_batch)
    }


def auto_restore_if_empty() -> bool:
    """Tự động khôi phục dữ liệu lên Supabase nếu database trống."""
    try:
        sb = get_supabase()
        res = sb.table("comics").select("id", count="exact").limit(1).execute()
        backup_path = get_backup_filepath()
        if (res.count or 0) == 0 and backup_path.exists():
            print(f"[INFO] Supabase chưa có truyện nào, phát hiện {backup_path.name}. Đang tự động khôi phục...")
            result = restore_backup_from_file(backup_path)
            print(f"[INFO] Tự động khôi phục hoàn tất: {result.get('so_truyen_khoi_phuc', 0)} truyện.")
            return True
        return False
    except Exception as e:
        print(f"[WARN] Auto-restore kiểm tra thất bại: {e}")
        return False

"""
Database Module (Supabase PostgreSQL)
=====================================
Quản lý kết nối tới máy chủ cơ sở dữ liệu Supabase.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)

_supabase_client: Client = None


def get_supabase() -> Client:
    """Tạo và trả về kết nối Supabase Client (singleton)."""
    global _supabase_client
    if _supabase_client is None:
        load_dotenv(ENV_FILE, override=True)
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()

        if not url or not key:
            raise RuntimeError(
                "Chưa cấu hình SUPABASE_URL hoặc SUPABASE_KEY trong file backend/.env! "
                "Vui lòng cung cấp thông tin kết nối Supabase."
            )
        _supabase_client = create_client(url, key)
    return _supabase_client


def init_db():
    """Kiểm tra kết nối tới Supabase và đảm bảo folder 'Mặc định' tồn tại."""
    sb = get_supabase()
    try:
        # Kiểm tra folder Mặc định
        res = sb.table("folders").select("id").eq("name", "Mặc định").execute()
        if not res.data:
            sb.table("folders").insert({
                "name": "Mặc định",
                "description": "Thư mục truyện mặc định"
            }).execute()
            print("[INFO] Đã tạo thư mục 'Mặc định' trên Supabase.")
        print("[INFO] Kết nối Supabase thành công và sẵn sàng phục vụ.")
    except Exception as e:
        print(f"[WARN] Lỗi khi kết nối hoặc khởi tạo bảng trên Supabase: {e}")

"""
Core Configuration Module
=========================
Quản lý các thông số cấu hình và biến môi trường (.env) cho ứng dụng.
Nhiệm vụ:
- Định nghĩa schema cấu hình bằng Pydantic BaseSettings.
- Tự động đọc file .env từ thư mục gốc của project (Supabase URL, Anon Key, Service Role Key).
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# Đường dẫn đến thư mục gốc của project (HManga-library)
BASE_DIR = Path(__file__).parent.parent.parent

class Settings(BaseSettings):
    """
    Lớp cấu hình hệ thống:
    - SUPABASE_URL: URL dự án Supabase
    - SUPABASE_ANON_KEY: Khóa công khai Anon của Supabase
    - SUPABASE_SERVICE_ROLE_KEY: Khóa quản trị Service Role (dùng cho backend kết nối không giới hạn RLS)
    """
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    COVER_IMAGES_DIR: str = "frontend/assets"
    CACHE_FILE: str = "backend/data_cache/comics_cache.json"

    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Khởi tạo đối tượng cấu hình singleton để sử dụng toàn ứng dụng
settings = Settings()

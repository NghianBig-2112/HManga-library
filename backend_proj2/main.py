from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from nhentai_service import fetch_manga_from_nhentai

# 1. Khởi tạo ứng dụng fastapi
app = FastAPI(
	title = "My personal manga api",
	description = "Backend lưu trữ truyện tranh cá nhân từ NHentai",
	version = "1.0.0"
)

# 2. Cấu hình CORS (Cross-Origin Resource Sharing)
# Giúp Frontend (HTML/JS) gọi được API từ Backend mà không bị trình duyệt chặn
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],       # Cho phép mọi nguồn truy cập (đang ở môi trường dev)
	allow_credentials=True,
	allow_methods=["*"],       # Cho phép GET, POST, DELETE, UPDATE
	allow_headers=["*"],
)

# 3. Tạo một đường dẫn (Route) kiểm tra đầu tiên
@app.get("/")
def home():
	return {
		"status": "online",
		"message": "Chào mừng bạn đến với Web truyện cá nhân"
	}

# API tra cứu thông tin truyện theo ID
@app.get("/api/v2/galleries/{manga_id}")
def get_nhentai_manga(manga_id):
	try:
		data = fetch_manga_from_nhentai(manga_id)
		if not data:
			raise HTTPException(status_code=404, detail=f"Không tìm thấy truyện với id: {manga_id}")
		return data
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))
"""
- Lấy dữ liệu từ nhentai: id, media_id, title_pretty, tags, num_pages, pages
"""

import requests
# from urllib.parse import urlparse

NHENTAI_SERVER = "https://nhentai.net/"
IMAGE_SERVER = "https://i3.nhentai.net"
THUMB_SERVER = "https://t3.nhentai.net"

def get_gallery_by_id(gallery_id):
	url = f"{NHENTAI_SERVER}/api/v2/galleries/{gallery_id}"

	# Header giả lập trình duyệt để tránh bị chặn 403
	headers = {
		"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
		"Referer": NHENTAI_SERVER
	}

	# Gửi GET request với thời gian chờ tối đa 10 giây
	response = requests.get(url, headers=headers, timeout=10)

	# Kiểm tra mã phản hồi HTTP
	if response.status_code == 200:
		return response.json()  # Trả về dict
	elif response.status_code == 404:
		raise Exception(f"Không tìm thấy truyện với ID: {gallery_id}")
	else:
		raise Exception(f"Lỗi khi gọi API: HTTP {response.status_code}")

def extract_gallery_data(data):
	"""
	Nhận raw dict từ API và bóc tách các trường dữ liệu cần thiết.
	"""
	# 1. Lấy id truyện
	id = int(data.get("id"))
	media_id = int(data.get("media_id"))

	# 2. Lấy tên truyện
	title_pretty = str(data.get("title").get("pretty"))

	# 3. Lấy đường dẫn ảnh bìa
	cover_path = data.get("cover").get("path")
	cover_url = f"{THUMB_SERVER}/{cover_path}"

	# 4. Lấy các tag
	language = "Unknown"
	category = "Unknown"
	artists = []
	genres = []
	tag_list = []

	for tag in data.get("tags", []):
		tag_id = tag.get("id")
		tag_type = tag.get("type")
		tag_name = tag.get("name")
		tag_slug = tag.get("slug")
		tag_description = tag.get("description")

		tag_list.append({
			"id": tag_id,
			"type": tag_type,
			"name": tag_name,
			"slug": tag_slug,
			"description": tag_description
		})

		if tag_type == "language" and tag_name in ("english", "japanese", "chinese"):
			language = tag_name
		elif tag_type == "category" and tag_name in ("manga", "doujinshi"):
			category = tag_name
		elif tag_type == "artist":
			artists.append(tag_name)
		elif tag_type == "tag":
			genres.append(tag_name)


	# 5. Lấy số trang
	num_pages = int(data.get("num_pages"))

	# 6: Lấy đường dẫn ảnh và mã hóa đuôi từng trang (j=jpg, p=png, w=webp, g=gif)
	pages = data.get("pages")
	page_list = []
	ext_chars = []
	for page in pages:
		page_path = page.get("path")
		page_list.append(f"{IMAGE_SERVER}/{page_path}")
		ext = page_path.split(".")[-1].lower()
		ext_chars.append(ext[0] if ext else "j")

	page_exts = "".join(ext_chars)

	# Trả về kết quả sạch sẽ theo cấu trúc bạn muốn
	return {
		"id": id,
		"media_id": media_id,
		"title": title_pretty,
		"cover_url": cover_url,
		"language": language,
		"category": category,
		"artists": artists,
		"genres": genres,
		"tags": tag_list,
		"num_pages": num_pages,
		"page_exts": page_exts,
		"pages": page_list
	}


def fetch_comic_from_nhentai(gallery_id):
	raw_data = get_gallery_by_id(gallery_id)
	data_extract = extract_gallery_data(raw_data)
	return data_extract

if __name__ == "__main__":
	start_find = 500000
	end_find = 686500
	step = 1000  # Nhảy bước 1000 ID để quét phủ khắp các thời kỳ thật nhanh

	page_extensions = set()
	cover_extensions = set()

	for i in range(start_find, end_find + 1, step):
		try:
			dict_data = fetch_comic_from_nhentai(i)

			# 1. Kiểm tra đuôi của ảnh bìa (cover_url)
			cover_file = dict_data["cover_url"].split("/")[-1]
			cover_ext = "." + cover_file.split(".", 1)[1]
			if cover_ext not in cover_extensions:
				cover_extensions.add(cover_ext)
				print(f"[ĐUÔI BÌA MỚI: {cover_ext}] -> ID {i}: {dict_data['cover_url']}")

			# 2. Kiểm tra đuôi của tất cả các trang (pages)
			for page_url in dict_data["pages"]:
				filename = page_url.split("/")[-1]
				ext = "." + filename.split(".", 1)[1]
				if ext not in page_extensions:
					page_extensions.add(ext)
					print(f"[ĐUÔI TRANG MỚI: {ext}] -> ID {i}: {page_url}")

		except Exception:
			continue

	print("\n=== TỔNG HỢP ĐUÔI ẢNH BÌA (COVER) ===")
	print(cover_extensions)
	print("\n=== TỔNG HỢP ĐUÔI TRANG TRUYỆN (PAGES) ===")
	print(page_extensions)
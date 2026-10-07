import requests
import socket


# Dạy Python trỏ thẳng vào IP máy chủ thay vì bị DNS nhà mạng lừa về 127.0.0.1
_orig_getaddrinfo = socket.getaddrinfo
def _cf_getaddrinfo(host, port, *args, **kwargs):
	if host and ("nhentai.net" in host):
		return _orig_getaddrinfo("172.67.74.203", port, *args, **kwargs)
	return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _cf_getaddrinfo


def fetch_manga_from_nhentai(manga_id):
	# lấy trực tiếp toàn bộ dữ liệu của nhentai
	url = f"https://nhentai.net/api/v2/galleries/{manga_id}"

	# Giả lập header cơ bản để nhentai chấp nhận
	headers = {
		"User-Agent": "Mozilla/5.0",
		"Referer": "https://nhentai.net/"
	}

	response = requests.get(url, headers=headers, timeout=10)
	if response.status_code == 404:
		return None
	if response.status_code != 200:
		raise Exception(f"Lỗi Nhentai: {response.status_code}")

	return response.json()
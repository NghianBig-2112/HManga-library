def check_tag_name(tag_type, tag_name):
	language = "Unknown"
	if tag_type == "language" and tag_name == "english" or tag_name == "japanese":
		language = str(tag_name)
	return language

if __name__ == "__main__":
	print(check_tag_name("language", "translated"))
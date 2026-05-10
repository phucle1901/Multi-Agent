import json
from pathlib import Path

input_file = Path("url2.json")
output_file = Path("url3.json")

with open(input_file, "r", encoding="utf-8") as f:
    data = json.load(f)

cleaned = []
for item in data:
    # copy để không sửa trực tiếp dữ liệu gốc
    new_item = dict(item)

    # xóa key base_url
    new_item.pop("base_url", None)

    # xóa các url có loai_job = "Tất cả"
    if "urls" in new_item and isinstance(new_item["urls"], list):
        new_item["urls"] = [
            url_item
            for url_item in new_item["urls"]
            if url_item.get("loai_job") != "Tất cả"
        ]

    cleaned.append(new_item)

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

print(f"Đã lưu file mới: {output_file}")
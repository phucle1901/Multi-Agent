#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

JOB_TYPE_MAP = {
    "": "Tất cả",
    "kinh-doanh-ban-hang": "Kinh doanh / Bán hàng",
    "marketing-pr-quang-cao": "Marketing / PR / Quảng cáo",
    "cham-soc-khach-hang-customer-service-van-hanh": "Chăm sóc khách hàng / Customer Service / Vận hành",
    "nhan-su-hanh-chinh-phap-che": "Nhân sự / Hành chính / Pháp chế",
    "cong-nghe-thong-tin": "Công nghệ thông tin",
    "lao-dong-pho-thong": "Lao động phổ thông",
    "tai-chinh-ngan-hang-bao-hiem": "Tài chính / Ngân hàng / Bảo hiểm",
    "bat-dong-san": "Bất động sản",
    "xay-dung": "Xây dựng",
    "ke-toan-kiem-toan-thue": "Kế toán / Kiểm toán / Thuế",
    "san-xuat": "Sản xuất",
    "giao-duc-dao-tao": "Giáo dục / Đào tạo",
    "ban-le-dich-vu-doi-song": "Bán lẻ / Dịch vụ đời sống",
    "phim-va-truyen-hinh-bao-chi-xuat-ban": "Phim và truyền hình / Báo chí / Xuất bản",
    "dien-dien-tu-vien-thong": "Điện / Điện tử / Viễn thông",
    "logistics-thu-mua-kho-van": "Logistics / Thu mua / Kho vận",
    "tu-van-chuyen-mon": "Tư vấn chuyên môn",
    "duoc-y-te-suc-khoe-cong-nghe-sinh-hoc": "Dược / Y tế / Sức khỏe / Công nghệ sinh học",
    "thiet-ke": "Thiết kế",
    "nha-hang-khach-san-du-lich": "Nhà hàng / Khách sạn / Du lịch",
    "nang-luong-moi-truong-nong-nghiep": "Năng lượng / Môi trường / Nông nghiệp",
    "tai-xe": "Tài xế",
    "bien-phien-dich": "Biên / Phiên dịch",
    "luat": "Luật",
}


def extract_job_slug(url: str) -> str:
    """Extract the job slug between `/tim-viec-lam-` and `-tai-...`.

    Examples:
    - /tim-viec-lam-luat-tai-ha-noi... -> luat
    - /tim-viec-lam-tai-phuong-ba-dinh... -> "" (means all jobs)
    """
    path = urlparse(url).path.lower()

    if "/tim-viec-lam-tai-" in path:
        return ""

    match = re.search(r"/tim-viec-lam-(.*?)-tai-", path)
    if match:
        return match.group(1).strip("-")

    return ""


def slug_to_label(slug: str) -> str:
    if slug in JOB_TYPE_MAP:
        return JOB_TYPE_MAP[slug]

    # Fallback if a new slug appears that is not in the mapping.
    words = [w for w in slug.split("-") if w]
    return " ".join(word.capitalize() for word in words) if words else "Tất cả"


def enrich_url(url: str, xa_phuong: str) -> dict[str, str]:
    slug = extract_job_slug(url)
    return {
        "url": url,
        "xa_phuong": xa_phuong,
        "loai_job": slug_to_label(slug),
    }


def enrich_payload(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []

    for entry in data:
        xa_phuong = entry.get("name", "")
        new_entry = dict(entry)

        if isinstance(entry.get("base_url"), str):
            new_entry["base_url"] = enrich_url(entry["base_url"], xa_phuong)

        urls = entry.get("urls", [])
        if isinstance(urls, list):
            new_entry["urls"] = [
                enrich_url(url, xa_phuong) if isinstance(url, str) else url
                for url in urls
            ]

        enriched.append(new_entry)

    return enriched


def build_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_enriched.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Đọc file JSON TopCV và gắn metadata xa_phuong + loai_job cho từng URL."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default="url.json",
        help="Đường dẫn file JSON đầu vào. Mặc định: url.json",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Đường dẫn file JSON đầu ra. Mặc định: <input>_enriched.json",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file đầu vào: {input_path}")

    output_path = Path(args.output) if args.output else build_output_path(input_path)

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("File JSON đầu vào phải là một list các object.")

    enriched_data = enrich_payload(data)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(enriched_data, f, ensure_ascii=False, indent=2)

    print(f"Đã tạo file: {output_path}")


if __name__ == "__main__":
    main()

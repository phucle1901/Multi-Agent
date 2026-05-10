#!/usr/bin/env python3
"""Gộp và loại bỏ trùng lặp links_job.json → merged_links.json.

Cùng một link_job có thể xuất hiện nhiều lần với xa_phuong/loai_job khác nhau.
Script này gộp chúng thành một bản ghi duy nhất với danh sách xa_phuong và loai_job.
"""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path


def merge_links(input_path: str, output_path: str) -> None:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file input: {input_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    grouped = defaultdict(lambda: {"xa_phuong": set(), "loai_job": set()})

    for item in data:
        link = (item.get("link_job") or "").strip()
        if not link:
            continue
        xa = (item.get("xa_phuong") or "").strip()
        loai = (item.get("loai_job") or "").strip()
        if xa:
            grouped[link]["xa_phuong"].add(xa)
        if loai:
            grouped[link]["loai_job"].add(loai)

    result = []
    for link_job, meta in grouped.items():
        result.append({
            "link_job": link_job,
            "xa_phuong": sorted(meta["xa_phuong"]),
            "loai_job": sorted(meta["loai_job"]),
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Gộp {len(data)} bản ghi → {len(result)} link duy nhất")
    print(f"Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Gộp và loại bỏ trùng lặp job links"
    )
    parser.add_argument(
        "--input",
        default=os.getenv("JOBCRAWL_LINKS_OUTPUT", "links_job.json"),
        help="Đường dẫn file input (env: JOBCRAWL_LINKS_OUTPUT)",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("JOBCRAWL_MERGED_LINKS", "merged_links.json"),
        help="Đường dẫn file output (env: JOBCRAWL_MERGED_LINKS)",
    )
    args = parser.parse_args()
    merge_links(args.input, args.output)


if __name__ == "__main__":
    main()

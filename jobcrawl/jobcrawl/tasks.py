"""Entry points cho Airflow integration.

Mỗi function tương ứng 1 task trong Airflow DAG.
Dùng subprocess để chạy spider/script → tránh Twisted reactor conflict,
mỗi task chạy trong process riêng biệt.

Sử dụng:
    - Airflow PythonOperator: gọi trực tiếp function
    - Airflow BashOperator: gọi `python -m jobcrawl.tasks <task_name>`
    - CLI: python -m jobcrawl.tasks crawl_links / merge / crawl_details / all
"""

import argparse
import logging
import subprocess
import sys

from jobcrawl import config

logger = logging.getLogger(__name__)


def _run_subprocess(cmd: list[str], cwd: str | None = None, label: str = "task") -> None:
    """Chạy subprocess, capture stdout+stderr; nếu fail → in tail log + raise rõ ràng.

    Đối với debug local: log ra console thay vì để CalledProcessError che lỗi gốc.
    """
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        # In stdout/stderr để admin biết tại sao fail
        if result.stdout:
            print(f"[{label}] STDOUT:\n{result.stdout[-4000:]}", file=sys.stderr)
        if result.stderr:
            print(f"[{label}] STDERR:\n{result.stderr[-4000:]}", file=sys.stderr)
        raise RuntimeError(
            f"{label} failed (exit code {result.returncode}). "
            f"Last stderr: {result.stderr[-500:] if result.stderr else 'empty'}"
        )
    # Re-emit subprocess output để Admin UI tail log thấy được
    if result.stdout:
        sys.stdout.write(result.stdout)
        sys.stdout.flush()


def crawl_job_links(input_file=None, output_file=None):
    """Bước 2: Crawl danh sách link job từ URL tìm kiếm."""
    input_file = input_file or config.URL_INPUT
    output_file = output_file or config.LINKS_JOB_OUTPUT

    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "topcv_spider_geturl",
        "-a", f"input_file={input_file}",
        "-O", output_file,
    ]
    _run_subprocess(cmd, cwd=str(config.BASE_DIR), label="crawl_links")


def merge_job_links(input_file=None, output_file=None):
    """Bước 3: Gộp trùng link job."""
    input_file = input_file or config.LINKS_JOB_OUTPUT
    output_file = output_file or config.MERGED_LINKS

    cmd = [
        sys.executable,
        str(config.BASE_DIR / "scripts" / "merge_links.py"),
        "--input", input_file,
        "--output", output_file,
    ]
    _run_subprocess(cmd, label="merge_links")


def crawl_job_details(input_file=None, output_file=None):
    """Bước 4: Crawl chi tiết từng job."""
    input_file = input_file or config.MERGED_LINKS
    output_file = output_file or config.JOB_DETAILS

    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "topcv_spider_detail",
        "-a", f"input_file={input_file}",
        "-a", f"output_file={output_file}",
    ]
    _run_subprocess(cmd, cwd=str(config.BASE_DIR), label="crawl_details")


def run_full_pipeline(url_input=None):
    """Chạy toàn bộ pipeline: crawl links → merge → crawl details."""
    crawl_job_links(input_file=url_input)
    merge_job_links()
    crawl_job_details()


def main():
    parser = argparse.ArgumentParser(description="Jobcrawl pipeline tasks")
    parser.add_argument(
        "task",
        choices=["crawl_links", "merge", "crawl_details", "all"],
        help="Task cần chạy",
    )
    args = parser.parse_args()

    task_map = {
        "crawl_links": crawl_job_links,
        "merge": merge_job_links,
        "crawl_details": crawl_job_details,
        "all": run_full_pipeline,
    }
    task_map[args.task]()


if __name__ == "__main__":
    main()

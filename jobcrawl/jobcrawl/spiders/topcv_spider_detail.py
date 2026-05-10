import json
from datetime import datetime, timezone
from pathlib import Path

import scrapy
from scrapy.spidermiddlewares.httperror import HttpError

from jobcrawl import config
from jobcrawl.items import JobDetailItem


class TopcvJobDetailSpider(scrapy.Spider):
    name = "topcv_spider_detail"
    allowed_domains = ["topcv.vn"]

    # Map header h3 → field name trong JobDetailItem
    SECTION_MAP = {
        "Mô tả công việc": "job_description",
        "Yêu cầu ứng viên": "requirements",
        "Quyền lợi": "benefits",
        "Địa điểm làm việc": "work_location",
        "Thời gian làm việc": "work_time",
        "Cách thức ứng tuyển": "application_method",
    }

    # Map label sidebar → field name trong JobDetailItem
    SIDEBAR_MAP = {
        "Cấp bậc": "level",
        "Số lượng tuyển": "quantity",
        "Hình thức làm việc": "work_type",
        "Giới tính": "gender",
    }

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "COOKIES_ENABLED": True,

        # --- Throttling: chậm hơn để an toàn với 14k+ requests ---
        "DOWNLOAD_DELAY": 2.0,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,

        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2,
        "AUTOTHROTTLE_MAX_DELAY": 15,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,

        "DOWNLOAD_TIMEOUT": 30,

        # --- Retry: Scrapy built-in (cho lỗi server/timeout) ---
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [408, 500, 502, 503, 504, 522, 524],

        # --- Backoff retry: cho 403/429 (qua BackoffRetryMiddleware) ---
        "BACKOFF_RETRY_CODES": [403, 429],
        "BACKOFF_INITIAL_DELAY": 10,
        "BACKOFF_MAX_DELAY": 120,
        "BACKOFF_FACTOR": 2,
        "BACKOFF_MAX_RETRIES": 5,

        "ERRBACK_RETRY_TIMES": 3,

        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",

        # --- Downloader middlewares ---
        "DOWNLOADER_MIDDLEWARES": {
            # Tắt UA mặc định, dùng rotating middleware
            "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
            "jobcrawl.middlewares.RotatingUserAgentMiddleware": 400,
            # Backoff retry cho 403/429 (chạy trước retry mặc định)
            "jobcrawl.middlewares.BackoffRetryMiddleware": 550,
        },

        "DEFAULT_REQUEST_HEADERS": {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        },

        "FEED_EXPORT_ENCODING": "utf-8",
        "FEED_EXPORT_INDENT": 2,
        # FEEDS được set động trong from_crawler để đồng bộ với output_file

        "ITEM_PIPELINES": {
            "jobcrawl.pipelines.JobDetailCleanupPipeline": 300,
        },
    }

    def __init__(self, input_file=None, output_file=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.input_file = input_file or config.MERGED_LINKS
        self.output_file = output_file or config.JOB_DETAILS

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        # Set FEEDS động để luôn đồng bộ với output_file (dù mặc định hay truyền vào)
        crawler.settings.set("FEEDS", {
            spider.output_file: {
                "format": "json",
                "encoding": "utf-8",
                "overwrite": False,
            },
        }, priority="spider")
        return spider

    def _load_done_urls(self):
        """Đọc các link_job đã crawl từ output file để skip khi resume."""
        output_path = Path(self.output_file)
        if not output_path.exists():
            return set()
        try:
            with output_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            done = {item.get("link_job", "") for item in data if item.get("link_job")}
            self.logger.info("Resume: found %d already-crawled URLs in %s",
                             len(done), self.output_file)
            return done
        except (json.JSONDecodeError, KeyError):
            return set()

    def start_requests(self):
        input_path = Path(self.input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file input: {self.input_file}")

        with input_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        done_urls = self._load_done_urls()
        total = len(data)
        skipped = 0

        for entry in data:
            link = (entry.get("link_job") or "").strip()
            if not link:
                continue
            if link in done_urls:
                skipped += 1
                continue
            yield scrapy.Request(
                url=link,
                callback=self.parse_detail,
                errback=self.errback_log,
                dont_filter=True,
                headers=self.build_headers("https://www.topcv.vn/"),
                meta={
                    "xa_phuong": entry.get("xa_phuong", []),
                    "loai_job": entry.get("loai_job", []),
                },
            )

        self.logger.info(
            "Total: %d | Skipped (already done): %d | To crawl: %d",
            total, skipped, total - skipped,
        )

    def parse_detail(self, response):
        item = JobDetailItem()

        # Metadata từ input
        item["link_job"] = response.url
        item["xa_phuong"] = response.meta.get("xa_phuong", [])
        item["loai_job"] = response.meta.get("loai_job", [])
        item["crawled_at"] = datetime.now(timezone.utc).isoformat()

        # Thông tin chính
        item["title"] = self._css_text(
            response, "h1.job-detail__info--title a::text"
        )
        item["salary"] = self._css_text(
            response, ".section-salary .job-detail__info--section-content-value::text"
        )
        item["location"] = self._css_text_all(
            response,
            ".section-location .job-detail__info--section-content-value *::text",
        )
        item["experience"] = self._css_text(
            response,
            "#job-detail-info-experience .job-detail__info--section-content-value::text",
        )
        item["deadline"] = self._css_text(
            response, ".job-detail__info--deadline-date::text"
        )

        # Mô tả chi tiết (match theo header h3)
        self._extract_sections(response, item)

        # Thông tin công ty
        self._extract_company_info(response, item)

        # Sidebar (Thông tin chung)
        self._extract_sidebar_info(response, item)

        self.logger.info("Parsed: %s", item.get("title") or response.url)
        yield item

    def _extract_sections(self, response, item):
        """Trích xuất các section mô tả bằng cách match h3 header text."""
        sections = response.css(
            ".job-detail__information-detail .job-description__item"
        )
        found = set()
        for section in sections:
            header = (section.css("h3::text").get() or "").strip()
            field_name = self.SECTION_MAP.get(header)
            if not field_name:
                continue
            parts = section.css(
                ".job-description__item--content *::text"
            ).getall()
            content = "\n".join(p.strip() for p in parts if p.strip())
            item[field_name] = content or None
            found.add(field_name)

        # Đảm bảo tất cả field đều tồn tại
        for field_name in self.SECTION_MAP.values():
            if field_name not in found:
                item[field_name] = None

    def _extract_company_info(self, response, item):
        """Trích xuất thông tin công ty."""
        company_block = response.css(".job-detail__company--information")

        item["company_name"] = self._css_text(
            company_block, ".company-name-label a::text"
        )

        # Các row thông tin công ty: Quy mô, Lĩnh vực, Địa chỉ
        company_items = company_block.css(
            ".job-detail__company--information-item"
        )
        company_data = {}
        for row in company_items:
            label_parts = row.css(".company-title::text").getall()
            label = " ".join(p.strip() for p in label_parts if p.strip())
            # Bỏ dấu ":" ở cuối label
            label = label.rstrip(":").strip()
            value = (row.css(".company-value::text").get() or "").strip()
            if label and value:
                company_data[label] = value

        item["company_size"] = company_data.get("Quy mô")
        item["company_field"] = company_data.get("Lĩnh vực")
        item["company_address"] = company_data.get("Địa điểm") or company_data.get("Địa chỉ")

    def _extract_sidebar_info(self, response, item):
        """Trích xuất thông tin sidebar (Cấp bậc, Số lượng tuyển, ...)."""
        groups = response.css(".box-general-group")
        sidebar_data = {}
        for group in groups:
            label = (
                group.css(".box-general-group-info-title::text").get() or ""
            ).strip()
            value = (
                group.css(".box-general-group-info-value::text").get() or ""
            ).strip()
            if label and value:
                sidebar_data[label] = value

        for label, field_name in self.SIDEBAR_MAP.items():
            item[field_name] = sidebar_data.get(label)

    # --- Retry / Error handling (reuse pattern từ spider hiện tại) ---

    def errback_log(self, failure):
        request = failure.request
        reason = self.get_failure_reason(failure)
        self.logger.warning("Request failed: %s | reason=%s", request.url, reason)

        retry_req = self.retry_request(
            request=request,
            reason=reason,
            retry_key="errback_retry_times",
            max_retry_setting="ERRBACK_RETRY_TIMES",
        )
        if retry_req:
            yield retry_req
            return

        self.logger.warning("Give up request: %s | reason=%s", request.url, reason)

    def retry_request(self, request, reason, retry_key, max_retry_setting):
        retry_times = request.meta.get(retry_key, 0)
        max_retries = self.settings.getint(max_retry_setting, 0)

        if retry_times >= max_retries:
            return None

        new_meta = dict(request.meta)
        new_meta[retry_key] = retry_times + 1
        new_meta["last_retry_reason"] = str(reason)
        new_meta["dont_cache"] = True

        new_request = request.replace(
            meta=new_meta,
            dont_filter=True,
            priority=request.priority + 10,
        )

        self.logger.warning(
            "Retrying %s (%s/%s) | reason=%s",
            request.url,
            retry_times + 1,
            max_retries,
            reason,
        )

        return new_request

    def get_failure_reason(self, failure):
        if failure.check(HttpError):
            response = failure.value.response
            return f"http_{response.status}"
        return failure.getErrorMessage() or failure.type.__name__

    @staticmethod
    def build_headers(referer=None):
        return {
            "Referer": referer or "https://www.topcv.vn/",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }

    @staticmethod
    def _css_text(selector, css_query):
        """Trích xuất text từ CSS selector, trả về None nếu không tìm thấy."""
        value = (selector.css(css_query).get() or "").strip()
        return value or None

    @staticmethod
    def _css_text_all(selector, css_query, separator=", "):
        """Trích xuất và nối tất cả text từ CSS selector."""
        parts = selector.css(css_query).getall()
        # Lọc bỏ các phần chỉ chứa dấu câu/khoảng trắng
        cleaned = [p.strip() for p in parts if p.strip().strip(",").strip()]
        joined = separator.join(cleaned)
        return joined or None

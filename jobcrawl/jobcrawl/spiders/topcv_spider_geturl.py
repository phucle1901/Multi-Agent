import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import scrapy
from scrapy.spidermiddlewares.httperror import HttpError

from jobcrawl import config


class TopcvJobLinksSpider(scrapy.Spider):
    name = "topcv_spider_geturl"
    allowed_domains = ["topcv.vn"]

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "COOKIES_ENABLED": True,

        "DOWNLOAD_DELAY": 2.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,

        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2,
        "AUTOTHROTTLE_MAX_DELAY": 30,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,

        "DOWNLOAD_TIMEOUT": 30,

        # built-in retry của Scrapy (chỉ giữ cho timeout/5xx; 403/429 do Backoff xử)
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 2,
        "RETRY_HTTP_CODES": [408, 500, 502, 503, 504, 522, 524],

        # Backoff retry cho 403/429 (qua BackoffRetryMiddleware)
        "BACKOFF_RETRY_CODES": [403, 429],
        "BACKOFF_INITIAL_DELAY": 10,
        "BACKOFF_MAX_DELAY": 120,
        "BACKOFF_FACTOR": 2,
        "BACKOFF_MAX_RETRIES": 5,


        # retry custom trong errback / page rỗng
        "ERRBACK_RETRY_TIMES": 2,
        "EMPTY_PAGE_RETRY_TIMES": 1,

        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",

        "DOWNLOADER_MIDDLEWARES": {
            "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
            "jobcrawl.middlewares.RotatingUserAgentMiddleware": 400,
            "jobcrawl.middlewares.BackoffRetryMiddleware": 550,
        },
        
        "USER_AGENT": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),

        "DEFAULT_REQUEST_HEADERS": {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="134", "Google Chrome";v="134"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },


        "FEED_EXPORT_ENCODING": "utf-8",
        "FEED_EXPORT_INDENT": 2,
    }

    def __init__(self, input_file=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.input_file = input_file or config.URL_INPUT

    def start_requests(self):
        input_path = Path(self.input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file input: {self.input_file}")

        with input_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for group in data:
            group_name = (group.get("name") or "").strip()

            for row in group.get("urls", []):
                seed_url = (row.get("url") or "").strip()
                if not seed_url:
                    continue

                xa_phuong = (row.get("xa_phuong") or group_name or "").strip()
                loai_job = (row.get("loai_job") or "").strip()

                yield scrapy.Request(
                    url=seed_url,
                    callback=self.parse,
                    errback=self.errback_log,
                    dont_filter=True,
                    headers=self.build_headers("https://www.topcv.vn/"),
                    meta={
                        "xa_phuong": xa_phuong,
                        "loai_job": loai_job,
                        "seed_url": seed_url,
                    },
                )

    def parse(self, response):
        current_page = self.extract_page_no(response.url)

        raw_job_links = response.css(
            "div.job-item-search-result h3.title a::attr(href), "
            "div.job-item-search-result div.avatar a::attr(href)"
        ).getall()

        job_links = set()
        for href in raw_job_links:
            if not href or not self.is_job_detail_url(href):
                continue

            job_url = self.normalize_job_url(response.urljoin(href))
            job_links.add(job_url)

        self.logger.info(
            "Page %s | found %s jobs | %s",
            current_page,
            len(job_links),
            response.url,
        )

        # page 200 nhưng rỗng -> retry thêm 1 lần
        if not job_links:
            retry_req = self.retry_request(
                request=response.request,
                reason="empty_page",
                retry_key="empty_page_retry_times",
                max_retry_setting="EMPTY_PAGE_RETRY_TIMES",
            )
            if retry_req:
                yield retry_req
                return

            self.logger.info("Stop on empty page | page=%s | %s", current_page, response.url)
            return

        for job_url in job_links:
            yield {
                "link_job": job_url,
                "xa_phuong": response.meta.get("xa_phuong", ""),
                "loai_job": response.meta.get("loai_job", ""),
                "page": current_page,
            }

        if current_page == 1:
            max_page = self.extract_max_page(response)
            self.logger.info("Total pages: %s | %s", max_page, response.url)
            seed_url = response.meta.get("seed_url", response.url)
            for page_no in range(2, max_page + 1):
                yield scrapy.Request(
                    url=self.build_page_url(seed_url, page_no),
                    callback=self.parse,
                    errback=self.errback_log,
                    dont_filter=True,
                    headers=self.build_headers(response.url),
                    meta={
                        "xa_phuong": response.meta.get("xa_phuong", ""),
                        "loai_job": response.meta.get("loai_job", ""),
                        "seed_url": seed_url,
                    },
                )

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
    def extract_max_page(response) -> int:
        """Đọc tổng số trang từ #job-listing-paginate-text.
        HTML dạng: <span>1&nbsp;/&nbsp;159 trang</span>
        """
        text = "".join(
            response.xpath('//*[@id="job-listing-paginate-text"]//text()').getall()
        )
        m = re.search(r'/\D*(\d+)\s*trang', text)
        if m:
            return int(m.group(1))
        return 1

    @staticmethod
    def build_page_url(base_url: str, page_no: int) -> str:
        """Tạo URL cho trang page_no từ seed URL."""
        parts = urlsplit(base_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["page"] = str(page_no)
        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, doseq=True),
            "",
        ))

    @staticmethod
    def extract_page_no(url: str) -> int:
        query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        try:
            return int(query.get("page", 1))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def is_job_detail_url(href: str) -> bool:
        # TopCV có 2 format job detail:
        #   /viec-lam/<slug>/<id>.html
        #   /brand/<brand>/tuyen-dung/<slug>-j<id>.html
        path = href.split("?", 1)[0].split("#", 1)[0]
        if not path.endswith(".html"):
            return False
        return "/viec-lam/" in path or "/tuyen-dung/" in path

    @staticmethod
    def normalize_job_url(url: str) -> str:
        parsed = urlsplit(url)

        drop_params = {
            "ta_source",
            "u_sr_id",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_id",
            "gclid",
            "fbclid",
        }

        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_query = [(k, v) for k, v in query_pairs if k not in drop_params]

        return urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(filtered_query, doseq=True),
            "",
        ))
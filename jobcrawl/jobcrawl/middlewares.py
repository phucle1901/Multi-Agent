import random
import time
import logging

from scrapy import signals

logger = logging.getLogger(__name__)


# Danh sách User-Agent thực tế (Chrome/Firefox trên Windows/Mac)
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
    # Firefox Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
]


class RotatingUserAgentMiddleware:
    """Xoay vòng User-Agent ngẫu nhiên cho mỗi request."""

    def process_request(self, request, spider):
        ua = random.choice(USER_AGENTS)
        request.headers["User-Agent"] = ua


class BackoffRetryMiddleware:
    """Retry với exponential backoff cho 403/429.

    Khi gặp 403 hoặc 429, middleware sẽ:
    1. Chờ (backoff) trước khi retry
    2. Tăng thời gian chờ theo cấp số nhân
    3. Giới hạn số lần retry tối đa

    Config qua custom_settings:
        BACKOFF_RETRY_CODES: list[int] — HTTP codes cần backoff (default: [403, 429])
        BACKOFF_INITIAL_DELAY: float — delay ban đầu tính bằng giây (default: 10)
        BACKOFF_MAX_DELAY: float — delay tối đa (default: 120)
        BACKOFF_FACTOR: float — hệ số nhân delay (default: 2)
        BACKOFF_MAX_RETRIES: int — số lần retry tối đa (default: 5)
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.retry_codes = set(
            settings.getlist("BACKOFF_RETRY_CODES", [403, 429])
        )
        self.initial_delay = settings.getfloat("BACKOFF_INITIAL_DELAY", 10)
        self.max_delay = settings.getfloat("BACKOFF_MAX_DELAY", 120)
        self.factor = settings.getfloat("BACKOFF_FACTOR", 2)
        self.max_retries = settings.getint("BACKOFF_MAX_RETRIES", 5)

    def process_response(self, request, response, spider):
        if response.status not in self.retry_codes:
            return response

        retries = request.meta.get("backoff_retries", 0)
        if retries >= self.max_retries:
            logger.warning(
                "Backoff give up: %s | status=%s | retries=%d",
                request.url, response.status, retries,
            )
            return response

        delay = min(
            self.initial_delay * (self.factor ** retries),
            self.max_delay,
        )
        # Thêm jitter ±30% để tránh thundering herd
        delay *= random.uniform(0.7, 1.3)

        logger.warning(
            "Backoff retry: %s | status=%s | retry=%d/%d | delay=%.1fs",
            request.url, response.status, retries + 1, self.max_retries, delay,
        )

        time.sleep(delay)

        new_meta = dict(request.meta)
        new_meta["backoff_retries"] = retries + 1

        return request.replace(
            meta=new_meta,
            dont_filter=True,
            priority=request.priority + 20,
        )


class JobcrawlSpiderMiddleware:

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        return None

    def process_spider_output(self, response, result, spider):
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class JobcrawlDownloaderMiddleware:

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        return None

    def process_response(self, request, response, spider):
        return response

    def process_exception(self, request, exception, spider):
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)

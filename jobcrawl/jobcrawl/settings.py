# Scrapy settings for jobcrawl project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import os
from pathlib import Path
from dotenv import load_dotenv

BOT_NAME = "jobcrawl"

SPIDER_MODULES = ["jobcrawl.spiders"]
NEWSPIDER_MODULE = "jobcrawl.spiders"
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "jobcrawl (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Concurrency and throttling settings
#CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "jobcrawl.middlewares.JobcrawlSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "jobcrawl.middlewares.JobcrawlDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "jobcrawl.pipelines.JobcrawlPipeline": 300,
#}

# HTTP cache backed by Redis
HTTPCACHE_ENABLED = True
HTTPCACHE_STORAGE = "jobcrawl.cache.RedisCacheStorage"
HTTPCACHE_POLICY = "scrapy.extensions.httpcache.DummyPolicy"
HTTPCACHE_EXPIRATION_SECS = 7 * 24 * 3600  # 7 ngày
HTTPCACHE_IGNORE_HTTP_CODES = [
    301, 302, 307, 308,
    400, 401, 403, 404, 408, 429,
    500, 502, 503, 504, 522, 524,
]
HTTPCACHE_IGNORE_SCHEMES = ["file"]
HTTPCACHE_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"

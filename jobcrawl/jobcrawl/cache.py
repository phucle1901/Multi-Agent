import gzip
import hashlib
import zlib

import redis
from scrapy.http import HtmlResponse


def make_key(url: str) -> str:
    return "jobcrawl:cache:" + hashlib.md5(url.encode()).hexdigest()


def _decompress(body: bytes, content_encoding: bytes) -> bytes:
    """Giải nén body nếu Content-Encoding là gzip/deflate/br. Trả nguyên bytes nếu không nén."""
    if not content_encoding:
        return body
    enc = content_encoding.lower()
    if b"gzip" in enc:
        return gzip.decompress(body)
    if b"deflate" in enc:
        return zlib.decompress(body)
    if b"br" in enc:
        import brotli  # cần `pip install brotli` nếu TopCV trả về brotli
        return brotli.decompress(body)
    return body


class RedisCacheStorage:
    def __init__(self, settings):
        self.url = settings.get("HTTPCACHE_REDIS_URL")
        self.ttl = settings.getint("HTTPCACHE_EXPIRATION_SECS")

    def open_spider(self, spider):
        self.db = redis.from_url(self.url)

    def close_spider(self, spider):
        self.db.close()

    def retrieve_response(self, spider, request):
        body = self.db.get(make_key(request.url))
        if body is None:
            return None
        # Body đã được giải nén lúc store → trả thẳng, không Content-Encoding header
        return HtmlResponse(url=request.url, body=body, encoding="utf-8")

    def store_response(self, spider, request, response):
        ce = response.headers.get(b"Content-Encoding", b"")
        body = _decompress(response.body, ce)
        self.db.set(make_key(request.url), body, ex=self.ttl)

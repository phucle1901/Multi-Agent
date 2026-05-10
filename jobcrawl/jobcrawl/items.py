import scrapy


class JobcrawlItem(scrapy.Item):
    pass


class JobDetailItem(scrapy.Item):
    # Metadata (từ merged_links.json)
    link_job = scrapy.Field()
    xa_phuong = scrapy.Field()       # list[str]
    loai_job = scrapy.Field()        # list[str]

    # Thông tin chính
    title = scrapy.Field()
    salary = scrapy.Field()
    location = scrapy.Field()
    experience = scrapy.Field()
    deadline = scrapy.Field()

    # Mô tả chi tiết
    job_description = scrapy.Field()
    requirements = scrapy.Field()
    benefits = scrapy.Field()
    work_location = scrapy.Field()
    work_time = scrapy.Field()
    application_method = scrapy.Field()

    # Thông tin công ty
    company_name = scrapy.Field()
    company_size = scrapy.Field()
    company_field = scrapy.Field()
    company_address = scrapy.Field()

    # Thông tin bổ sung
    quantity = scrapy.Field()
    work_type = scrapy.Field()
    level = scrapy.Field()
    gender = scrapy.Field()

    # Metadata crawl
    crawled_at = scrapy.Field()

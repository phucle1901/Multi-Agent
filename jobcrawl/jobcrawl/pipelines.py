from itemadapter import ItemAdapter


class JobcrawlPipeline:
    def process_item(self, item, spider):
        return item


class JobDetailCleanupPipeline:
    """Strip whitespace và chuẩn hóa empty values cho JobDetailItem."""

    def process_item(self, item, spider):
        if spider.name != "topcv_spider_detail":
            return item

        adapter = ItemAdapter(item)
        for field_name in adapter.field_names():
            value = adapter.get(field_name)
            if isinstance(value, str):
                cleaned = value.strip()
                adapter[field_name] = cleaned if cleaned else None
        return item

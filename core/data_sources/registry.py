"""数据源注册表——按数据类型管理主/备源"""


class _DataSourceRegistry:
    """单例注册表"""
    
    def __init__(self):
        self._categories = {
            "stock_daily": {
                "primary": "baostock",
                "fallback": "tencent",
                "description": "日K线",
            },
            "realtime": {
                "primary": "tencent",
                "fallback": "sina",
                "description": "实时行情",
            },
            "financial": {
                "primary": "akshare",
                "fallback": None,
                "description": "财务数据",
            },
            "sectors": {
                "primary": "akshare",
                "fallback": "sina",
                "description": "板块数据",
            },
            "sentiment": {
                "primary": "sina_news",
                "fallback": None,
                "description": "情绪数据",
            },
        }
    
    def get_primary(self, category):
        cat = self._categories.get(category)
        return cat['primary'] if cat else None
    
    def get_fallback(self, category):
        cat = self._categories.get(category)
        return cat.get('fallback') if cat else None
    
    def switch_primary(self, category, source_name):
        if category in self._categories:
            self._categories[category]['primary'] = source_name
    
    def list_categories(self):
        result = {}
        for name, cfg in self._categories.items():
            result[name] = {
                'primary': cfg['primary'],
                'fallback': cfg.get('fallback'),
                'description': cfg['description'],
            }
        return result
    
    def register_source(self, category, source_name, source_obj):
        if category not in self._categories:
            self._categories[category] = {
                "primary": source_name,
                "fallback": None,
                "description": "",
            }
        if 'sources' not in self._categories[category]:
            self._categories[category]['sources'] = {}
        self._categories[category]['sources'][source_name] = source_obj


# 全局单例
registry = _DataSourceRegistry()


def get_registry():
    return registry


def list_sources():
    return registry.list_categories()


def switch_source(category, source_name):
    registry.switch_primary(category, source_name)
    return {"status": "ok", "category": category, "primary": source_name}

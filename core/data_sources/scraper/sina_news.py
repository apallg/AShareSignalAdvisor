"""新浪个股新闻爬虫适配器"""
from .base_scraper import BaseScraper


def _prefix(code):
    """600xxx → sh600519, 000xxx → sz000001, 300xxx → sz300001"""
    if code.startswith(("6", "5")):
        return "sh" + code
    return "sz" + code


class SinaNewsScraper(BaseScraper):
    """新浪财经个股新闻"""
    
    def get_news(self, code: str, pages: int = 2) -> list:
        """获取个股新闻列表"""
        items = []
        prefix = _prefix(code)
        url = ("https://vip.stock.finance.sina.com.cn/corp/go.php/"
               f"vCB_AllNewsStock/symbol/{prefix}.phtml")
        try:
            resp = self._request(url)
            resp.encoding = "gbk"
            html = resp.text
            items = self._parse_news(html)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"SinaNews({code}) 失败: {e}")
        return items
    
    def _parse_news(self, html: str) -> list:
        """解析新浪个股新闻 HTML"""
        import re
        items = []
        # 查找新闻表格行
        pattern = r'<tr>.*?(\d{4}-\d{2}-\d{2}).*?<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>'
        for m in re.finditer(pattern, html):
            try:
                title = m.group(3).strip()
                title = re.sub(r'<[^>]+>', '', title)
                if title and len(title) > 4:
                    items.append({
                        "title": title,
                        "url": m.group(2).strip(),
                        "date": m.group(1),
                    })
            except Exception:
                continue
        return items
    
    def batch_get(self, codes: list, pages: int = 1) -> dict:
        """批量获取多只股票的新闻"""
        result = {}
        for code in codes:
            result[code] = self.get_news(code, pages)
        return result
    
    def name(self) -> str:
        return "新浪财经个股新闻"

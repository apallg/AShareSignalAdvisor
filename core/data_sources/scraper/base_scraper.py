"""爬虫基类——统一处理反爬策略"""
import time
import random
import requests


class BaseScraper:
    """爬虫基类，统一处理 User-Agent、频率控制、重试"""
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    ]
    
    def __init__(self, min_interval=2.0):
        self.session = requests.Session()
        self.last_request = 0.0
        self.min_interval = min_interval
    
    def _request(self, url, headers=None, **kwargs):
        """带频率控制和反爬的请求"""
        elapsed = time.time() - self.last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed + random.uniform(0, 0.5))
        
        h = headers or {}
        h.setdefault("User-Agent", random.choice(self.USER_AGENTS))
        h.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        h.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        
        self.last_request = time.time()
        return self.session.get(url, headers=h, timeout=15, **kwargs)

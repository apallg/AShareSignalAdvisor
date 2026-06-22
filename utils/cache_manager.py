"""
缓存管理 - 基于 diskcache 的文件级缓存
"""
import hashlib
from pathlib import Path
from typing import Any, Callable, Optional
import diskcache as dc
import config


class CacheManager:
    """文件级缓存，避免重复的 API 和数据请求"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self._cache = dc.Cache(str(cache_dir or config.CACHE_DIR))
        self._cleanup_skip = 0

    def get(self, key: str) -> Any:
        return self._cache.get(key)

    def set(self, key: str, value: Any, expire: int = 3600):
        self._cache.set(key, value, expire=expire)

    def get_or_set(self, key: str, func: Callable, expire: int = 3600) -> Any:
        """缓存命中则返回，否则调用 func 并缓存"""
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = func()
        self._cache.set(key, result, expire=expire)
        return result

    def get_with_fallback(self, key, func, expire=3600):
        """获取数据：先查缓存 → 再调func → 失败则回退到MySQL"""
        # 1. 查本地缓存（最快）
        result = self.get(key)
        if result is not None:
            return result
        # 2. 调用 func() 获取新数据
        from datetime import datetime, timedelta
        try:
            result = func()
            self.set(key, result, expire=expire)
            # 异步保存到 MySQL
            if config.MYSQL_ENABLED:
                try:
                    from core.database import DataCacheRepo
                    from core.database import DailyQuotesRepo
                    expires_at = datetime.now() + timedelta(seconds=expire)
                    DataCacheRepo.save(key, result, expires_at)
                    self._cleanup_skip += 1
                    if self._cleanup_skip >= 50:
                        DataCacheRepo.cleanup_old(3)
                        DailyQuotesRepo.cleanup_old(3)
                        self._cleanup_skip = 0
                except Exception:
                    pass
            return result
        except Exception:
            pass
        # 3. func() 失败 → 回退到 MySQL
        if config.MYSQL_ENABLED:
            try:
                from core.database import DataCacheRepo
                stale = DataCacheRepo.get(key)
                if stale is not None:
                    return stale
            except Exception:
                pass
        raise  # 完全无数据

    def remove(self, key: str):
        self._cache.pop(key, None)

    def close(self):
        self._cache.close()

    @staticmethod
    def make_key(prefix: str, *args) -> str:
        """生成确定性缓存键"""
        raw = f"{prefix}:" + ":".join(str(a) for a in args)
        return hashlib.md5(raw.encode()).hexdigest()

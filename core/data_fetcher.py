
"""A股行情/财务/资金数据获取"""
import time
from datetime import datetime, timedelta
import pandas as pd
import akshare as ak
import requests
import json
from utils.cache_manager import CacheManager
import config
import logging
logger = logging.getLogger(__name__)

def _retry(func, ma=3, dl=3):
    """重试装饰器"""
    last = None
    for a in range(ma):
        try:
            return func()
        except Exception as e:
            last = e
            if a < ma - 1:
                time.sleep(dl)
    raise last

class DataFetcher:
    _spot_cache = None
    _spot_cache_time = 0

    def __init__(self, cache=None):
        self.cache = cache or CacheManager()
        self._save_count = 0
        self._ds = {}  # 数据源追踪
        self._miniqmt_source = None

    def _mark_source(self, key, source):
        self._ds[key] = source

    def get_sources(self):
        """获取本次请求各数据来源"""
        return dict(self._ds)

    @property
    def _qmt(self):
        """懒加载 MiniQmtSource"""
        if self._miniqmt_source is None:
            try:
                from core.data_sources.miniqmt_source import MiniQmtSource
                self._miniqmt_source = MiniQmtSource()
            except Exception:
                self._miniqmt_source = False
        return self._miniqmt_source if self._miniqmt_source else None

    def _persist(self, key, data, expire=3600):
        """持久化数据到 MySQL，带批量清理"""
        if not config.MYSQL_ENABLED:
            return
        try:
            from core.database import DataCacheRepo, DailyQuotesRepo
            expires_at = datetime.now() + timedelta(seconds=expire)
            DataCacheRepo.save(key, data, expires_at)
            self._save_count += 1
            if self._save_count >= 30:
                DataCacheRepo.cleanup_old(3)
                self._save_count = 0
        except Exception as e:
            logger.warning(f"MySQL持久化失败: {e}")

    def _get_with_fallback(self, key, func, expire=3600, default=None):
        """缓存->API->MySQL 三级回退"""
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            result = func()
            self.cache.set(key, result, expire=expire)
            self._persist(key, result, expire)
            return result
        except Exception as e:
            logger.debug(f"主数据源获取失败({key[:40]}): {e}")

        if config.MYSQL_ENABLED:
            try:
                from core.database import DataCacheRepo
                stale = DataCacheRepo.get(key)
                if stale is not None:
                    logger.info(f"MySQL回退命中: {key[:40]}")
                    return stale
            except Exception as e:
                logger.debug(f"MySQL回退失败({key[:40]}): {e}")

        raise Exception("所有数据源不可用")

    
    def _tencent_daily_raw(self, code, start_date, end_date, adj="qfq"):
        """??IFZQ HTTP API ?????????????"""
        url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,640,{adj}"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                return None
            d = data.get("data", {})
            code_key = code
            if code_key not in d:
                for k in d:
                    code_key = k
                    break
            klines = d.get(code_key, {}).get("qfqday") or d.get(code_key, {}).get("day") or d.get(code_key, {}).get("qfq")
            if not klines:
                return None
            import pandas as pd
            rows = []
            for k in klines:
                try:
                    date_str = str(k[0])
                    if len(date_str) >= 10 and date_str >= start_date and date_str <= end_date:
                        rows.append({
                            "date": date_str, "open": float(k[1]), "close": float(k[2]),
                            "high": float(k[3]), "low": float(k[4]), "volume": float(k[5]),
                        })
                except (IndexError, ValueError):
                    continue
            if not rows:
                return None
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            df["amplitude"] = df["pct_chg"] = df["turnover"] = 0
            return df
        except Exception as e:
            logger.warning(f"Tencent daily raw({code}) ??: {e}")
            return None
    def _tencent_daily(self, symbol, start_date, end_date, adjust="qfq"):
        """通过腾讯 IFZQ HTTP API 获取日K线（HTTP协议，不被安全软件拦截）"""
        mkt = "sh" if symbol.startswith(("6", "5")) else "sz"
        adj = "qfq" if adjust == "qfq" else ("hfq" if adjust == "hfq" else "")
        url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={mkt}{symbol},day,,,640,{adj}"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                return None
            code_key = f"{mkt}{symbol}"
            day_data = data.get("data", {}).get(code_key, {})
            klines = day_data.get("qfqday") or day_data.get("day") or day_data.get("qfq")
            if not klines:
                return None
            import pandas as pd
            rows = []
            for k in klines:
                try:
                    date_str = str(k[0])
                    if len(date_str) >= 10 and date_str >= start_date[:10] and date_str <= end_date[:10]:
                        rows.append({
                            "date": date_str, "open": float(k[1]), "close": float(k[2]),
                            "high": float(k[3]), "low": float(k[4]), "volume": float(k[5]),
                        })
                except (IndexError, ValueError):
                    continue
            if rows:
                df = pd.DataFrame(rows)
                # Try to get amount column if available (some formats include it)
                try:
                    df["amount"] = [float(k[6]) if len(k) > 6 else 0 for k in klines if len(str(k[0])) >= 10 and str(k[0]) >= start_date[:10] and str(k[0]) <= end_date[:10]]
                except Exception:
                    df["amount"] = 0
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
                # Rename columns to match expected format
                df["amplitude"] = 0
                df["pct_chg"] = 0
                df["turnover"] = 0
                return df
        except Exception as e:
            logger.warning(f"Tencent daily({symbol}) 失败: {e}")
        return None

    def _tencent_stock_name(self, symbol):
        """通过腾讯HTTP实时行情获取股票名称"""
        mkt = "sh" if symbol.startswith(("6", "5")) else "sz"
        url = f"http://qt.gtimg.cn/q={mkt}{symbol}"
        try:
            resp = requests.get(url, timeout=5)
            resp.encoding = "gbk"
            fields = resp.text.split("~")
            if len(fields) >= 2:
                name = fields[1].strip()
                if name and name != "":
                    return name
        except Exception as e:
            logger.warning(f"Tencent stock name({symbol}) 失败: {e}")
        return None

    def _netease_daily(self, symbol, start_date, end_date):
        """通过网易163 HTTP接口获取日K线数据"""
        prefix = "0" if symbol.startswith(("6", "5")) else "1"
        url = f"http://quotes.money.163.com/service/chddata.html?code={prefix}{symbol}&start={start_date[:10]}&end={end_date[:10]}"
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = "gbk"
            lines = resp.text.strip().split("\r\n")
            if len(lines) < 2:
                return None
            import pandas as pd
            rows = []
            for line in lines[1:]:
                fields = line.split(",")
                if len(fields) >= 6:
                    try:
                        date_str = fields[0].replace("-", "")
                        if date_str >= start_date[:10].replace("-","") and date_str <= end_date[:10].replace("-",""):
                            rows.append({
                                "date": fields[0],
                                "open": float(fields[2]) if fields[2] else 0,
                                "high": float(fields[3]) if fields[3] else 0,
                                "close": float(fields[4]) if fields[4] else 0,
                                "low": float(fields[5]) if fields[5] else 0,
                                "volume": float(fields[6]) if len(fields) > 6 and fields[6] else 0,
                                "amount": float(fields[7]) if len(fields) > 7 and fields[7] else 0,
                            })
                    except (ValueError, IndexError):
                        continue
            if not rows:
                return None
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            df["amplitude"] = 0
            df["pct_chg"] = df["close"].pct_change().fillna(0) * 100
            df["turnover"] = 0
            return df
        except Exception as e:
            logger.warning(f"NetEase daily({symbol}) 失败: {e}")
            return None

    def get_stock_daily(self, symbol, start_date=None, end_date=None, adjust="qfq"):
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        # date formats
        sd_dash = start_date[:4] + "-" + start_date[4:6] + "-" + start_date[6:8] if len(start_date) >= 8 else start_date
        ed_dash = end_date[:4] + "-" + end_date[4:6] + "-" + end_date[6:8] if len(end_date) >= 8 else end_date
        ck = CacheManager.make_key("daily", symbol, start_date, end_date, adjust)

        # 0. Try miniQMT (如果可用)
        qmt = self._qmt
        if qmt:
            try:
                result = qmt.get_kline(symbol, "1d", sd_dash, ed_dash)
                if result is not None and not result.empty:
                    self._mark_source("stock_daily", "miniQMT(xtdata)")
                    self.cache.set(ck, result, expire=config.CACHE_EXPIRE_DATA)
                    self._persist(ck, result, config.CACHE_EXPIRE_DATA)
                    return result
            except Exception as e:
                logger.debug(f"miniQMT daily({symbol}) 未命中: {e}")

        # 1. Try Tencent HTTP API (不会被安全软件拦截)
        try:
            result = self._tencent_daily(symbol, sd_dash, ed_dash, adjust)
            if result is not None and not result.empty:
                self._mark_source("stock_daily", "腾讯IFZQ HTTP")
                self.cache.set(ck, result, expire=config.CACHE_EXPIRE_DATA)
                self._persist(ck, result, config.CACHE_EXPIRE_DATA)
                return result
        except Exception as e:
            logger.warning(f"Tencent daily({symbol}) 失败: {e}")

        # 1.5 Try NetEase 163 HTTP API
        try:
            result = self._netease_daily(symbol, sd_dash, ed_dash)
            if result is not None and not result.empty:
                self._mark_source("stock_daily", "网易163 HTTP")
                self.cache.set(ck, result, expire=config.CACHE_EXPIRE_DATA)
                self._persist(ck, result, config.CACHE_EXPIRE_DATA)
                return result
        except Exception as e:
            logger.warning(f"NetEase daily({symbol}) 失败: {e}")

        # 2. Try akshare (East Money - HTTPS, 可能被阻)
        try:
            result = self._fetch_akshare_daily(symbol, start_date, end_date, adjust)
            if result is not None and not result.empty:
                self._mark_source("stock_daily", "东方财富(akshare)")
                self.cache.set(ck, result, expire=config.CACHE_EXPIRE_DATA)
                self._persist(ck, result, config.CACHE_EXPIRE_DATA)
                return result
        except Exception as e:
            logger.warning(f"akshare daily({symbol}) 失败: {e}")
        try:
            result = self._fetch_baostock_daily(symbol, start_date, end_date, adjust)
            if result is not None and not result.empty:
                self._mark_source("stock_daily", "BaoStock")
                self.cache.set(ck, result, expire=config.CACHE_EXPIRE_DATA)
                self._persist(ck, result, config.CACHE_EXPIRE_DATA)
                return result
        except Exception as e:
            logger.warning(f"BaoStock daily({symbol}) 失败: {e}")
        if config.MYSQL_ENABLED:
            try:
                from core.database import DailyQuotesRepo
                stale = DailyQuotesRepo.get_range(symbol, start_date, end_date)
                if stale is not None and not stale.empty:
                    self._mark_source("stock_daily", "MySQL缓存")
                    logger.info(f"MySQL回退命中 daily: {symbol}")
                    return stale
            except Exception:
                pass

        raise Exception(f"所有数据源({symbol})均不可用")

    def _fetch_akshare_daily(self, symbol, start_date, end_date, adjust):
        """通过 akshare 获取日K（原始逻辑）"""
        ck = CacheManager.make_key("daily_ak", symbol, start_date, end_date, adjust)
        def _fetch():
            df = _retry(lambda: ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust=adjust))
            if df.empty:
                raise ValueError("stock no data")
            cm = {"\u65e5\u671f":"date","\u5f00\u76d8":"open","\u6536\u76d8":"close","\u6700\u9ad8":"high","\u6700\u4f4e":"low","\u6210\u4ea4\u91cf":"volume","\u6210\u4ea4\u989d":"amount","\u632f\u5e45":"amplitude","\u6da8\u8dcc\u5e45":"pct_chg","\u6da8\u8dcc\u989d":"change","\u6362\u624b\u7387":"turnover"}
            df = df.rename(columns=cm)
            df["date"] = pd.to_datetime(df["date"])
            return df.sort_values("date").reset_index(drop=True)
        try:
            return self._get_with_fallback(ck, _fetch, config.CACHE_EXPIRE_DATA)
        except Exception:
            raise Exception("akshare daily failed")

    def _fetch_baostock_daily(self, symbol, start_date, end_date, adjust):
        """通过 BaoStock 获取日K线"""
        # 将 YYYYMMDD 转为 YYYY-MM-DD
        def _fmt(d):
            if d and len(d) >= 8 and "-" not in d:
                return d[:4] + "-" + d[4:6] + "-" + d[6:8]
            return d
        sd = _fmt(start_date) if start_date else None
        ed = _fmt(end_date) if end_date else None
        try:
            import baostock as bs
            bs_code = "sh." + symbol if symbol.startswith(("6", "5")) else "sz." + symbol
            adj_flag = "2" if adjust == "qfq" else ("3" if adjust == "hfq" else "1")
            lg = bs.login()
            if lg.error_code != "0":
                logger.warning(f"BaoStock login failed: {lg.error_msg}")
                return None
            rs = bs.query_history_k_data_plus(
                bs_code,
                fields="date,open,high,low,close,volume,amount",
                start_date=sd, end_date=ed,
                frequency="d", adjustflag=adj_flag)
            if rs is None:
                logger.warning(f"BaoStock query({symbol}) 返回 None")
                return None
            if rs.error_code != "0":
                bs.logout()
                return None
            data = []
            while rs.next():
                row = rs.get_row_data()
                if row[0] and row[0] != "":
                    data.append(row)
            bs.logout()
            if not data:
                return None
            df = pd.DataFrame(data, columns=["date","open","high","low","close","volume","amount"])
            for col in ["open","high","low","close","volume","amount"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            df["amplitude"] = 0
            df["pct_chg"] = 0
            df["turnover"] = 0
            return df
        except Exception as e:
            logger.warning(f"BaoStock daily({symbol}) 失败: {e}")
            return None

    def get_stock_name(self, symbol):
        ck = CacheManager.make_key("name", symbol)
        # 1. Try Tencent HTTP (不会被拦截)
        try:
            name = self._tencent_stock_name(symbol)
            if name:
                self._mark_source("stock_name", "腾讯实时行情")
                self.cache.set(ck, name, expire=config.CACHE_EXPIRE_NAME)
                self._persist(ck, name, config.CACHE_EXPIRE_NAME)
                return name
        except Exception:
            pass
        # 2. Try akshare fallback
        try:
            return self._get_with_fallback(ck, lambda: self._fetch_name(symbol), config.CACHE_EXPIRE_NAME)
        except Exception:
            return symbol

    def _fetch_name(self, symbol):
        df = _retry(lambda: ak.stock_zh_a_spot_em(), ma=2, dl=2)
        match = df[df["\u4ee3\u7801"] == symbol]
        if not match.empty:
            return str(match.iloc[0]["\u540d\u79f0"])
        raise ValueError(f"\u80a1\u7968 {symbol} \u672a\u627e\u5230")
    _INDEX_MAP = {"\u4e0a\u8bc1\u6307\u6570":"sh000001","\u6df1\u8bc1\u6210\u6307":"sz399001","\u521b\u4e1a\u677f\u6307":"sz399006","\u79d1\u521b50":"sh000688"}

    def get_market_indices(self):
        ck = CacheManager.make_key("indices")

        # 1. Try miniQMT
        qmt = self._qmt
        if qmt:
            try:
                q = qmt.get_market_indices(list(self._INDEX_MAP.values()))
                if q:
                    rows = []
                    for name, symbol in self._INDEX_MAP.items():
                        info = q.get(symbol, {})
                        rows.append({
                            "名称": name,
                            "最新价": info.get("price", 0),
                            "涨跌幅": info.get("pct_chg", 0),
                        })
                    df = pd.DataFrame(rows)
                    if not df.empty:
                        self._mark_source("indices", "miniQMT(xtdata)")
                        self.cache.set(ck, df, expire=60)
                        self._persist(ck, df, 60)
                        return df
            except Exception as e:
                logger.debug(f"miniQMT index spot 未命中: {e}")

        # 2. Try akshare
        def _fetch():
            df = _retry(lambda: ak.stock_zh_index_spot_em(), ma=3, dl=3)
            return df[df["\u540d\u79f0"].isin(list(self._INDEX_MAP.keys()))].copy()
        try:
            return self._get_with_fallback(ck, _fetch, 300)
        except Exception as e:
            logger.warning(f"akshare index spot 失败: {e}")
            return pd.DataFrame()

    def get_index_daily(self, index_name, days=365):
        symbol = self._INDEX_MAP.get(index_name)
        if not symbol:
            raise ValueError("bad index")
        end = datetime.now()
        start = end - timedelta(days=days)
        ck = CacheManager.make_key("idx_daily", symbol, start.strftime("%Y%m%d"))
        sd = start.strftime("%Y-%m-%d")
        ed = end.strftime("%Y-%m-%d")

        # 1. Try Tencent IFZQ HTTP API
        try:
            result = self._tencent_daily_raw(symbol, sd, ed)
            if result is not None and not result.empty:
                self._mark_source("index_daily", "腾讯IFZQ HTTP")
                self.cache.set(ck, result, expire=config.CACHE_EXPIRE_DATA)
                self._persist(ck, result, config.CACHE_EXPIRE_DATA)
                return result
        except Exception as e:
            logger.warning(f"Tencent index daily({index_name}) 失败: {e}")

        # 2. Try akshare (East Money HTTPS)
        def _fetch():
            df = _retry(lambda: ak.stock_zh_index_daily_em(symbol=symbol), ma=3, dl=3)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            return df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
        try:
            return self._get_with_fallback(ck, _fetch, config.CACHE_EXPIRE_DATA)
        except Exception as e:

            return pd.DataFrame()

    def get_top_gainers(self, top_n=20):
        ck = CacheManager.make_key("top_gainers", str(top_n))
        def _fetch():
            df = _retry(lambda: ak.stock_zh_a_spot_em(), ma=3, dl=3)
            return df.nlargest(top_n, "\u6da8\u8dcc\u5e45")
        try:
            return self._get_with_fallback(ck, _fetch, 300)
        except Exception as e:

            return pd.DataFrame()

    def get_top_losers(self, top_n=20):
        ck = CacheManager.make_key("top_losers", str(top_n))
        def _fetch():
            df = _retry(lambda: ak.stock_zh_a_spot_em(), ma=3, dl=3)
            return df.nsmallest(top_n, "\u6da8\u8dcc\u5e45")
        try:
            return self._get_with_fallback(ck, _fetch, 300)
        except Exception as e:

            return pd.DataFrame()

    def get_sector_performance(self):
        ck = CacheManager.make_key("sectors")
        # 1. Try THS (同花顺) — 不走东方财富域名，不受代理影响
        try:
            result = self._ths_sectors()
            if result is not None and not result.empty:
                self.cache.set(ck, result, expire=600)
                self._persist(ck, result, 600)
                self._mark_source("sectors", "同花顺(THS)")
                return result
        except Exception as e:
            logger.warning(f"THS sectors 失败: {e}")

        # 2. Try akshare (EastMoney)
        def _fetch():
            return _retry(lambda: ak.stock_board_industry_name_em(), ma=2, dl=3)
        try:
            result = self._get_with_fallback(ck, _fetch, 600)
            if result is not None and not result.empty:
                self._mark_source("sectors", "东方财富(akshare)")
                return result
        except Exception as e:
            logger.warning(f"akshare sectors 失败: {e}")

        # 3. Try Sina HTTP (legacy, may be broken)
        try:
            result = self._sina_sectors()
            if result is not None and not result.empty:
                self.cache.set(ck, result, expire=600)
                self._persist(ck, result, 600)
                self._mark_source("sectors", "新浪板块排行 HTTP")
                return result
        except Exception as e:
            logger.warning(f"Sina sectors 失败: {e}")

        raise Exception("板块数据: 所有数据源均不可用")

    def _ths_sectors(self):
        """通过同花顺 akshare 接口获取板块涨跌排行"""
        df = _retry(lambda: ak.stock_board_industry_summary_ths(), ma=2, dl=3)
        if df is None or df.empty:
            return None
        # 列名: 序号, 板块名称, 涨跌幅, 总成交量, 总成交额, ...
        # 映射为统一格式供前端使用
        df = df.rename(columns={
            df.columns[1]: "板块名称",
            df.columns[2]: "涨跌幅",
        })
        df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
        return df[["板块名称", "涨跌幅"]]

    def _sina_sectors(self):
        import re
        import requests
        url = "http://vip.stock.finance.sina.com.cn/q/go.php/vIndustryRank/kind/sshy/p/1/num/50/sort/changepercent/"
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = "gbk"
            if not resp.text or len(resp.text) < 100:
                logger.warning(f"Sina sectors 响应内容过短: {resp.text[:200]}")
                return None
            matches = re.findall(r'<a[^>]*>(\w+)</a>.*?<td[^>]*>(-?\d+\.\d+)%</td>', resp.text, re.DOTALL)
            if not matches:
                logger.warning(f"Sina sectors 正则未匹配，响应前500字符: {resp.text[:500]}")
                return None
            import pandas as pd
            df = pd.DataFrame(matches, columns=["板块名称", "涨跌幅"])
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
            return df
        except Exception as e:
            logger.warning(f"_sina_sectors 失败: {e}")
            return None

    def get_stock_financial(self, symbol):
        ck = CacheManager.make_key("fin2", symbol)
        try:
            return self._get_with_fallback(ck, lambda: self._fetch_financial(symbol), config.CACHE_EXPIRE_FINANCIAL)
        except Exception as e:
            logger.warning(f"get_stock_financial({symbol}) 失败: {e}")
            return {}


    def _fetch_financial(self, symbol):
        df = _retry(lambda: ak.stock_financial_abstract(symbol=symbol), ma=2, dl=2)
        if df is None or df.empty:
            raise ValueError("无财务数据")
        if len(df.columns) < 3:
            raise ValueError("财务数据列不足")
        latest_col = df.columns[2]  # 最新报告期
        indicator_col = df.columns[1]  # 指标列名

        # 模糊匹配：指标名称可能因 akshare 版本不同而有细微差异
        def _find_val(*keywords):
            mask = pd.Series(True, index=df.index)
            for kw in keywords:
                mask &= df[indicator_col].astype(str).str.contains(kw, na=False)
            row = df[mask]
            if not row.empty:
                val = row.iloc[0][latest_col]
                return val if pd.notna(val) else ""
            return ""

        return {
            "每股收益": _find_val("基本每股收益"),
            "净资产收益率": _find_val("净资产收益率", "ROE"),
            "每股净资产": _find_val("每股净资产"),
            "营业收入增长率": _find_val("营业总", "收入", "增长"),
            "净利润增长率": _find_val("归属", "净利润", "增长"),
            "资产负债率": _find_val("资产负债率"),
        }
    def get_capital_flow(self, symbol):
        ck = CacheManager.make_key("flow", symbol)
        def _fetch():
            mkt = "sh" if symbol.startswith("6") else "sz" if symbol.startswith(("0","3")) else ""
            if not mkt:
                raise ValueError("未知市场")
            return _retry(lambda: ak.stock_individual_fund_flow(stock=symbol, market=mkt), ma=2, dl=2)
        try:
            return self._get_with_fallback(ck, _fetch, config.CACHE_EXPIRE_DATA)
        except Exception as e:
            logger.warning(f"get_capital_flow({symbol}) 失败: {e}")
            return {}


    def get_realtime_quote(self, symbol):
        ck = CacheManager.make_key("quote", symbol)
        try:
            return self._get_with_fallback(ck, lambda: self._fetch_realtime(symbol), 120)
        except Exception as e:
            logger.warning(f"get_realtime_quote({symbol}) 失败: {e}")
            return {}

    def _fetch_realtime(self, symbol):
        # 0. 先试 miniQMT
        qmt = self._qmt
        if qmt:
            try:
                quotes = qmt.get_quotes([symbol])
                if symbol in quotes:
                    q = quotes[symbol]
                    return {
                        "名称": q.get("name", ""),
                        "最新价": q.get("price", 0),
                        "涨跌幅": q.get("pct_chg", 0),
                        "涨跌额": q.get("change", 0),
                        "成交量": q.get("volume", 0),
                        "成交额": q.get("amount", 0),
                        "市盈率-动态": "",
                        "市净率": "",
                    }
            except Exception as e:
                logger.debug(f"miniQMT 实时行情({symbol}) 未命中: {e}")

        # 1. 回退 akshare (缓存全市场快照 30 秒)
        now = time.time()
        if DataFetcher._spot_cache is None or now - DataFetcher._spot_cache_time > 30:
            DataFetcher._spot_cache = _retry(lambda: ak.stock_zh_a_spot_em(), ma=3, dl=2)
            DataFetcher._spot_cache_time = now
        df = DataFetcher._spot_cache
        match = df[df["\u4ee3\u7801"] == symbol]
        if match.empty:
            raise ValueError(f"{symbol} 实时数据不存在")
        row = match.iloc[0]
        return {"\u540d\u79f0":row.get("\u540d\u79f0"),"\u6700\u65b0\u4ef7":row.get("\u6700\u65b0\u4ef7"),"\u6da8\u8dcc\u5e45":row.get("\u6da8\u8dcc\u5e45"),"\u6da8\u8dcc\u989d":row.get("\u6da8\u8dcc\u989d"),"\u6210\u4ea4\u91cf":row.get("\u6210\u4ea4\u91cf"),"\u6210\u4ea4\u989d":row.get("\u6210\u4ea4\u989d"),"\u5e02\u76c8\u7387":row.get("\u5e02\u76c8\u7387-\u52a8\u6001"),"\u5e02\u51c0\u7387":row.get("\u5e02\u51c0\u7387")}

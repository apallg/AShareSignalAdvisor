"""
MiniQmtSource — 迅投 miniQMT 实时行情数据源。
封装 xtquant.xtdata，实现 BaseRealtimeSource 接口。
需要：miniQMT 已启动、xtquant 已安装。
"""
import logging
from typing import List, Dict, Any
from core.data_sources.base import BaseRealtimeSource

logger = logging.getLogger(__name__)


class MiniQmtSource(BaseRealtimeSource):
    def __init__(self):
        self._xtdata = None

    @property
    def name(self):
        return "miniqmt"

    @staticmethod
    def to_xtcode(symbol):
        """000001 → 000001.SZ, 600519 → 600519.SH"""
        symbol = str(symbol).zfill(6)
        if symbol.startswith(("6", "5")):
            return f"{symbol}.SH"
        elif symbol.startswith(("0", "3", "2")):
            return f"{symbol}.SZ"
        return symbol

    def _ensure_connected(self):
        if self._xtdata is None:
            try:
                from xtquant import xtdata
                self._xtdata = xtdata
            except ImportError:
                raise RuntimeError(
                    "xtquant 未安装，请从 QMT 安装目录安装：\n"
                    "pip install {QMT_DIR}/bin.x64/xtquant-*.whl"
                )
        return self._xtdata

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取实时行情"""
        xtdata = self._ensure_connected()
        result = {}

        try:
            normalized = [self.to_xtcode(s) for s in symbols]

            # get_full_tick 需要传列表，返回 dict
            ticks = xtdata.get_full_tick(normalized)
            if ticks and isinstance(ticks, str):
                import json
                ticks = json.loads(ticks)

            if isinstance(ticks, dict):
                for raw_symbol, norm in zip(symbols, normalized):
                    tick = ticks.get(norm, ticks.get(raw_symbol))
                    if not tick or not isinstance(tick, dict):
                        continue
                    result[raw_symbol] = {
                        "symbol": raw_symbol,
                        "name": tick.get("stockName", tick.get("name", "")),
                        "price": float(tick.get("lastPrice", tick.get("price", 0))),
                        "open": float(tick.get("open", 0)),
                        "high": float(tick.get("high", 0)),
                        "low": float(tick.get("low", 0)),
                        "volume": int(tick.get("volume", 0)),
                        "amount": float(tick.get("amount", 0)),
                        "pct_chg": float(tick.get("pctChg", tick.get("changePercent", 0))),
                        "change": float(tick.get("lastPrice", 0)) - float(tick.get("lastClose", tick.get("preClose", 0))),
                        "bid1": float(tick.get("bidPrice", [[0]])[0]) if tick.get("bidPrice") else 0,
                        "ask1": float(tick.get("askPrice", [[0]])[0]) if tick.get("askPrice") else 0,
                        "pre_close": float(tick.get("lastClose", tick.get("preClose", 0))),
                        "turnover": float(tick.get("turnoverRate", tick.get("turnover", 0))),
                    }
        except Exception as e:
            logger.error(f"miniQMT 行情获取异常: {e}")

        return result

    def get_market_indices(self, index_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取指数行情"""
        return self.get_quotes(index_codes)

    def get_kline(self, symbol, period="1d", start=None, end=None):
        """
        获取K线数据。period: "1m"/"5m"/"15m"/"30m"/"1h"/"1d"/"1w"/"1mon"
        返回 DataFrame (open, high, low, close, volume, amount)
        """
        xtdata = self._ensure_connected()
        norm = self.to_xtcode(symbol)

        start = (start or "").replace("-", "")
        end = (end or "").replace("-", "")

        try:
            raw = xtdata.get_market_data_ex(
                stock_list=[norm],
                period=period,
                start_time=start,
                end_time=end,
                field_list=["open", "high", "low", "close", "volume", "amount"],
            )
            # raw 可能是 {symbol: DataFrame} 或 DataFrame
            if raw is None:
                return None
            if isinstance(raw, dict):
                df = raw.get(norm, raw.get(symbol))
            else:
                df = raw
            if df is not None and hasattr(df, 'empty') and not df.empty:
                return df
        except Exception as e:
            logger.error(f"miniQMT K线获取失败 {symbol}: {e}")

        return None

    def get_tick_data(self, symbol, start=None, end=None):
        """获取分笔数据"""
        xtdata = self._ensure_connected()
        norm = self.to_xtcode(symbol)
        try:
            return xtdata.get_tick_data(norm, start or "", end or "")
        except Exception as e:
            logger.error(f"miniQMT 分笔数据获取失败 {symbol}: {e}")
            return None

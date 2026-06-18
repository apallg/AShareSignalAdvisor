"""
技术指标计算 + K 线形态识别
"""
from typing import Optional
import pandas as pd
import numpy as np
import ta


class Analyzer:
    """技术指标与分析工具"""

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """批量添加常用技术指标到 DataFrame"""
        if df.empty or len(df) < 20:
            return df

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # ── 均线 ──
        df["MA5"] = ta.trend.sma_indicator(close, window=5)
        df["MA10"] = ta.trend.sma_indicator(close, window=10)
        df["MA20"] = ta.trend.sma_indicator(close, window=20)
        df["MA60"] = ta.trend.sma_indicator(close, window=60)

        df["EMA5"] = ta.trend.ema_indicator(close, window=5)
        df["EMA20"] = ta.trend.ema_indicator(close, window=20)

        # ── MACD ──
        macd = ta.trend.MACD(close)
        df["MACD"] = macd.macd()
        df["MACD_signal"] = macd.macd_signal()
        df["MACD_hist"] = macd.macd_diff()

        # ── RSI ──
        df["RSI14"] = ta.momentum.rsi(close, window=14)

        # ── KDJ ──
        low_min = low.rolling(window=9).min()
        high_max = high.rolling(window=9).max()
        rsv = 100 * ((close - low_min) / (high_max - low_min + 1e-10))
        df["KDJ_K"] = rsv.ewm(com=2).mean()
        df["KDJ_D"] = df["KDJ_K"].ewm(com=2).mean()
        df["KDJ_J"] = 3 * df["KDJ_K"] - 2 * df["KDJ_D"]

        # ── 布林带 ──
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        df["BB_upper"] = bb.bollinger_hband()
        df["BB_middle"] = bb.bollinger_mavg()
        df["BB_lower"] = bb.bollinger_lband()
        df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_middle"]

        # ── 成交量均线 ──
        df["VOL_MA5"] = volume.rolling(5).mean()
        df["VOL_MA20"] = volume.rolling(20).mean()

        # ── ATR (平均真实波幅) ──
        df["ATR14"] = ta.volatility.average_true_range(high, low, close, window=14)

        return df

    @staticmethod
    def latest_indicators(df: pd.DataFrame) -> dict:
        """提取最新一期的指标摘要"""
        if df.empty:
            return {}
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        return {
            "最新价": round(float(latest["close"]), 2),
            "涨跌幅": round(float(latest.get("pct_chg", 0)), 2),
            "MA5": round(float(latest.get("MA5", 0)), 2),
            "MA10": round(float(latest.get("MA10", 0)), 2),
            "MA20": round(float(latest.get("MA20", 0)), 2),
            "MA60": round(float(latest.get("MA60", 0)), 2),
            "MACD": round(float(latest.get("MACD", 0)), 4),
            "MACD_signal": round(float(latest.get("MACD_signal", 0)), 4),
            "RSI14": round(float(latest.get("RSI14", 0)), 2),
            "KDJ_K": round(float(latest.get("KDJ_K", 0)), 2),
            "KDJ_D": round(float(latest.get("KDJ_D", 0)), 2),
            "KDJ_J": round(float(latest.get("KDJ_J", 0)), 2),
            "BB_upper": round(float(latest.get("BB_upper", 0)), 2),
            "BB_lower": round(float(latest.get("BB_lower", 0)), 2),
            "ATR14": round(float(latest.get("ATR14", 0)), 2),
            "成交量(万)": round(float(latest.get("volume", 0)) / 10000, 2),
        }

    @staticmethod
    def detect_cross_signals(df: pd.DataFrame) -> list:
        """检测金叉/死叉等信号"""
        signals = []
        if len(df) < 2:
            return signals

        p, c = df.iloc[-2], df.iloc[-1]  # prev, curr

        # MACD 金叉/死叉
        try:
            if p.get("MACD", 0) < p.get("MACD_signal", 0) and c.get("MACD", 0) >= c.get("MACD_signal", 0):
                signals.append(("金叉", "MACD 金叉"))
            elif p.get("MACD", 0) > p.get("MACD_signal", 0) and c.get("MACD", 0) <= c.get("MACD_signal", 0):
                signals.append(("死叉", "MACD 死叉"))
        except Exception:
            pass

        # 均线金叉/死叉
        try:
            if p.get("MA5", 0) < p.get("MA20", 0) and c.get("MA5", 0) >= c.get("MA20", 0):
                signals.append(("金叉", "MA5 上穿 MA20"))
            elif p.get("MA5", 0) > p.get("MA20", 0) and c.get("MA5", 0) <= c.get("MA20", 0):
                signals.append(("死叉", "MA5 下穿 MA20"))
        except Exception:
            pass

        # KDJ 金叉/死叉
        try:
            if p.get("KDJ_K", 0) < p.get("KDJ_D", 0) and c.get("KDJ_K", 0) >= c.get("KDJ_D", 0):
                signals.append(("金叉", "KDJ 金叉"))
            elif p.get("KDJ_K", 0) > p.get("KDJ_D", 0) and c.get("KDJ_K", 0) <= c.get("KDJ_D", 0):
                signals.append(("死叉", "KDJ 死叉"))
        except Exception:
            pass

        return signals

    @staticmethod
    def detect_kline_patterns(df: pd.DataFrame) -> list:
        """检测 K 线形态"""
        patterns = []
        if len(df) < 2:
            return patterns

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None

        o, c_val, h, l = latest["open"], latest["close"], latest["high"], latest["low"]
        body = abs(c_val - o)
        upper_shadow = h - max(o, c_val)
        lower_shadow = min(o, c_val) - l
        total_range = h - l

        if total_range == 0:
            return patterns

        # 十字星
        if body / total_range < 0.1:
            patterns.append(("十字星", "多空力量平衡，变盘信号"))

        # 锤子线 / 吊颈线
        if prev is not None:
            prev_close = prev["close"]
            if lower_shadow > 2 * body and upper_shadow < body * 0.3:
                if c_val > prev_close or lower_shadow > total_range * 0.6:
                    patterns.append(("锤子线", "下影线长，可能见底反转"))
                else:
                    patterns.append(("吊颈线", "高位长下影，可能见顶"))

            # 吞没形态
            prev_body = abs(prev["close"] - prev["open"])
            if body > prev_body * 1.2:
                if c_val > o and prev["close"] < prev["open"] and c_val > prev["open"] and o < prev["close"]:
                    patterns.append(("阳包阴", "看涨吞没形态"))
                elif c_val < o and prev["close"] > prev["open"] and c_val < prev["open"] and o > prev["close"]:
                    patterns.append(("阴包阳", "看跌吞没形态"))

        # 三连阳 / 三连阴
        if len(df) >= 4:
            last3 = df.iloc[-4:]
            if all(r["close"] > r["open"] for _, r in last3.iterrows()):
                patterns.append(("三连阳", "连续三天收阳，强势信号"))
            elif all(r["close"] < r["open"] for _, r in last3.iterrows()):
                patterns.append(("三连阴", "连续三天收阴，弱势信号"))

        return patterns

    @staticmethod
    def get_analysis_context(df: pd.DataFrame, financial: Optional[dict] = None, indicators_added: bool = False) -> str:
        """生成供 LLM 分析的上下文文本"""
        if df.empty:
            return "数据不足"

        if not indicators_added:
            df = Analyzer.add_indicators(df)
        ind = Analyzer.latest_indicators(df)
        signals = Analyzer.detect_cross_signals(df)
        patterns = Analyzer.detect_kline_patterns(df)

        # 近期表现
        recent = df.tail(60)
        pct_5d = (recent["close"].iloc[-1] / recent["close"].iloc[-5] - 1) * 100 if len(recent) >= 5 else 0
        pct_20d = (recent["close"].iloc[-1] / recent["close"].iloc[-20] - 1) * 100 if len(recent) >= 20 else 0
        pct_60d = (recent["close"].iloc[-1] / recent["close"].iloc[0] - 1) * 100 if len(recent) >= 60 else 0

        lines = [
            "=== 近期表现 ===",
            f"5日涨跌幅: {pct_5d:.2f}%",
            f"20日涨跌幅: {pct_20d:.2f}%",
            f"60日涨跌幅: {pct_60d:.2f}%",
            "",
            "=== 技术指标 ===",
        ]
        for k, v in ind.items():
            lines.append(f"{k}: {v}")

        if signals:
            lines.extend(["", "=== 交叉信号 ==="])
            for sig_type, desc in signals:
                emoji = "🟢" if sig_type == "金叉" else "🔴"
                lines.append(f"{emoji} {desc}")

        if patterns:
            lines.extend(["", "=== K线形态 ==="])
            for p_name, p_desc in patterns:
                lines.append(f"• {p_name}: {p_desc}")

        if financial:
            lines.extend(["", "=== 财务摘要 ==="])
            for k, v in financial.items():
                lines.append(f"{k}: {v}")

        return "\n".join(lines)

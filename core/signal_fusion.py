"""
多指标信号融合投票 — 对已附指标 DataFrame 做加权投票，产出综合交易信号
"""
from dataclasses import dataclass, field
import pandas as pd
import logging

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "MACD": 1.0,
    "RSI": 0.8,
    "MA": 0.7,
    "KDJ": 0.5,
    "BB": 0.6,
    "VOLUME": 0.3,
}


@dataclass
class FusionResult:
    score: float = 0.0           # -max_weight ~ +max_weight
    action: str = "hold"         # buy / sell / hold
    confidence: float = 0.0      # 0.0 ~ 1.0
    indicator_votes: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)


class SignalFusion:
    def __init__(self, weights: dict = None):
        self.weights = weights or DEFAULT_WEIGHTS
        self._max_weight = sum(abs(w) for w in self.weights.values())

    def evaluate(self, df: pd.DataFrame) -> FusionResult:
        if len(df) < 2:
            return FusionResult()

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        votes = {}
        reasons = []

        v = self._vote_macd(prev, latest)
        votes["MACD"] = v
        if v != 0:
            reasons.append(("MACD", "金叉" if v > 0 else "死叉"))

        v = self._vote_rsi(latest)
        votes["RSI"] = v
        if v != 0:
            reasons.append(("RSI", "超卖" if v > 0 else "超买"))

        v = self._vote_ma(latest)
        votes["MA"] = v
        if v != 0:
            reasons.append(("MA", "多头排列" if v > 0 else "空头排列"))

        v = self._vote_kdj(prev, latest)
        votes["KDJ"] = v
        if v != 0:
            reasons.append(("KDJ", "金叉" if v > 0 else "死叉"))

        v = self._vote_bb(latest)
        votes["BB"] = v
        if v != 0:
            reasons.append(("BB", "触及下轨" if v > 0 else "触及上轨"))

        v = self._vote_volume(latest)
        votes["VOLUME"] = v
        if v != 0:
            reasons.append(("VOLUME", "放量上涨" if v > 0 else "放量下跌"))

        weighted_sum = sum(self.weights.get(k, 0) * v for k, v in votes.items())
        confidence = abs(weighted_sum) / self._max_weight if self._max_weight > 0 else 0

        if weighted_sum > 0 and confidence >= 0.3:
            action = "buy"
        elif weighted_sum < 0 and confidence >= 0.3:
            action = "sell"
        else:
            action = "hold"

        return FusionResult(
            score=round(weighted_sum, 3),
            action=action,
            confidence=round(confidence, 3),
            indicator_votes=votes,
            reasons=[f"{name}: {reason}" for name, reason in reasons],
        )

    def _safe(self, row, *keys):
        for k in keys:
            v = row.get(k)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                return v
        return 0

    def _vote_macd(self, prev, latest) -> int:
        macd = self._safe(latest, "MACD")
        sig = self._safe(latest, "MACD_signal")
        prev_macd = self._safe(prev, "MACD")
        prev_sig = self._safe(prev, "MACD_signal")
        if prev_macd < prev_sig and macd >= sig:
            return 1
        if prev_macd > prev_sig and macd <= sig:
            return -1
        return 0

    def _vote_rsi(self, latest) -> int:
        rsi = self._safe(latest, "RSI14")
        if rsi < 30:
            return 1
        if rsi > 70:
            return -1
        return 0

    def _vote_ma(self, latest) -> int:
        ma5 = self._safe(latest, "MA5")
        ma10 = self._safe(latest, "MA10")
        ma20 = self._safe(latest, "MA20")
        if ma5 and ma10 and ma20:
            if ma5 > ma20 and ma5 > ma10:
                return 1
            if ma5 < ma20 and ma5 < ma10:
                return -1
        return 0

    def _vote_kdj(self, prev, latest) -> int:
        k = self._safe(latest, "KDJ_K")
        d = self._safe(latest, "KDJ_D")
        prev_k = self._safe(prev, "KDJ_K")
        prev_d = self._safe(prev, "KDJ_D")
        if prev_k < prev_d and k >= d and k < 30:
            return 1
        if prev_k > prev_d and k <= d and k > 70:
            return -1
        return 0

    def _vote_bb(self, latest) -> int:
        close = self._safe(latest, "close")
        lower = self._safe(latest, "BB_lower")
        upper = self._safe(latest, "BB_upper")
        if close and lower and close <= lower:
            return 1
        if close and upper and close >= upper:
            return -1
        return 0

    def _vote_volume(self, latest) -> int:
        vol = self._safe(latest, "volume")
        vol_ma20 = self._safe(latest, "VOL_MA20")
        pct = self._safe(latest, "pct_chg")
        if vol and vol_ma20 and vol > 1.5 * vol_ma20:
            if pct > 1:
                return 1
            if pct < -1:
                return -1
        return 0

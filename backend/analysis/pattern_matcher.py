"""
패턴 클러스터링 모듈
최근 가격 패턴과 과거 유사 패턴을 비교하여 방향 예측
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PatternMatch:
    """유사 패턴 매칭 결과"""
    similarity: float      # 0.0 ~ 1.0 (코사인 유사도)
    direction: str         # "up", "down", "flat"
    outcome_pct: float     # 이후 가격 변동률 (%)


@dataclass
class PatternResult:
    """패턴 분석 최종 결과"""
    total_matches: int
    up_count: int
    down_count: int
    up_pct: float
    avg_outcome_pct: float
    best_matches: list[dict]
    description: str


class PatternMatcher:
    """
    가격 패턴 유사도 비교.
    최근 N봉 정규화 패턴 → 과거 패턴 DB와 코사인 유사도 비교.
    """

    def __init__(self, pattern_length: int = 20, min_similarity: float = 0.85):
        self.pattern_length = pattern_length
        self.min_similarity = min_similarity
        self._pattern_db: list[dict] = []  # {"pattern": ndarray, "outcome": float, "symbol": str}
        self._max_patterns = 5000

    def _normalize_pattern(self, prices: list[float]) -> Optional[np.ndarray]:
        """가격 시계열을 정규화 (0~1 스케일링)."""
        if len(prices) < self.pattern_length:
            return None
        segment = np.array(prices[-self.pattern_length:], dtype=float)
        mn, mx = segment.min(), segment.max()
        if mx - mn < 1e-10:
            return None
        return (segment - mn) / (mx - mn)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """코사인 유사도 계산."""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def add_pattern(self, prices: list[float], outcome_pct: float, symbol: str = ""):
        """과거 패턴을 DB에 추가."""
        pattern = self._normalize_pattern(prices)
        if pattern is None:
            return
        self._pattern_db.append({
            "pattern": pattern,
            "outcome": outcome_pct,
            "symbol": symbol,
        })
        if len(self._pattern_db) > self._max_patterns:
            self._pattern_db = self._pattern_db[-self._max_patterns:]

    def build_from_candles(self, close_prices: list[float], symbol: str = "", lookahead: int = 5):
        """
        캔들 데이터에서 과거 패턴 DB를 자동 구축.
        각 위치에서 pattern_length개 패턴 추출 → lookahead봉 후 결과 기록.
        """
        if len(close_prices) < self.pattern_length + lookahead + 1:
            return

        for i in range(self.pattern_length, len(close_prices) - lookahead):
            segment = close_prices[i - self.pattern_length:i]
            entry = close_prices[i]
            future = close_prices[i + lookahead]
            if entry <= 0:
                continue
            outcome = ((future - entry) / entry) * 100
            self.add_pattern(segment, outcome, symbol)

    def find_similar(self, current_prices: list[float], top_k: int = 50) -> Optional[PatternResult]:
        """
        현재 패턴과 유사한 과거 패턴을 찾아 방향 예측.
        """
        if not self._pattern_db:
            return None

        current = self._normalize_pattern(current_prices)
        if current is None:
            return None

        # 유사도 계산
        matches: list[PatternMatch] = []
        for entry in self._pattern_db:
            sim = self._cosine_similarity(current, entry["pattern"])
            if sim >= self.min_similarity:
                direction = "up" if entry["outcome"] > 0.5 else "down" if entry["outcome"] < -0.5 else "flat"
                matches.append(PatternMatch(
                    similarity=sim,
                    direction=direction,
                    outcome_pct=entry["outcome"],
                ))

        if not matches:
            return PatternResult(
                total_matches=0, up_count=0, down_count=0,
                up_pct=0.5, avg_outcome_pct=0.0,
                best_matches=[], description="유사 패턴 없음",
            )

        # 유사도 순 정렬
        matches.sort(key=lambda m: m.similarity, reverse=True)
        top_matches = matches[:top_k]

        up_count = sum(1 for m in top_matches if m.direction == "up")
        down_count = sum(1 for m in top_matches if m.direction == "down")
        total = len(top_matches)
        up_pct = up_count / total if total > 0 else 0.5
        avg_outcome = sum(m.outcome_pct for m in top_matches) / total if total > 0 else 0.0

        best_list = [
            {"similarity": round(m.similarity, 4), "direction": m.direction, "outcome_pct": round(m.outcome_pct, 2)}
            for m in top_matches[:5]
        ]

        direction_str = "상승" if up_pct > 0.6 else "하락" if up_pct < 0.4 else "혼조"
        desc = f"유사 패턴 {total}건 중 {up_count}건({up_pct:.0%}) 상승 — {direction_str} 우세"

        return PatternResult(
            total_matches=total,
            up_count=up_count,
            down_count=down_count,
            up_pct=round(up_pct, 4),
            avg_outcome_pct=round(avg_outcome, 4),
            best_matches=best_list,
            description=desc,
        )

    def get_confidence_modifier(self, result: Optional[PatternResult], signal: str) -> float:
        """패턴 매칭 결과 기반 신뢰도 보정."""
        if not result or result.total_matches < 10:
            return 0.0

        is_long = "LONG" in signal
        is_short = "SHORT" in signal

        if is_long and result.up_pct > 0.65:
            return min(0.05 * (result.up_pct - 0.5), 0.05)
        elif is_short and result.up_pct < 0.35:
            return min(0.05 * (0.5 - result.up_pct), 0.05)
        elif is_long and result.up_pct < 0.35:
            return -0.03
        elif is_short and result.up_pct > 0.65:
            return -0.03

        return 0.0

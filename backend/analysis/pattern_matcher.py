"""
패턴 클러스터링 모듈
최근 가격 패턴과 과거 유사 패턴을 비교하여 방향 예측.
C2 개선: DTW(Dynamic Time Warping) 거리 + Z-score 정규화
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
        """Z-score 정규화 (C2: min-max 대신 Z-score로 스케일 불변)."""
        if len(prices) < self.pattern_length:
            return None
        segment = np.array(prices[-self.pattern_length:], dtype=float)
        std = segment.std()
        if std < 1e-10:
            return None
        return (segment - segment.mean()) / std

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """코사인 유사도 계산 (빠른 사전 필터용)."""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def _dtw_distance(self, a: np.ndarray, b: np.ndarray) -> float:
        """
        C2: DTW(Dynamic Time Warping) 거리 계산.
        시간축 왜곡에 강건한 패턴 비교.
        Sakoe-Chiba band(window=3)로 속도 최적화.
        """
        n = len(a)
        m = len(b)
        window = min(3, max(n, m))  # Sakoe-Chiba band

        dtw = np.full((n + 1, m + 1), np.inf)
        dtw[0, 0] = 0.0

        for i in range(1, n + 1):
            j_start = max(1, i - window)
            j_end = min(m, i + window)
            for j in range(j_start, j_end + 1):
                cost = (a[i - 1] - b[j - 1]) ** 2
                dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])

        dist = float(np.sqrt(dtw[n, m]))
        return dist

    def _dtw_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """DTW 거리를 0~1 유사도로 변환."""
        dist = self._dtw_distance(a, b)
        # Z-score 정규화된 패턴의 DTW 거리를 유사도로 변환
        # 최대 거리 = sqrt(pattern_length) * 4 정도 (z-score 범위 고려)
        max_dist = np.sqrt(self.pattern_length) * 4.0
        similarity = max(0.0, 1.0 - dist / max_dist)
        return similarity

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
        C2: 2단계 필터링 — 코사인 사전필터(빠름) → DTW 정밀 비교(정확).
        """
        if not self._pattern_db:
            return None

        current = self._normalize_pattern(current_prices)
        if current is None:
            return None

        # 1단계: 코사인 유사도로 후보 사전 필터 (상위 200개)
        cosine_pre = self.min_similarity - 0.10  # 여유 있게 필터
        candidates = []
        for entry in self._pattern_db:
            cos_sim = self._cosine_similarity(current, entry["pattern"])
            if cos_sim >= cosine_pre:
                candidates.append((cos_sim, entry))

        candidates.sort(key=lambda x: x[0], reverse=True)
        candidates = candidates[:200]

        # 2단계: DTW 유사도로 정밀 비교
        matches: list[PatternMatch] = []
        for _cos_sim, entry in candidates:
            dtw_sim = self._dtw_similarity(current, entry["pattern"])
            if dtw_sim >= self.min_similarity:
                direction = "up" if entry["outcome"] > 0.5 else "down" if entry["outcome"] < -0.5 else "flat"
                matches.append(PatternMatch(
                    similarity=dtw_sim,
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

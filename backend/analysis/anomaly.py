"""
이상치 탐지 모듈
Isolation Forest 기반 비정상 시장 상태 감지
"""
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# 캐시
_anomaly_cache: dict = {"model": None, "updated_at": None}
ANOMALY_CACHE_TTL = 600  # 10분


@dataclass
class AnomalyResult:
    """이상치 탐지 결과"""
    is_anomaly: bool
    anomaly_score: float  # -1(이상) ~ +1(정상)
    description: str
    features: dict


def _extract_features(
    volume_ratio: float,
    atr_ratio: float,
    price_change_pct: float,
    funding_rate: float = 0.0,
    oi_change_pct: float = 0.0,
) -> np.ndarray:
    """특징 벡터 추출."""
    return np.array([
        volume_ratio,
        atr_ratio,
        price_change_pct,
        funding_rate * 100,
        oi_change_pct,
    ])


class AnomalyDetector:
    """
    Isolation Forest 기반 이상치 탐지.
    sklearn 없이 간이 구현 (통계적 이상치).
    """

    def __init__(self):
        self._history: list[np.ndarray] = []
        self._mean: Optional[np.ndarray] = None
        self._std: Optional[np.ndarray] = None
        self._min_samples = 50

    def update(self, features: np.ndarray):
        """히스토리에 특징 벡터 추가."""
        self._history.append(features)
        # 최대 1000개 유지
        if len(self._history) > 1000:
            self._history = self._history[-1000:]
        # 통계 갱신
        if len(self._history) >= self._min_samples:
            data = np.array(self._history)
            self._mean = np.mean(data, axis=0)
            self._std = np.std(data, axis=0)
            self._std[self._std < 1e-8] = 1e-8

    def detect(
        self,
        volume_ratio: float,
        atr_ratio: float,
        price_change_pct: float,
        funding_rate: float = 0.0,
        oi_change_pct: float = 0.0,
    ) -> AnomalyResult:
        """
        이상치 탐지 실행.
        Z-score 기반: |z| > 3 → 이상치
        """
        features = _extract_features(
            volume_ratio, atr_ratio, price_change_pct, funding_rate, oi_change_pct
        )
        self.update(features)

        if self._mean is None or self._std is None:
            return AnomalyResult(
                is_anomaly=False,
                anomaly_score=0.0,
                description="데이터 축적 중 (최소 50개 필요)",
                features=_features_dict(features),
            )

        z_scores = np.abs((features - self._mean) / self._std)
        max_z = float(np.max(z_scores))
        avg_z = float(np.mean(z_scores))

        # 이상치 판정: 최대 z-score > 3 또는 평균 z-score > 2
        is_anomaly = max_z > 3.0 or avg_z > 2.0
        # anomaly_score: -1(매우 이상) ~ +1(매우 정상)
        anomaly_score = max(-1.0, min(1.0, 1.0 - avg_z / 3.0))

        # 어떤 특징이 이상한지 설명
        feature_names = ["거래량비율", "ATR비율", "가격변동%", "펀딩레이트", "OI변화%"]
        anomalous_features = [
            f"{feature_names[i]}(z={z_scores[i]:.1f})"
            for i in range(len(z_scores))
            if z_scores[i] > 2.5
        ]

        if is_anomaly:
            desc = f"비정상 시장 상태 감지: {', '.join(anomalous_features)}"
        else:
            desc = "정상 범위"

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=round(anomaly_score, 4),
            description=desc,
            features=_features_dict(features),
        )

    def get_anomaly_modifier(self, anomaly_result: AnomalyResult) -> float:
        """이상치 기반 신뢰도 보정값. 이상치 감지 시 신뢰도 감소."""
        if anomaly_result.is_anomaly:
            return -0.05 * (1.0 - anomaly_result.anomaly_score)
        return 0.0


def _features_dict(features: np.ndarray) -> dict:
    """특징 벡터를 딕셔너리로 변환."""
    names = ["volume_ratio", "atr_ratio", "price_change_pct", "funding_rate_pct", "oi_change_pct"]
    return {n: round(float(features[i]), 4) for i, n in enumerate(names)}

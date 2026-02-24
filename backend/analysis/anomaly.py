"""
이상치 탐지 모듈
C4 개선: Mahalanobis 거리 + 시간 가중 공분산 기반 비정상 시장 상태 감지.
기존 Z-score 대비 특징 간 상관관계를 고려하여 더 정확한 이상치 판별.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


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
    C4: Mahalanobis 거리 기반 이상치 탐지.
    - 특징 간 상관관계를 반영하여 다변량 이상치 감지
    - 시간 가중(지수 감쇠)으로 최근 데이터에 더 높은 가중치
    - 공분산 행렬이 특이(singular)한 경우 Z-score 폴백
    """

    def __init__(self, decay: float = 0.995):
        self._history: list[np.ndarray] = []
        self._mean: Optional[np.ndarray] = None
        self._cov_inv: Optional[np.ndarray] = None  # 공분산 역행렬
        self._std: Optional[np.ndarray] = None       # Z-score 폴백용
        self._min_samples = 50
        self._decay = decay  # 시간 가중 감쇠율 (0.995 → ~500봉 반감기)

    def update(self, features: np.ndarray):
        """히스토리에 특징 벡터 추가 + 통계 갱신."""
        self._history.append(features)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

        if len(self._history) >= self._min_samples:
            self._update_statistics()

    def _update_statistics(self):
        """시간 가중 평균/공분산 계산."""
        data = np.array(self._history)
        n = len(data)

        # 시간 가중치: 최근 → 높은 가중치
        weights = np.array([self._decay ** (n - 1 - i) for i in range(n)])
        weights /= weights.sum()

        # 가중 평균
        self._mean = np.average(data, axis=0, weights=weights)

        # 가중 공분산 행렬
        centered = data - self._mean
        weighted_centered = centered * weights[:, np.newaxis]
        cov = centered.T @ weighted_centered

        # Z-score 폴백용 표준편차
        self._std = np.sqrt(np.diag(cov))
        self._std[self._std < 1e-8] = 1e-8

        # 공분산 역행렬 (정칙화 + 역행렬)
        try:
            # 정칙화: 작은 값을 대각에 추가 (numerical stability)
            reg = 1e-6 * np.eye(cov.shape[0])
            self._cov_inv = np.linalg.inv(cov + reg)
        except np.linalg.LinAlgError:
            self._cov_inv = None
            logger.debug("공분산 역행렬 계산 실패 → Z-score 폴백")

    def _mahalanobis_distance(self, features: np.ndarray) -> Optional[float]:
        """Mahalanobis 거리 계산: sqrt((x-μ)^T Σ^{-1} (x-μ))"""
        if self._mean is None or self._cov_inv is None:
            return None
        diff = features - self._mean
        md_sq = diff @ self._cov_inv @ diff
        if md_sq < 0:
            return None
        return float(np.sqrt(md_sq))

    def _zscore_fallback(self, features: np.ndarray) -> tuple[float, float, np.ndarray]:
        """Z-score 폴백 (공분산 역행렬 불가 시)."""
        z_scores = np.abs((features - self._mean) / self._std)
        max_z = float(np.max(z_scores))
        avg_z = float(np.mean(z_scores))
        return max_z, avg_z, z_scores

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
        Mahalanobis 거리 > 3.0 → 이상치 (chi-squared df=5 기준 p<0.01).
        폴백: Z-score |z| > 3 또는 avg_z > 2.
        """
        features = _extract_features(
            volume_ratio, atr_ratio, price_change_pct, funding_rate, oi_change_pct
        )
        self.update(features)

        if self._mean is None:
            return AnomalyResult(
                is_anomaly=False,
                anomaly_score=0.0,
                description="데이터 축적 중 (최소 50개 필요)",
                features=_features_dict(features),
            )

        # Mahalanobis 거리 시도
        md = self._mahalanobis_distance(features)

        feature_names = ["거래량비율", "ATR비율", "가격변동%", "펀딩레이트", "OI변화%"]

        if md is not None:
            # Mahalanobis 기반 판정
            # 5차원 카이제곱 분포: 99% = ~15.09, sqrt → ~3.9
            is_anomaly = md > 3.5
            anomaly_score = max(-1.0, min(1.0, 1.0 - md / 5.0))

            # 어떤 특징이 기여하는지 (개별 Z-score로 보조 설명)
            z_scores = np.abs((features - self._mean) / self._std)
            anomalous_features = [
                f"{feature_names[i]}(z={z_scores[i]:.1f})"
                for i in range(len(z_scores))
                if z_scores[i] > 2.5
            ]

            if is_anomaly:
                desc = f"비정상 시장 상태 (Mahalanobis={md:.1f}): {', '.join(anomalous_features)}"
            else:
                desc = f"정상 범위 (Mahalanobis={md:.1f})"

        else:
            # Z-score 폴백
            max_z, avg_z, z_scores = self._zscore_fallback(features)
            is_anomaly = max_z > 3.0 or avg_z > 2.0
            anomaly_score = max(-1.0, min(1.0, 1.0 - avg_z / 3.0))

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

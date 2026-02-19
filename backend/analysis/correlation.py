"""
코인 간 상관관계 분석 모듈
- 30개 코인의 수익률 상관관계 행렬 계산
- BTC 대비 β(베타) 계수 산출
- 알트코인 시그널 신뢰도 보정에 활용
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 상관관계 캐시
_corr_cache: dict = {"matrix": None, "betas": None, "updated_at": None}
CORR_CACHE_TTL = 300  # 5분


class CorrelationAnalyzer:
    """코인 간 상관관계 분석"""

    def __init__(self, candle_repo):
        self.candle_repo = candle_repo

    async def update_correlation(self, symbols: list[str], timeframe: str = "1h") -> dict:
        """
        상관관계 행렬 및 베타 계수 업데이트.
        symbols: 분석 대상 심볼 리스트
        """
        now = datetime.now(timezone.utc)
        if (
            _corr_cache["matrix"] is not None
            and _corr_cache["updated_at"]
            and (now - _corr_cache["updated_at"]).total_seconds() < CORR_CACHE_TTL
        ):
            return _corr_cache

        try:
            returns_data = {}

            for symbol in symbols:
                try:
                    df = await self.candle_repo.get_candles(symbol, timeframe, limit=500)
                    if df is None or len(df) < 100:
                        continue
                    # 수익률 계산
                    returns = df["close"].pct_change().dropna()
                    returns_data[symbol] = returns
                except Exception:
                    continue

            if len(returns_data) < 5:
                logger.warning("상관관계 분석 스킵: 충분한 심볼 없음 (%d개)", len(returns_data))
                return _corr_cache

            # DataFrame으로 합치기 (인덱스 정렬)
            returns_df = pd.DataFrame(returns_data)
            # NaN이 많은 열 제거
            returns_df = returns_df.dropna(axis=1, thresh=int(len(returns_df) * 0.7))

            if returns_df.shape[1] < 5:
                return _corr_cache

            # 상관관계 행렬
            corr_matrix = returns_df.corr()

            # BTC 대비 베타 계수 계산
            betas = {}
            btc_col = "BTC/USDT"
            if btc_col in returns_df.columns:
                btc_returns = returns_df[btc_col].dropna()
                btc_var = btc_returns.var()
                if btc_var > 0:
                    for col in returns_df.columns:
                        if col == btc_col:
                            betas[col] = 1.0
                            continue
                        # 공통 인덱스만 사용
                        common = returns_df[[btc_col, col]].dropna()
                        if len(common) < 50:
                            continue
                        cov = common[btc_col].cov(common[col])
                        beta = cov / btc_var
                        betas[col] = round(float(beta), 4)

            # 상관관계 행렬을 dict로 변환 (JSON 직렬화 가능)
            corr_dict = {}
            for sym in corr_matrix.columns:
                corr_dict[sym] = {
                    other: round(float(corr_matrix.loc[sym, other]), 4)
                    for other in corr_matrix.columns
                }

            _corr_cache["matrix"] = corr_dict
            _corr_cache["betas"] = betas
            _corr_cache["updated_at"] = now

            logger.info(
                "상관관계 업데이트: %d개 심볼, BTC 베타 %d개",
                len(corr_dict), len(betas),
            )

            return _corr_cache

        except Exception as e:
            logger.error("상관관계 분석 실패: %s", e)
            return _corr_cache

    def get_beta(self, symbol: str) -> Optional[float]:
        """특정 심볼의 BTC 대비 베타 계수 반환."""
        if _corr_cache["betas"]:
            return _corr_cache["betas"].get(symbol)
        return None

    def get_correlation(self, symbol_a: str, symbol_b: str) -> Optional[float]:
        """두 심볼 간 상관계수 반환."""
        matrix = _corr_cache.get("matrix")
        if matrix and symbol_a in matrix and symbol_b in matrix[symbol_a]:
            return matrix[symbol_a][symbol_b]
        return None

    def get_btc_confidence_modifier(self, symbol: str, signal: str) -> float:
        """
        BTC 베타 기반 신뢰도 보정값 반환.
        높은 베타 + BTC와 같은 방향 → 신뢰도 증가
        높은 베타 + BTC와 반대 방향 → 신뢰도 감소
        """
        beta = self.get_beta(symbol)
        if beta is None or symbol == "BTC/USDT":
            return 0.0

        # 베타가 1보다 높으면 BTC에 더 민감 → 보정 폭 증가
        sensitivity = min(abs(beta) - 1.0, 0.5) * 0.1 if abs(beta) > 1.0 else 0.0

        btc_corr = self.get_correlation(symbol, "BTC/USDT")
        if btc_corr is None:
            return 0.0

        # 높은 상관관계 + 높은 베타 → 더 큰 보정
        if btc_corr > 0.7:
            return sensitivity  # 양의 보정 (BTC와 함께 움직임)
        elif btc_corr < 0.3:
            return -sensitivity * 0.5  # 약한 음의 보정

        return 0.0

    def get_summary(self) -> dict:
        """API용 상관관계 요약 반환."""
        betas = _corr_cache.get("betas", {}) or {}
        matrix = _corr_cache.get("matrix", {}) or {}
        updated = _corr_cache.get("updated_at")

        # 상위 베타 코인
        sorted_betas = sorted(betas.items(), key=lambda x: abs(x[1]), reverse=True)

        return {
            "symbol_count": len(matrix),
            "beta_count": len(betas),
            "top_beta": sorted_betas[:10] if sorted_betas else [],
            "updated_at": updated.isoformat() if updated else None,
        }

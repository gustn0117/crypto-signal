"""
가격 레벨 분석 모듈
ATR, 지지/저항선, 최근 고저점 계산
"""
import logging
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass, asdict
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class PriceLevels:
    """가격 레벨 정보"""
    atr: float                      # ATR(14) 절대값
    atr_percent: float              # ATR / 현재가 * 100
    support_levels: List[float]     # 가까운 지지선 (최대 3개, 가격 내림차순)
    resistance_levels: List[float]  # 가까운 저항선 (최대 3개, 가격 오름차순)
    recent_high: float              # 20봉 최고가
    recent_low: float               # 20봉 최저가

    def to_dict(self) -> dict:
        return asdict(self)


def _find_swing_points(df: pd.DataFrame, lookback: int = 100, window: int = 2) -> tuple[List[float], List[float]]:
    """
    Swing high/low 기반 지지/저항선 탐색
    window: 양옆 몇 봉을 비교할지 (2 = 양옆 2봉씩)
    """
    data = df.tail(lookback)
    highs = data["high"].values
    lows = data["low"].values
    swing_highs = []
    swing_lows = []

    for i in range(window, len(data) - window):
        # Swing High: 현재 봉의 고가가 양옆 window개 봉보다 높음
        is_swing_high = all(highs[i] > highs[i - j] for j in range(1, window + 1)) and \
                        all(highs[i] > highs[i + j] for j in range(1, window + 1))
        if is_swing_high:
            swing_highs.append(highs[i])

        # Swing Low: 현재 봉의 저가가 양옆 window개 봉보다 낮음
        is_swing_low = all(lows[i] < lows[i - j] for j in range(1, window + 1)) and \
                       all(lows[i] < lows[i + j] for j in range(1, window + 1))
        if is_swing_low:
            swing_lows.append(lows[i])

    return swing_highs, swing_lows


def calculate_levels(df: pd.DataFrame) -> PriceLevels:
    """
    가격 레벨 계산
    - ATR(14)
    - 지지/저항선 (swing high/low 기반)
    - 최근 20봉 고저점
    """
    try:
        current_price = df["close"].iloc[-1]

        # ATR 계산
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr_series is None or atr_series.empty or pd.isna(atr_series.iloc[-1]):
            atr = current_price * 0.02  # 폴백: 가격의 2%
            logger.warning("ATR 계산 실패, 폴백 사용: %.4f", atr)
        else:
            atr = float(atr_series.iloc[-1])

        atr_percent = (atr / current_price) * 100 if current_price > 0 else 0

        # 최근 고저점
        recent_data = df.tail(20)
        recent_high = float(recent_data["high"].max())
        recent_low = float(recent_data["low"].min())

        # Swing 기반 지지/저항
        swing_highs, swing_lows = _find_swing_points(df)

        # 현재 가격 기준으로 분류
        resistance_levels = sorted(
            [h for h in swing_highs if h > current_price],
            key=lambda x: x  # 가까운 것부터
        )[:3]

        support_levels = sorted(
            [l for l in swing_lows if l < current_price],
            key=lambda x: -x  # 가까운 것부터 (가격 내림차순)
        )[:3]

        # 지지/저항이 부족하면 최근 고저점으로 보충
        if not resistance_levels:
            resistance_levels = [recent_high]
        if not support_levels:
            support_levels = [recent_low]

        return PriceLevels(
            atr=round(atr, 6),
            atr_percent=round(atr_percent, 2),
            support_levels=[round(s, 6) for s in support_levels],
            resistance_levels=[round(r, 6) for r in resistance_levels],
            recent_high=round(recent_high, 6),
            recent_low=round(recent_low, 6),
        )
    except Exception as e:
        logger.error("가격 레벨 계산 오류: %s", e, exc_info=True)
        current_price = df["close"].iloc[-1] if len(df) > 0 else 0
        fallback_atr = current_price * 0.02
        return PriceLevels(
            atr=round(fallback_atr, 6),
            atr_percent=2.0,
            support_levels=[round(current_price * 0.98, 6)],
            resistance_levels=[round(current_price * 1.02, 6)],
            recent_high=round(current_price * 1.02, 6),
            recent_low=round(current_price * 0.98, 6),
        )

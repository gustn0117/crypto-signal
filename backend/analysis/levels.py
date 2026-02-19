"""
가격 레벨 분석 모듈
ATR, 지지/저항선, Pivot Points, Fibonacci 되돌림 계산
"""
import logging
import numpy as np
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass, asdict, field
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
    pivot_levels: dict = field(default_factory=dict)        # {"P": ..., "R1": ..., "S1": ..., "R2": ..., "S2": ...}
    fibonacci_levels: List[float] = field(default_factory=list)  # 0.236, 0.382, 0.500, 0.618, 0.786

    def to_dict(self) -> dict:
        return asdict(self)


def _calc_pivot_points(df: pd.DataFrame) -> dict:
    """직전 완성 봉의 HLC를 사용한 전통적 Pivot Points 계산.
    Returns: {"P": float, "R1": float, "S1": float, "R2": float, "S2": float}
    """
    if len(df) < 2:
        return {}
    prev = df.iloc[-2]  # 직전 완성 봉
    h, l, c = float(prev["high"]), float(prev["low"]), float(prev["close"])
    p = (h + l + c) / 3
    return {
        "P": round(p, 6),
        "R1": round(2 * p - l, 6),
        "S1": round(2 * p - h, 6),
        "R2": round(p + (h - l), 6),
        "S2": round(p - (h - l), 6),
    }


def _calc_fibonacci_levels(df: pd.DataFrame, lookback: int = 50) -> List[float]:
    """최근 주요 스윙(고점~저점) 사이 Fibonacci 되돌림 레벨 계산.
    상승 추세면 저점 기준 상방, 하락 추세면 고점 기준 하방으로 계산.
    """
    if len(df) < lookback:
        data = df
    else:
        data = df.tail(lookback)

    swing_high = float(data["high"].max())
    swing_low = float(data["low"].min())
    price_range = swing_high - swing_low

    if price_range <= 0:
        return []

    current_price = float(df["close"].iloc[-1])
    ratios = [0.236, 0.382, 0.500, 0.618, 0.786]

    # 현재가가 중간 이상 → 상승 추세 가정 (저점 기준 되돌림)
    mid = swing_low + price_range * 0.5
    if current_price >= mid:
        levels = [round(swing_high - price_range * r, 6) for r in ratios]
    else:
        levels = [round(swing_low + price_range * r, 6) for r in ratios]

    return levels


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

        # Pivot Points
        pivot_levels = _calc_pivot_points(df)

        # Fibonacci 되돌림
        fibonacci_levels = _calc_fibonacci_levels(df)

        # Pivot/Fibonacci 레벨을 지지/저항에 병합 (현재가 기준 분류)
        extra_levels = fibonacci_levels[:]
        for key in ("R1", "R2", "S1", "S2"):
            if key in pivot_levels:
                extra_levels.append(pivot_levels[key])

        for lv in extra_levels:
            if lv > current_price and lv not in resistance_levels:
                resistance_levels.append(lv)
            elif lv < current_price and lv not in support_levels:
                support_levels.append(lv)

        # 재정렬 후 상위 5개만
        resistance_levels = sorted(resistance_levels)[:5]
        support_levels = sorted(support_levels, reverse=True)[:5]

        return PriceLevels(
            atr=round(atr, 6),
            atr_percent=round(atr_percent, 2),
            support_levels=[round(s, 6) for s in support_levels],
            resistance_levels=[round(r, 6) for r in resistance_levels],
            recent_high=round(recent_high, 6),
            recent_low=round(recent_low, 6),
            pivot_levels=pivot_levels,
            fibonacci_levels=fibonacci_levels,
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

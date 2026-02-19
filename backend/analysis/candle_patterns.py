"""
캔들스틱 패턴 인식 모듈
도지, 해머, 잉걸핑, 모닝스타, 이브닝스타 등
거래량 확인 기능 포함
"""
import logging
import numpy as np
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class CandlePatternResult:
    """캔들 패턴 분석 결과"""
    name: str
    signal: str  # "long", "short", "neutral"
    strength: float
    description: str


def _volume_factor(df: pd.DataFrame, bar_index: int = -1, lookback: int = 20) -> float:
    """
    캔들 패턴 발생 시점의 거래량 확인 계수 (0.7 ~ 1.3).
    거래량이 평균의 1.5배 이상이면 패턴 강도를 부스트,
    평균의 0.5배 미만이면 패턴 강도를 감소.
    """
    if "volume" not in df.columns or len(df) < lookback + 2:
        return 1.0  # 거래량 데이터 없으면 영향 없음

    vol = df["volume"].values
    idx = len(vol) + bar_index if bar_index < 0 else bar_index
    if idx < lookback:
        return 1.0

    avg_vol = np.mean(vol[idx - lookback:idx])
    if avg_vol <= 0:
        return 1.0

    current_vol = vol[idx]
    ratio = current_vol / avg_vol

    if ratio >= 2.0:
        return 1.3  # 매우 높은 거래량: +30%
    elif ratio >= 1.5:
        return 1.15  # 높은 거래량: +15%
    elif ratio < 0.5:
        return 0.7  # 매우 낮은 거래량: -30%
    elif ratio < 0.8:
        return 0.85  # 낮은 거래량: -15%
    return 1.0


def _body_size(row: pd.Series) -> float:
    return abs(row["close"] - row["open"])


def _upper_shadow(row: pd.Series) -> float:
    return row["high"] - max(row["close"], row["open"])


def _lower_shadow(row: pd.Series) -> float:
    return min(row["close"], row["open"]) - row["low"]


def _is_bullish(row: pd.Series) -> bool:
    return row["close"] > row["open"]


def _is_bearish(row: pd.Series) -> bool:
    return row["close"] < row["open"]


def detect_doji(df: pd.DataFrame) -> CandlePatternResult | None:
    """도지 패턴 감지 (몸통이 매우 작은 캔들)"""
    last = df.iloc[-1]
    body = _body_size(last)
    total_range = last["high"] - last["low"]

    if total_range == 0:
        return None

    if body / total_range < 0.1:
        vf = _volume_factor(df)
        return CandlePatternResult(
            name="도지 (Doji)",
            signal="neutral",
            strength=min(0.95, 0.5 * vf),
            description="추세 전환 가능성 - 매수/매도 세력 균형"
        )
    return None


def detect_hammer(df: pd.DataFrame) -> CandlePatternResult | None:
    """해머/역해머 패턴 감지"""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = _body_size(last)
    lower = _lower_shadow(last)
    upper = _upper_shadow(last)

    if body == 0:
        return None

    vf = _volume_factor(df)

    if _is_bearish(prev) and lower >= body * 2 and upper <= body * 0.3:
        return CandlePatternResult(
            name="해머 (Hammer)",
            signal="long",
            strength=min(0.95, 0.7 * vf),
            description="하락 추세 후 해머 패턴 - 반등 가능성"
        )

    if _is_bullish(prev) and upper >= body * 2 and lower <= body * 0.3:
        return CandlePatternResult(
            name="행잉맨 (Hanging Man)",
            signal="short",
            strength=min(0.95, 0.7 * vf),
            description="상승 추세 후 행잉맨 패턴 - 하락 전환 가능성"
        )
    return None


def detect_engulfing(df: pd.DataFrame) -> CandlePatternResult | None:
    """잉걸핑 패턴 감지"""
    last = df.iloc[-1]
    prev = df.iloc[-2]

    last_body = _body_size(last)
    prev_body = _body_size(prev)

    if prev_body == 0:
        return None

    vf = _volume_factor(df)

    if (_is_bearish(prev) and _is_bullish(last) and
            last["open"] <= prev["close"] and last["close"] >= prev["open"] and
            last_body > prev_body):
        return CandlePatternResult(
            name="불리시 잉걸핑 (Bullish Engulfing)",
            signal="long",
            strength=min(0.95, 0.8 * vf),
            description="강한 상승 전환 시그널"
        )

    if (_is_bullish(prev) and _is_bearish(last) and
            last["open"] >= prev["close"] and last["close"] <= prev["open"] and
            last_body > prev_body):
        return CandlePatternResult(
            name="베어리시 잉걸핑 (Bearish Engulfing)",
            signal="short",
            strength=min(0.95, 0.8 * vf),
            description="강한 하락 전환 시그널"
        )
    return None


def detect_morning_evening_star(df: pd.DataFrame) -> CandlePatternResult | None:
    """모닝스타 / 이브닝스타 패턴 감지 (3캔들 패턴)"""
    if len(df) < 3:
        return None

    first = df.iloc[-3]
    second = df.iloc[-2]
    third = df.iloc[-1]

    first_body = _body_size(first)
    second_body = _body_size(second)
    third_body = _body_size(third)

    if first_body == 0:
        return None

    # 3봉 패턴: 마지막 봉(확인봉)의 거래량 확인
    vf = _volume_factor(df)

    if (_is_bearish(first) and second_body < first_body * 0.3 and
            _is_bullish(third) and third_body > first_body * 0.5):
        return CandlePatternResult(
            name="모닝스타 (Morning Star)",
            signal="long",
            strength=min(0.95, 0.85 * vf),
            description="강한 바닥 반전 패턴 - 상승 전환 기대"
        )

    if (_is_bullish(first) and second_body < first_body * 0.3 and
            _is_bearish(third) and third_body > first_body * 0.5):
        return CandlePatternResult(
            name="이브닝스타 (Evening Star)",
            signal="short",
            strength=min(0.95, 0.85 * vf),
            description="강한 천정 반전 패턴 - 하락 전환 기대"
        )
    return None


def detect_three_soldiers_crows(df: pd.DataFrame) -> CandlePatternResult | None:
    """적삼병 / 흑삼병 패턴 감지"""
    if len(df) < 3:
        return None

    candles = [df.iloc[-3], df.iloc[-2], df.iloc[-1]]

    all_bullish = all(_is_bullish(c) for c in candles)
    rising_closes = candles[0]["close"] < candles[1]["close"] < candles[2]["close"]

    # 3봉 연속 패턴: 마지막 봉 거래량 확인
    vf = _volume_factor(df)

    if all_bullish and rising_closes:
        return CandlePatternResult(
            name="적삼병 (Three White Soldiers)",
            signal="long",
            strength=min(0.95, 0.85 * vf),
            description="강한 상승 모멘텀 - 연속 3양봉"
        )

    all_bearish = all(_is_bearish(c) for c in candles)
    falling_closes = candles[0]["close"] > candles[1]["close"] > candles[2]["close"]

    if all_bearish and falling_closes:
        return CandlePatternResult(
            name="흑삼병 (Three Black Crows)",
            signal="short",
            strength=min(0.95, 0.85 * vf),
            description="강한 하락 모멘텀 - 연속 3음봉"
        )
    return None


def analyze_candle_patterns(df: pd.DataFrame) -> List[CandlePatternResult]:
    """모든 캔들 패턴을 분석하고 감지된 패턴 목록 반환"""
    if len(df) < 3:
        return []

    detectors = [
        detect_doji,
        detect_hammer,
        detect_engulfing,
        detect_morning_evening_star,
        detect_three_soldiers_crows,
    ]

    patterns = []
    for detector in detectors:
        try:
            result = detector(df)
            if result is not None:
                patterns.append(result)
        except Exception as e:
            logger.error("캔들 패턴 감지 오류 (%s): %s", detector.__name__, e, exc_info=True)

    return patterns

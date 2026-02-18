"""
캔들스틱 패턴 인식 모듈
도지, 해머, 잉걸핑, 모닝스타, 이브닝스타 등
"""
import logging
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
        return CandlePatternResult(
            name="도지 (Doji)",
            signal="neutral",
            strength=0.5,
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

    if _is_bearish(prev) and lower >= body * 2 and upper <= body * 0.3:
        return CandlePatternResult(
            name="해머 (Hammer)",
            signal="long",
            strength=0.7,
            description="하락 추세 후 해머 패턴 - 반등 가능성"
        )

    if _is_bullish(prev) and upper >= body * 2 and lower <= body * 0.3:
        return CandlePatternResult(
            name="행잉맨 (Hanging Man)",
            signal="short",
            strength=0.7,
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

    if (_is_bearish(prev) and _is_bullish(last) and
            last["open"] <= prev["close"] and last["close"] >= prev["open"] and
            last_body > prev_body):
        return CandlePatternResult(
            name="불리시 잉걸핑 (Bullish Engulfing)",
            signal="long",
            strength=0.8,
            description="강한 상승 전환 시그널"
        )

    if (_is_bullish(prev) and _is_bearish(last) and
            last["open"] >= prev["close"] and last["close"] <= prev["open"] and
            last_body > prev_body):
        return CandlePatternResult(
            name="베어리시 잉걸핑 (Bearish Engulfing)",
            signal="short",
            strength=0.8,
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

    if (_is_bearish(first) and second_body < first_body * 0.3 and
            _is_bullish(third) and third_body > first_body * 0.5):
        return CandlePatternResult(
            name="모닝스타 (Morning Star)",
            signal="long",
            strength=0.85,
            description="강한 바닥 반전 패턴 - 상승 전환 기대"
        )

    if (_is_bullish(first) and second_body < first_body * 0.3 and
            _is_bearish(third) and third_body > first_body * 0.5):
        return CandlePatternResult(
            name="이브닝스타 (Evening Star)",
            signal="short",
            strength=0.85,
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

    if all_bullish and rising_closes:
        return CandlePatternResult(
            name="적삼병 (Three White Soldiers)",
            signal="long",
            strength=0.85,
            description="강한 상승 모멘텀 - 연속 3양봉"
        )

    all_bearish = all(_is_bearish(c) for c in candles)
    falling_closes = candles[0]["close"] > candles[1]["close"] > candles[2]["close"]

    if all_bearish and falling_closes:
        return CandlePatternResult(
            name="흑삼병 (Three Black Crows)",
            signal="short",
            strength=0.85,
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

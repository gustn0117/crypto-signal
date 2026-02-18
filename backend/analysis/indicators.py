"""
기술적 지표 분석 모듈
RSI, MACD, 볼린저밴드, EMA, Stochastic 등 기본 지표 계산
"""
import logging
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class IndicatorResult:
    """개별 지표 분석 결과"""
    name: str
    signal: str  # "long", "short", "neutral"
    strength: float  # 0.0 ~ 1.0
    value: float
    description: str


def analyze_rsi(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """RSI (Relative Strength Index) 분석"""
    try:
        rsi = ta.rsi(df["close"], length=period)
        if rsi is None or rsi.empty:
            logger.warning("RSI 계산 결과 없음 (데이터: %d행)", len(df))
            return IndicatorResult("RSI", "neutral", 0.0, 0.0, "데이터 부족")

        current_rsi = rsi.iloc[-1]

        if current_rsi <= 30:
            signal = "long"
            strength = (30 - current_rsi) / 30
            desc = f"RSI {current_rsi:.1f} - 과매도 구간 (롱 기회)"
        elif current_rsi >= 70:
            signal = "short"
            strength = (current_rsi - 70) / 30
            desc = f"RSI {current_rsi:.1f} - 과매수 구간 (숏 기회)"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"RSI {current_rsi:.1f} - 중립 구간"

        return IndicatorResult("RSI", signal, min(strength, 1.0), current_rsi, desc)
    except Exception as e:
        logger.error("RSI 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("RSI", "neutral", 0.0, 0.0, f"분석 오류")


def analyze_macd(df: pd.DataFrame) -> IndicatorResult:
    """MACD 분석 (크로스오버 + 히스토그램)"""
    try:
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is None or macd_df.empty:
            logger.warning("MACD 계산 결과 없음 (데이터: %d행)", len(df))
            return IndicatorResult("MACD", "neutral", 0.0, 0.0, "데이터 부족")

        macd_line = macd_df.iloc[:, 0]
        signal_line = macd_df.iloc[:, 1]
        histogram = macd_df.iloc[:, 2]

        curr_macd = macd_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        curr_signal = signal_line.iloc[-1]
        prev_signal = signal_line.iloc[-2]
        curr_hist = histogram.iloc[-1]

        # 골든 크로스
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            signal = "long"
            strength = 0.8
            desc = "MACD 골든크로스 발생 (강한 롱 시그널)"
        # 데드 크로스
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            signal = "short"
            strength = 0.8
            desc = "MACD 데드크로스 발생 (강한 숏 시그널)"
        elif curr_hist > 0:
            signal = "long"
            strength = min(abs(curr_hist) / abs(curr_macd + 1e-10) * 0.5, 0.5)
            desc = f"MACD 히스토그램 양수 ({curr_hist:.4f})"
        elif curr_hist < 0:
            signal = "short"
            strength = min(abs(curr_hist) / abs(curr_macd + 1e-10) * 0.5, 0.5)
            desc = f"MACD 히스토그램 음수 ({curr_hist:.4f})"
        else:
            signal = "neutral"
            strength = 0.0
            desc = "MACD 중립"

        return IndicatorResult("MACD", signal, strength, curr_macd, desc)
    except Exception as e:
        logger.error("MACD 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("MACD", "neutral", 0.0, 0.0, f"분석 오류")


def analyze_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> IndicatorResult:
    """볼린저밴드 분석"""
    try:
        bbands = ta.bbands(df["close"], length=period, std=std)
        if bbands is None or bbands.empty:
            logger.warning("BB 계산 결과 없음 (데이터: %d행)", len(df))
            return IndicatorResult("BB", "neutral", 0.0, 0.0, "데이터 부족")

        lower = bbands.iloc[:, 0].iloc[-1]
        upper = bbands.iloc[:, 2].iloc[-1]
        current_price = df["close"].iloc[-1]

        band_width = upper - lower
        if band_width == 0:
            return IndicatorResult("BB", "neutral", 0.0, current_price, "밴드 폭 0")

        position = (current_price - lower) / band_width

        if position <= 0.05:
            signal = "long"
            strength = 0.9
            desc = f"가격이 하단밴드 터치 (강한 반등 기대)"
        elif position <= 0.2:
            signal = "long"
            strength = 0.5
            desc = f"가격이 하단밴드 근접"
        elif position >= 0.95:
            signal = "short"
            strength = 0.9
            desc = f"가격이 상단밴드 터치 (하락 전환 가능)"
        elif position >= 0.8:
            signal = "short"
            strength = 0.5
            desc = f"가격이 상단밴드 근접"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"가격이 밴드 중간 위치 ({position:.0%})"

        return IndicatorResult("BB", signal, strength, current_price, desc)
    except Exception as e:
        logger.error("BB 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("BB", "neutral", 0.0, 0.0, f"분석 오류")


def analyze_ema_cross(df: pd.DataFrame, short_period: int = 9, long_period: int = 21) -> IndicatorResult:
    """EMA 크로스 분석"""
    try:
        ema_short = ta.ema(df["close"], length=short_period)
        ema_long = ta.ema(df["close"], length=long_period)

        if ema_short is None or ema_long is None:
            logger.warning("EMA 계산 결과 없음 (데이터: %d행)", len(df))
            return IndicatorResult("EMA", "neutral", 0.0, 0.0, "데이터 부족")

        curr_short = ema_short.iloc[-1]
        prev_short = ema_short.iloc[-2]
        curr_long = ema_long.iloc[-1]
        prev_long = ema_long.iloc[-2]

        if prev_short <= prev_long and curr_short > curr_long:
            signal = "long"
            strength = 0.7
            desc = f"EMA{short_period}/{long_period} 골든크로스"
        elif prev_short >= prev_long and curr_short < curr_long:
            signal = "short"
            strength = 0.7
            desc = f"EMA{short_period}/{long_period} 데드크로스"
        elif curr_short > curr_long:
            signal = "long"
            strength = 0.3
            desc = f"EMA{short_period} > EMA{long_period} (상승 추세)"
        else:
            signal = "short"
            strength = 0.3
            desc = f"EMA{short_period} < EMA{long_period} (하락 추세)"

        return IndicatorResult("EMA", signal, strength, curr_short, desc)
    except Exception as e:
        logger.error("EMA 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("EMA", "neutral", 0.0, 0.0, f"분석 오류")


def analyze_stochastic(df: pd.DataFrame) -> IndicatorResult:
    """스토캐스틱 분석"""
    try:
        stoch = ta.stoch(df["high"], df["low"], df["close"])
        if stoch is None or stoch.empty:
            logger.warning("STOCH 계산 결과 없음 (데이터: %d행)", len(df))
            return IndicatorResult("STOCH", "neutral", 0.0, 0.0, "데이터 부족")

        k = stoch.iloc[:, 0].iloc[-1]
        d = stoch.iloc[:, 1].iloc[-1]

        if k <= 20 and d <= 20:
            signal = "long"
            strength = 0.7
            desc = f"스토캐스틱 과매도 (K:{k:.1f}, D:{d:.1f})"
        elif k >= 80 and d >= 80:
            signal = "short"
            strength = 0.7
            desc = f"스토캐스틱 과매수 (K:{k:.1f}, D:{d:.1f})"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"스토캐스틱 중립 (K:{k:.1f}, D:{d:.1f})"

        return IndicatorResult("STOCH", signal, strength, k, desc)
    except Exception as e:
        logger.error("STOCH 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("STOCH", "neutral", 0.0, 0.0, f"분석 오류")

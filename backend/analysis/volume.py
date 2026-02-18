"""
거래량 분석 모듈
거래량 급증, OBV, VWAP 등
"""
import logging
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VolumeResult:
    """거래량 분석 결과"""
    name: str
    signal: str
    strength: float
    value: float
    description: str


def analyze_volume(df: pd.DataFrame) -> list[VolumeResult]:
    """종합 거래량 분석"""
    results = []

    try:
        vol_surge = _detect_volume_surge(df)
        if vol_surge:
            results.append(vol_surge)
    except Exception as e:
        logger.error("거래량 급증 분석 오류: %s", e, exc_info=True)

    try:
        obv_result = _analyze_obv(df)
        if obv_result:
            results.append(obv_result)
    except Exception as e:
        logger.error("OBV 분석 오류: %s", e, exc_info=True)

    try:
        divergence = _detect_price_volume_divergence(df)
        if divergence:
            results.append(divergence)
    except Exception as e:
        logger.error("거래량 다이버전스 분석 오류: %s", e, exc_info=True)

    return results


def _detect_volume_surge(df: pd.DataFrame, lookback: int = 20, threshold: float = 2.0) -> VolumeResult | None:
    """거래량 급증 감지 (평균 대비)"""
    if len(df) < lookback:
        return None

    avg_volume = df["volume"].iloc[-lookback - 1:-1].mean()
    current_volume = df["volume"].iloc[-1]

    if avg_volume == 0:
        return None

    ratio = current_volume / avg_volume

    if ratio >= threshold:
        is_bullish = df["close"].iloc[-1] > df["open"].iloc[-1]
        signal = "long" if is_bullish else "short"
        strength = min(ratio / 5.0, 1.0)
        direction = "상승" if is_bullish else "하락"

        return VolumeResult(
            name="거래량 급증",
            signal=signal,
            strength=strength,
            value=ratio,
            description=f"거래량 {ratio:.1f}배 급증 + {direction}봉 → {signal.upper()} 시그널"
        )
    return None


def _analyze_obv(df: pd.DataFrame) -> VolumeResult | None:
    """OBV 트렌드 분석"""
    obv = ta.obv(df["close"], df["volume"])
    if obv is None or len(obv) < 10:
        return None

    obv_sma = obv.rolling(10).mean()
    curr_obv = obv.iloc[-1]
    curr_sma = obv_sma.iloc[-1]
    prev_obv = obv.iloc[-2]
    prev_sma = obv_sma.iloc[-2]

    if pd.isna(curr_sma) or pd.isna(prev_sma):
        return None

    if prev_obv <= prev_sma and curr_obv > curr_sma:
        return VolumeResult(
            name="OBV",
            signal="long",
            strength=0.6,
            value=curr_obv,
            description="OBV가 이동평균 상향 돌파 - 매수세 유입"
        )
    elif prev_obv >= prev_sma and curr_obv < curr_sma:
        return VolumeResult(
            name="OBV",
            signal="short",
            strength=0.6,
            value=curr_obv,
            description="OBV가 이동평균 하향 돌파 - 매도세 유입"
        )
    return None


def _detect_price_volume_divergence(df: pd.DataFrame, lookback: int = 5) -> VolumeResult | None:
    """가격-거래량 다이버전스 감지"""
    if len(df) < lookback + 1:
        return None

    recent = df.iloc[-lookback:]
    price_change = (recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0]
    vol_change = (recent["volume"].iloc[-1] - recent["volume"].iloc[0]) / (recent["volume"].iloc[0] + 1e-10)

    if price_change > 0.02 and vol_change < -0.3:
        return VolumeResult(
            name="거래량 다이버전스",
            signal="short",
            strength=0.65,
            value=vol_change,
            description=f"가격 상승({price_change:.1%}) but 거래량 감소({vol_change:.1%}) - 상승 약화"
        )

    if price_change < -0.02 and vol_change < -0.3:
        return VolumeResult(
            name="거래량 다이버전스",
            signal="long",
            strength=0.65,
            value=vol_change,
            description=f"가격 하락({price_change:.1%}) + 거래량 감소({vol_change:.1%}) - 하락 약화"
        )

    return None

"""
거래량 분석 모듈
거래량 급증, OBV, 가격-거래량 다이버전스, VWAP 이탈, 거래량 프로파일, 거래량 MA 크로스
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
    """종합 거래량 분석 (6개 분석)"""
    results = []

    for analyzer in [
        _detect_volume_surge,
        _analyze_obv,
        _detect_price_volume_divergence,
        _analyze_vwap_deviation,
        _analyze_volume_profile,
        _analyze_volume_ma_cross,
    ]:
        try:
            result = analyzer(df)
            if result:
                results.append(result)
        except Exception as e:
            logger.error("%s 분석 오류: %s", analyzer.__name__, e, exc_info=True)

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


def _analyze_vwap_deviation(df: pd.DataFrame) -> VolumeResult | None:
    """VWAP 이탈 — 가격이 VWAP 위/아래로 크게 벗어났을 때"""
    if len(df) < 20:
        return None

    vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    if vwap is None or vwap.empty:
        return None

    current_price = df["close"].iloc[-1]
    current_vwap = float(vwap.dropna().iloc[-1])

    if current_vwap == 0:
        return None

    deviation = (current_price - current_vwap) / current_vwap * 100

    # 큰 이탈만 시그널 (±3% 이상)
    if deviation > 3.0:
        strength = min(deviation / 6.0, 0.8)
        return VolumeResult(
            name="VWAP 이탈",
            signal="short",
            strength=strength,
            value=deviation,
            description=f"가격이 VWAP 위 +{deviation:.1f}% — 평균 회귀 가능 (숏)"
        )
    elif deviation < -3.0:
        strength = min(abs(deviation) / 6.0, 0.8)
        return VolumeResult(
            name="VWAP 이탈",
            signal="long",
            strength=strength,
            value=deviation,
            description=f"가격이 VWAP 아래 {deviation:.1f}% — 평균 회귀 가능 (롱)"
        )

    return None


def _analyze_volume_profile(df: pd.DataFrame, lookback: int = 50) -> VolumeResult | None:
    """거래량 프로파일 — 고점/저점 구간의 거래량 분포"""
    if len(df) < lookback:
        return None

    recent = df.iloc[-lookback:]
    current_price = recent["close"].iloc[-1]

    # 가격 범위를 10등분
    price_range = recent["high"].max() - recent["low"].min()
    if price_range == 0:
        return None

    # 현재 가격이 전체 범위의 어디에 있는지
    position = (current_price - recent["low"].min()) / price_range

    # 상위 30% / 하위 30% 구간 거래량 비교
    high_threshold = recent["low"].min() + price_range * 0.7
    low_threshold = recent["low"].min() + price_range * 0.3

    high_zone_vol = recent[recent["close"] >= high_threshold]["volume"].sum()
    low_zone_vol = recent[recent["close"] <= low_threshold]["volume"].sum()
    total_vol = recent["volume"].sum()

    if total_vol == 0:
        return None

    high_ratio = high_zone_vol / total_vol
    low_ratio = low_zone_vol / total_vol

    # 현재 가격이 저거래량 구간에 있으면 브레이크아웃 가능
    if position > 0.7 and high_ratio < 0.15:
        return VolumeResult(
            name="거래량 프로파일",
            signal="long",
            strength=0.5,
            value=high_ratio,
            description=f"고점 구간 저거래량 ({high_ratio:.0%}) — 저항 약함 (브레이크아웃 가능)"
        )
    elif position < 0.3 and low_ratio < 0.15:
        return VolumeResult(
            name="거래량 프로파일",
            signal="short",
            strength=0.5,
            value=low_ratio,
            description=f"저점 구간 저거래량 ({low_ratio:.0%}) — 지지 약함 (브레이크다운 가능)"
        )

    return None


def _analyze_volume_ma_cross(df: pd.DataFrame, short_period: int = 5, long_period: int = 20) -> VolumeResult | None:
    """거래량 이동평균 크로스 — 단기 vol MA > 장기 vol MA"""
    if len(df) < long_period + 2:
        return None

    vol = df["volume"]
    vol_short = vol.rolling(short_period).mean()
    vol_long = vol.rolling(long_period).mean()

    curr_short = vol_short.iloc[-1]
    prev_short = vol_short.iloc[-2]
    curr_long = vol_long.iloc[-1]
    prev_long = vol_long.iloc[-2]

    if pd.isna(curr_short) or pd.isna(curr_long) or pd.isna(prev_short) or pd.isna(prev_long):
        return None

    # 골든크로스: 단기 > 장기 전환
    if prev_short <= prev_long and curr_short > curr_long:
        is_bullish = df["close"].iloc[-1] > df["close"].iloc[-2]
        signal = "long" if is_bullish else "short"
        ratio = curr_short / curr_long if curr_long > 0 else 1.0
        return VolumeResult(
            name="거래량 MA 크로스",
            signal=signal,
            strength=min(ratio / 2.0, 0.7),
            value=ratio,
            description=f"거래량 MA{short_period} > MA{long_period} ({ratio:.1f}배) — 거래 활성화"
        )

    return None

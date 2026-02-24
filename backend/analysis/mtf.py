"""
멀티 타임프레임 분석 모듈
상위 타임프레임의 추세를 확인하여 시그널 신뢰도 조정
"""
import logging
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# 상위 TF 매핑 (config에서도 정의하지만 여기서도 기본값)
HIGHER_TF_MAP = {
    "1m": "5m", "5m": "15m", "15m": "1h",
    "30m": "4h", "1h": "4h", "4h": "1d", "1d": "1d",
}

# 2단계 상위 TF 매핑 (한 단계 더 위)
SECOND_HIGHER_TF_MAP = {
    "1m": "15m", "5m": "1h", "15m": "4h",
    "30m": "1d", "1h": "1d", "4h": "1d", "1d": "1d",
}


@dataclass
class MTFConfirmation:
    """멀티 타임프레임 확인 결과"""
    higher_tf: str
    higher_tf_trend: str        # "bullish", "bearish", "neutral"
    alignment: str              # "aligned", "opposed", "neutral"
    confidence_modifier: float  # -0.2 ~ +0.15
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


def check_higher_tf(
    higher_tf_df: pd.DataFrame,
    signal_direction: str,
    higher_tf: str = "",
) -> Optional[MTFConfirmation]:
    """
    상위 타임프레임 추세 확인 (MACD + ADX + EMA 기반)

    방법:
    1. MACD 히스토그램 방향 → 추세 방향 (주)
    2. ADX > 25 → 강한 추세 여부
    3. DI+/DI- 비교 → 보조 방향
    4. EMA(21) 기울기 → 보조 확인

    보정값:
    - 정렬 + 강한 추세(ADX>25): +0.20
    - 정렬 + 약한 추세(ADX<25): +0.10
    - 반대 + 강한 추세: -0.25
    - 반대 + 약한 추세: -0.15

    signal_direction: "long" 또는 "short" (현재 TF의 시그널 방향)
    """
    if higher_tf_df is None or len(higher_tf_df) < 50:
        return None

    try:
        close = higher_tf_df["close"]
        high = higher_tf_df["high"]
        low = higher_tf_df["low"]

        # 1) MACD 히스토그램 방향
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is None or macd_df.empty:
            return None

        histogram = macd_df.iloc[:, 2]
        hist_vals = histogram.dropna()
        if len(hist_vals) < 2:
            return None

        macd_bullish = float(hist_vals.iloc[-1]) > 0

        # 2) ADX + DI+/DI- (B4: ADX 등급별 차등 보정)
        adx_df = ta.adx(high, low, close, length=14)
        adx_val = 0.0
        adx_grade = "none"  # "none"(<15), "weak"(15-25), "strong"(25-40), "extreme"(>40)
        di_bullish = None

        if adx_df is not None and not adx_df.empty:
            adx_col = [c for c in adx_df.columns if "ADX" in c and "DM" not in c]
            dmp_col = [c for c in adx_df.columns if "DMP" in c]
            dmn_col = [c for c in adx_df.columns if "DMN" in c]

            if adx_col and dmp_col and dmn_col:
                adx_val = float(adx_df[adx_col[0]].dropna().iloc[-1])
                dmp = float(adx_df[dmp_col[0]].dropna().iloc[-1])
                dmn = float(adx_df[dmn_col[0]].dropna().iloc[-1])
                di_bullish = dmp > dmn
                # B4: ADX 등급 분류
                if adx_val >= 40:
                    adx_grade = "extreme"
                elif adx_val >= 25:
                    adx_grade = "strong"
                elif adx_val >= 15:
                    adx_grade = "weak"
                else:
                    adx_grade = "none"

        # 3) EMA(21) 기울기 (보조)
        ema21 = ta.ema(close, length=21)
        ema_rising = None
        if ema21 is not None and len(ema21.dropna()) >= 4:
            ema_rising = float(ema21.iloc[-1]) > float(ema21.iloc[-3])

        # 종합 추세 판단: MACD(주) + DI(보조) + EMA(보조)
        bullish_votes = 0
        bearish_votes = 0

        # MACD (가중치 2)
        if macd_bullish:
            bullish_votes += 2
        else:
            bearish_votes += 2

        # DI (가중치 1)
        if di_bullish is True:
            bullish_votes += 1
        elif di_bullish is False:
            bearish_votes += 1

        # EMA (가중치 1)
        if ema_rising is True:
            bullish_votes += 1
        elif ema_rising is False:
            bearish_votes += 1

        if bullish_votes > bearish_votes:
            trend = "bullish"
            trend_desc = "상승 추세"
        elif bearish_votes > bullish_votes:
            trend = "bearish"
            trend_desc = "하락 추세"
        else:
            trend = "neutral"
            trend_desc = "횡보"

        # 정렬 판단 + B4: ADX 등급별 차등 보정
        is_long_signal = signal_direction in ("long", "LONG", "STRONG_LONG")
        is_short_signal = signal_direction in ("short", "SHORT", "STRONG_SHORT")

        # B4: ADX 등급별 보정값 테이블
        #   none(<15): 추세 없음 → 약한 보정
        #   weak(15-25): 약한 추세 → 보통 보정
        #   strong(25-40): 강한 추세 → 강한 보정
        #   extreme(>40): 극강 추세 → 최대 보정
        aligned_mod = {"none": 0.05, "weak": 0.10, "strong": 0.20, "extreme": 0.25}
        opposed_mod = {"none": -0.10, "weak": -0.15, "strong": -0.25, "extreme": -0.30}

        adx_label = {"none": "무추세", "weak": "약", "strong": "강", "extreme": "극강"}
        adx_info = f"ADX {adx_label.get(adx_grade, '?')}({adx_val:.0f})"

        if trend == "bullish" and is_long_signal:
            alignment = "aligned"
            modifier = aligned_mod.get(adx_grade, 0.10)
            desc = f"{higher_tf} {trend_desc}({adx_info}) - 롱과 정렬 (신뢰도 +{modifier:.0%})"
        elif trend == "bearish" and is_short_signal:
            alignment = "aligned"
            modifier = aligned_mod.get(adx_grade, 0.10)
            desc = f"{higher_tf} {trend_desc}({adx_info}) - 숏과 정렬 (신뢰도 +{modifier:.0%})"
        elif trend == "bullish" and is_short_signal:
            alignment = "opposed"
            modifier = opposed_mod.get(adx_grade, -0.15)
            desc = f"{higher_tf} {trend_desc}({adx_info}) - 숏과 반대 (신뢰도 {modifier:+.0%})"
        elif trend == "bearish" and is_long_signal:
            alignment = "opposed"
            modifier = opposed_mod.get(adx_grade, -0.15)
            desc = f"{higher_tf} {trend_desc}({adx_info}) - 롱과 반대 (신뢰도 {modifier:+.0%})"
        else:
            alignment = "neutral"
            # B4: ADX 무추세(<15)면 마이너스 보정
            modifier = -0.05 if adx_grade == "none" else 0.0
            desc = f"{higher_tf} {trend_desc}({adx_info}) - 추세 불명확"

        return MTFConfirmation(
            higher_tf=higher_tf,
            higher_tf_trend=trend,
            alignment=alignment,
            confidence_modifier=modifier,
            description=desc,
        )
    except Exception as e:
        logger.error("MTF 분석 오류: %s", e, exc_info=True)
        return None


def check_multi_tf(
    higher_tf_df: Optional[pd.DataFrame],
    second_tf_df: Optional[pd.DataFrame],
    signal_direction: str,
    higher_tf: str = "",
    second_tf: str = "",
) -> Optional[MTFConfirmation]:
    """
    2단계 멀티 타임프레임 확인.
    1차 상위 TF (가중치 1.0) + 2차 상위 TF (가중치 0.5) 합산.
    최대 보정값: ±0.30
    """
    result1 = check_higher_tf(higher_tf_df, signal_direction, higher_tf)
    result2 = check_higher_tf(second_tf_df, signal_direction, second_tf)

    if result1 is None and result2 is None:
        return None

    mod1 = result1.confidence_modifier if result1 else 0.0
    mod2 = (result2.confidence_modifier * 0.5) if result2 else 0.0
    total_mod = max(-0.30, min(0.30, mod1 + mod2))

    # 기본 결과는 1차 상위 TF 기준, 없으면 2차
    base = result1 or result2
    desc_parts = []
    if result1:
        desc_parts.append(f"1차({higher_tf}): {result1.alignment}")
    if result2:
        desc_parts.append(f"2차({second_tf}): {result2.alignment}")
    desc = f"멀티TF [{', '.join(desc_parts)}] 보정={total_mod:+.2f}"

    return MTFConfirmation(
        higher_tf=base.higher_tf,
        higher_tf_trend=base.higher_tf_trend,
        alignment=base.alignment,
        confidence_modifier=total_mod,
        description=desc,
    )

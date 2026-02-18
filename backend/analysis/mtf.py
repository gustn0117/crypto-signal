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
    상위 타임프레임 추세 확인

    방법:
    1. EMA(21) 방향: 현재 EMA > 이전 EMA → bullish
    2. 가격 위치: 종가가 EMA(50) 위 → bullish

    signal_direction: "long" 또는 "short" (현재 TF의 시그널 방향)
    """
    if higher_tf_df is None or len(higher_tf_df) < 50:
        return None

    try:
        close = higher_tf_df["close"]

        # EMA(21) 추세 방향
        ema21 = ta.ema(close, length=21)
        if ema21 is None or len(ema21) < 2:
            return None

        ema21_rising = ema21.iloc[-1] > ema21.iloc[-3] if len(ema21) >= 4 else ema21.iloc[-1] > ema21.iloc[-2]

        # EMA(50) 대비 가격 위치
        ema50 = ta.ema(close, length=50)
        if ema50 is None or pd.isna(ema50.iloc[-1]):
            return None

        price_above_ema50 = close.iloc[-1] > ema50.iloc[-1]

        # 추세 판단
        if ema21_rising and price_above_ema50:
            trend = "bullish"
            trend_desc = "상승 추세"
        elif not ema21_rising and not price_above_ema50:
            trend = "bearish"
            trend_desc = "하락 추세"
        else:
            trend = "neutral"
            trend_desc = "횡보"

        # 정렬 판단
        is_long_signal = signal_direction in ("long", "LONG", "STRONG_LONG")
        is_short_signal = signal_direction in ("short", "SHORT", "STRONG_SHORT")

        if trend == "bullish" and is_long_signal:
            alignment = "aligned"
            modifier = 0.15
            desc = f"{higher_tf} {trend_desc} - 롱 시그널과 정렬 (신뢰도 +15%)"
        elif trend == "bearish" and is_short_signal:
            alignment = "aligned"
            modifier = 0.15
            desc = f"{higher_tf} {trend_desc} - 숏 시그널과 정렬 (신뢰도 +15%)"
        elif trend == "bullish" and is_short_signal:
            alignment = "opposed"
            modifier = -0.2
            desc = f"{higher_tf} {trend_desc} - 숏 시그널과 반대 (신뢰도 -20%)"
        elif trend == "bearish" and is_long_signal:
            alignment = "opposed"
            modifier = -0.2
            desc = f"{higher_tf} {trend_desc} - 롱 시그널과 반대 (신뢰도 -20%)"
        else:
            alignment = "neutral"
            modifier = 0.0
            desc = f"{higher_tf} {trend_desc} - 추세 불명확"

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

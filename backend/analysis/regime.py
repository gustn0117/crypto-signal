"""
시장 레짐 감지 모듈
ADX, 볼린저 밴드폭, ATR 비율을 활용하여 현재 시장 상태를 분류
"""
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


@dataclass
class MarketRegime:
    regime: str  # TRENDING_UP / TRENDING_DOWN / RANGING / VOLATILE
    adx_value: float
    bb_width_pct: float
    volatility_rank: float  # 0~1
    description: str


def detect_regime(df: pd.DataFrame) -> MarketRegime:
    """DataFrame에서 시장 레짐을 감지한다."""
    if len(df) < 60:
        return MarketRegime("UNKNOWN", 0, 0, 0.5, "데이터 부족")

    try:
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # 1. ADX(14) - 추세 강도
        adx_df = ta.adx(high, low, close, length=14)
        adx_value = 0.0
        if adx_df is not None and not adx_df.empty:
            adx_col = [c for c in adx_df.columns if "ADX" in c and "DM" not in c]
            if adx_col:
                adx_value = float(adx_df[adx_col[0]].dropna().iloc[-1])

        # 2. 볼린저 밴드폭
        bbands = ta.bbands(close, length=20, std=2.0)
        bb_width_pct = 0.0
        avg_bb_width = 0.0
        if bbands is not None and not bbands.empty:
            upper_col = [c for c in bbands.columns if "BBU" in c]
            lower_col = [c for c in bbands.columns if "BBL" in c]
            mid_col = [c for c in bbands.columns if "BBM" in c]
            if upper_col and lower_col and mid_col:
                bb_upper = bbands[upper_col[0]]
                bb_lower = bbands[lower_col[0]]
                bb_mid = bbands[mid_col[0]]
                bb_width = (bb_upper - bb_lower) / bb_mid * 100
                bb_width_pct = float(bb_width.dropna().iloc[-1])
                avg_bb_width = float(bb_width.rolling(50, min_periods=20).mean().dropna().iloc[-1])

        # 3. ATR 비율: 현재 ATR / 50기간 평균 ATR
        atr = ta.atr(high, low, close, length=14)
        atr_ratio = 1.0
        if atr is not None and not atr.empty:
            current_atr = float(atr.dropna().iloc[-1])
            avg_atr = float(atr.rolling(50, min_periods=20).mean().dropna().iloc[-1])
            atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

        # 4. EMA(21) 기울기 - 추세 방향
        ema21 = ta.ema(close, length=21)
        ema_slope = 0.0
        if ema21 is not None and not ema21.empty:
            ema_vals = ema21.dropna()
            if len(ema_vals) >= 6:
                ema_slope = (float(ema_vals.iloc[-1]) - float(ema_vals.iloc[-5])) / float(ema_vals.iloc[-5]) * 100

        # 5. 변동성 순위
        volatility_rank = min(atr_ratio / 2.0, 1.0)

        # 6. 레짐 분류
        if adx_value >= 25:
            if ema_slope > 0:
                regime = "TRENDING_UP"
                desc = f"상승 추세 (ADX={adx_value:.1f}, EMA기울기={ema_slope:+.2f}%)"
            else:
                regime = "TRENDING_DOWN"
                desc = f"하락 추세 (ADX={adx_value:.1f}, EMA기울기={ema_slope:+.2f}%)"
        elif atr_ratio > 1.5 or (avg_bb_width > 0 and bb_width_pct > avg_bb_width * 1.3):
            regime = "VOLATILE"
            desc = f"변동성 확대 (ATR비율={atr_ratio:.2f}, BB폭={bb_width_pct:.1f}%)"
        else:
            regime = "RANGING"
            desc = f"횡보 (ADX={adx_value:.1f}, ATR비율={atr_ratio:.2f})"

        return MarketRegime(regime, adx_value, bb_width_pct, volatility_rank, desc)

    except Exception as e:
        logger.warning("레짐 감지 실패: %s", e)
        return MarketRegime("UNKNOWN", 0, 0, 0.5, f"감지 오류: {e}")

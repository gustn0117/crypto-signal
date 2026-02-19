"""
시장 레짐 감지 모듈
ADX, 볼린저 밴드폭, ATR 비율, Keltner Channel을 활용하여 현재 시장 상태를 분류
soft scoring: 각 레짐에 확률 점수 부여
"""
import logging
from dataclasses import dataclass, field

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
    scores: dict = field(default_factory=dict)  # soft scoring: {"trending": 0.7, "volatile": 0.2, "ranging": 0.1}


def detect_regime(df: pd.DataFrame) -> MarketRegime:
    """DataFrame에서 시장 레짐을 감지한다 (soft scoring 포함)."""
    if len(df) < 60:
        return MarketRegime("UNKNOWN", 0, 0, 0.5, "데이터 부족",
                            {"trending": 0.33, "volatile": 0.33, "ranging": 0.34})

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
                ema_base = float(ema_vals.iloc[-5])
                if ema_base > 0 and not pd.isna(ema_base):
                    ema_slope = (float(ema_vals.iloc[-1]) - ema_base) / ema_base * 100

        # 5. Keltner Channel 폭 — 변동성 보조 지표
        kc_expansion = 1.0
        try:
            kc = ta.kc(high, low, close, length=20, scalar=1.5)
            if kc is not None and not kc.empty:
                kcu_col = [c for c in kc.columns if "KCU" in c]
                kcl_col = [c for c in kc.columns if "KCL" in c]
                kcm_col = [c for c in kc.columns if "KCB" in c or "KCM" in c]
                if kcu_col and kcl_col:
                    kc_upper = kc[kcu_col[0]]
                    kc_lower = kc[kcl_col[0]]
                    kc_mid = kc[kcm_col[0]] if kcm_col else (kc_upper + kc_lower) / 2
                    kc_width = (kc_upper - kc_lower) / kc_mid * 100
                    kc_width_clean = kc_width.dropna()
                    if len(kc_width_clean) >= 20:
                        curr_kc = float(kc_width_clean.iloc[-1])
                        avg_kc = float(kc_width_clean.rolling(50, min_periods=20).mean().dropna().iloc[-1])
                        kc_expansion = curr_kc / avg_kc if avg_kc > 0 else 1.0
        except Exception:
            pass  # KC 실패 시 기본값 유지

        # 6. 변동성 순위
        volatility_rank = min(atr_ratio / 2.0, 1.0)

        # 7. Soft Scoring — 각 레짐에 확률 점수
        trending_score = min(adx_value / 40.0, 1.0)
        volatile_score = min(atr_ratio / 2.0, 1.0) * min(kc_expansion, 1.5) / 1.5
        # BB폭이 평균 대비 크면 변동성 점수 부스트
        if avg_bb_width > 0 and bb_width_pct > avg_bb_width * 1.2:
            bb_excess = bb_width_pct / avg_bb_width - 1.0
            volatile_score = min(1.0, volatile_score + bb_excess * 0.3)
        ranging_score = max(0.0, 1.0 - max(trending_score, volatile_score))

        # 정규화
        total = trending_score + volatile_score + ranging_score
        if total > 0:
            trending_score /= total
            volatile_score /= total
            ranging_score /= total
        else:
            trending_score = volatile_score = ranging_score = 0.33

        scores = {
            "trending": round(trending_score, 3),
            "volatile": round(volatile_score, 3),
            "ranging": round(ranging_score, 3),
        }

        # 8. 레짐 분류 (최고 점수 기반, 하위 호환)
        if adx_value >= 25:
            if ema_slope > 0:
                regime = "TRENDING_UP"
                desc = f"상승 추세 (ADX={adx_value:.1f}, EMA기울기={ema_slope:+.2f}%)"
            else:
                regime = "TRENDING_DOWN"
                desc = f"하락 추세 (ADX={adx_value:.1f}, EMA기울기={ema_slope:+.2f}%)"
        elif atr_ratio > 1.5 or (avg_bb_width > 0 and bb_width_pct > avg_bb_width * 1.3) or kc_expansion > 1.4:
            regime = "VOLATILE"
            desc = f"변동성 확대 (ATR비율={atr_ratio:.2f}, BB폭={bb_width_pct:.1f}%, KC확장={kc_expansion:.2f})"
        else:
            regime = "RANGING"
            desc = f"횡보 (ADX={adx_value:.1f}, ATR비율={atr_ratio:.2f})"

        return MarketRegime(regime, adx_value, bb_width_pct, volatility_rank, desc, scores)

    except Exception as e:
        logger.warning("레짐 감지 실패: %s", e)
        return MarketRegime("UNKNOWN", 0, 0, 0.5, f"감지 오류: {e}",
                            {"trending": 0.33, "volatile": 0.33, "ranging": 0.34})

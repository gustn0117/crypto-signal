"""
트레이드 파라미터 계산 모듈
진입가, 손절(SL), 익절(TP), 리스크/리워드 비율
"""
import logging
import pandas as pd
from dataclasses import dataclass, asdict
from typing import Optional

from .levels import PriceLevels
from .indicators import TF_CATEGORY

logger = logging.getLogger(__name__)

# 타임프레임 카테고리별 ATR 배율
SL_ATR_MULT = {"scalp": 1.0, "swing": 1.5, "position": 2.0}
SL_MIN_ATR_FRAC = {"scalp": 0.3, "swing": 0.5, "position": 0.7}
SL_FLOOR_ATR_FRAC = {"scalp": 0.2, "swing": 0.3, "position": 0.4}

# 변동성 기반 TP R:R 배율
TP_RR_HIGH_VOL = (1.2, 2.4, 3.6)
TP_RR_LOW_VOL = (0.8, 1.6, 2.4)


# 트레일링 스톱 ATR 배율 (카테고리별)
TRAILING_ATR_MULT = {"scalp": 1.5, "swing": 2.0, "position": 2.5}

# 포지션 사이징 기준 ATR% (이 ATR%일 때 기본 포지션 비율)
POSITION_BASE_ATR_PCT = 2.5  # 기준점: ATR 2.5%일 때 기본 비율
POSITION_BASE_PCT = {"scalp": 3.0, "swing": 5.0, "position": 8.0}  # 기본 포지션 비율 (%)
POSITION_MIN_PCT = 1.0  # 최소 포지션 비율
POSITION_MAX_PCT = 15.0  # 최대 포지션 비율


def _calc_trailing_stop(atr: float, cat: str, atr_percent: float) -> float:
    """ATR 기반 트레일링 스톱 거리 계산. 변동성에 따라 조정."""
    base_mult = TRAILING_ATR_MULT.get(cat, 2.0)
    if atr_percent > 5.0:
        mult = base_mult + 0.5  # 고변동성: 더 넓은 트레일링
    elif atr_percent < 1.5:
        mult = max(1.0, base_mult - 0.3)  # 저변동성: 더 타이트한 트레일링
    else:
        mult = base_mult
    return atr * mult


def _calc_position_size_atr(atr_percent: float, cat: str) -> float:
    """변동성 기반 추천 포지션 사이즈 (% of capital).
    높은 변동성 → 작은 포지션, 낮은 변동성 → 큰 포지션.
    """
    base = POSITION_BASE_PCT.get(cat, 5.0)
    if atr_percent <= 0:
        return base
    ratio = POSITION_BASE_ATR_PCT / atr_percent
    adjusted = base * ratio
    return max(POSITION_MIN_PCT, min(POSITION_MAX_PCT, round(adjusted, 1)))


def _calc_kelly_position(confidence: float, risk_reward: float) -> float:
    """Kelly Criterion 기반 포지션 사이즈 (% of capital).
    f* = (b*p - q) / b
    b = risk_reward (평균 수익 / 평균 손실)
    p = win_rate (confidence를 proxy로 사용)
    Fractional Kelly (25%) 적용으로 보수적 운용.
    """
    win_rate = max(0.1, min(0.9, confidence))  # 극단값 방지
    b = max(0.5, risk_reward)
    q = 1.0 - win_rate
    kelly_full = (b * win_rate - q) / b
    if kelly_full <= 0:
        return POSITION_MIN_PCT
    kelly_fraction = kelly_full * 0.25  # 25% fractional Kelly
    pct = kelly_fraction * 100  # 비율 → 퍼센트
    return max(POSITION_MIN_PCT, min(POSITION_MAX_PCT, round(pct, 1)))


def _calc_position_size(atr_percent: float, cat: str, confidence: float = 0.5, risk_reward: float = 2.0) -> float:
    """ATR 역비례 방식(60%) + Kelly Criterion(40%) 블렌딩."""
    atr_pct = _calc_position_size_atr(atr_percent, cat)
    kelly_pct = _calc_kelly_position(confidence, risk_reward)
    blended = atr_pct * 0.6 + kelly_pct * 0.4
    return max(POSITION_MIN_PCT, min(POSITION_MAX_PCT, round(blended, 1)))


def _volatility_adjusted_multiplier(
    atr_percent: float,
    base_mult: float,
    base_min_frac: float,
    base_floor_frac: float,
) -> tuple:
    """
    ATR% 기반 동적 SL 배율 조정.
    고변동성(>5%): SL 넓힘, 저변동성(<1.5%): SL 좁힘
    """
    if atr_percent > 5.0:
        sl_adj, frac_adj = 0.3, 0.1
    elif atr_percent < 1.5:
        sl_adj, frac_adj = -0.2, -0.05
    else:
        sl_adj, frac_adj = 0.0, 0.0

    return (
        max(base_mult + sl_adj, 0.5),
        max(base_min_frac + frac_adj, 0.15),
        max(base_floor_frac + frac_adj, 0.1),
    )


@dataclass
class TradeParams:
    """트레이드 파라미터"""
    entry_price: float
    stop_loss: float
    take_profit_1: float    # 1:1 R:R
    take_profit_2: float    # 1:2 R:R
    take_profit_3: float    # 1:3 R:R
    risk_reward_ratio: float
    risk_percent: float     # SL까지 거리 %
    position_direction: str  # "long" or "short"
    trailing_stop_distance: float = 0.0  # ATR 기반 트레일링 스톱 거리
    suggested_position_pct: float = 0.0  # 변동성 기반 추천 포지션 비율 (%)

    def to_dict(self) -> dict:
        return {k: round(v, 6) if isinstance(v, float) else v for k, v in asdict(self).items()}


def calculate_trade_params(
    df: pd.DataFrame,
    signal_type: str,
    levels: PriceLevels,
    timeframe: str = "1h",
    confidence: float = 0.5,
) -> Optional[TradeParams]:
    """
    시그널 타입과 가격 레벨을 기반으로 트레이드 파라미터 계산.
    타임프레임별 ATR 배율 적용 (스캘핑: 타이트, 포지션: 넓음).
    """
    if signal_type in ("NEUTRAL",):
        return None

    try:
        current_price = float(df["close"].iloc[-1])
        atr = levels.atr

        if atr <= 0 or current_price <= 0:
            return None

        atr_percent = (atr / current_price) * 100

        # 타임프레임 카테고리별 ATR 배율 + 변동성 동적 조정
        cat = TF_CATEGORY.get(timeframe, "swing")
        sl_mult, min_frac, floor_frac = _volatility_adjusted_multiplier(
            atr_percent, SL_ATR_MULT[cat], SL_MIN_ATR_FRAC[cat], SL_FLOOR_ATR_FRAC[cat]
        )

        is_long = signal_type in ("STRONG_LONG", "LONG")

        if is_long:
            support_based_sl = None
            if levels.support_levels:
                nearest_support = levels.support_levels[0]
                support_based_sl = nearest_support - min_frac * atr

            atr_based_sl = current_price - sl_mult * atr
            min_sl = current_price - min_frac * atr

            if support_based_sl is not None and support_based_sl < min_sl:
                stop_loss = max(support_based_sl, atr_based_sl)
            else:
                stop_loss = atr_based_sl

            if current_price - stop_loss < floor_frac * atr:
                stop_loss = current_price - atr * (sl_mult * 0.67)

            risk = current_price - stop_loss
            entry_price = current_price

            tp_rr = TP_RR_HIGH_VOL if atr_percent > 5.0 else TP_RR_LOW_VOL if atr_percent < 1.5 else (1.0, 2.0, 3.0)
            tp1 = entry_price + risk * tp_rr[0]
            tp2 = entry_price + risk * tp_rr[1]
            tp3 = entry_price + risk * tp_rr[2]

        else:  # SHORT
            resistance_based_sl = None
            if levels.resistance_levels:
                nearest_resistance = levels.resistance_levels[0]
                resistance_based_sl = nearest_resistance + min_frac * atr

            atr_based_sl = current_price + sl_mult * atr
            max_sl = current_price + min_frac * atr

            if resistance_based_sl is not None and resistance_based_sl > max_sl:
                stop_loss = min(resistance_based_sl, atr_based_sl)
            else:
                stop_loss = atr_based_sl

            if stop_loss - current_price < floor_frac * atr:
                stop_loss = current_price + atr * (sl_mult * 0.67)

            risk = stop_loss - current_price
            entry_price = current_price

            tp_rr = TP_RR_HIGH_VOL if atr_percent > 5.0 else TP_RR_LOW_VOL if atr_percent < 1.5 else (1.0, 2.0, 3.0)
            tp1 = entry_price - risk * tp_rr[0]
            tp2 = entry_price - risk * tp_rr[1]
            tp3 = entry_price - risk * tp_rr[2]

        risk_percent = (risk / entry_price) * 100 if entry_price > 0 else 0
        rr_ratio = 2.0

        # 트레일링 스톱 거리 계산
        trailing_dist = _calc_trailing_stop(atr, cat, atr_percent)

        # 추천 포지션 사이즈 계산 (ATR + Kelly 블렌딩)
        position_pct = _calc_position_size(atr_percent, cat, confidence, rr_ratio)

        return TradeParams(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward_ratio=rr_ratio,
            risk_percent=round(risk_percent, 2),
            position_direction="long" if is_long else "short",
            trailing_stop_distance=round(trailing_dist, 6),
            suggested_position_pct=position_pct,
        )
    except Exception as e:
        logger.error("트레이드 파라미터 계산 오류: %s", e, exc_info=True)
        return None

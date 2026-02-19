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

    def to_dict(self) -> dict:
        return {k: round(v, 6) if isinstance(v, float) else v for k, v in asdict(self).items()}


def calculate_trade_params(
    df: pd.DataFrame,
    signal_type: str,
    levels: PriceLevels,
    timeframe: str = "1h",
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

        # 타임프레임 카테고리별 ATR 배율
        cat = TF_CATEGORY.get(timeframe, "swing")
        sl_mult = SL_ATR_MULT[cat]
        min_frac = SL_MIN_ATR_FRAC[cat]
        floor_frac = SL_FLOOR_ATR_FRAC[cat]

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

            tp1 = entry_price + risk * 1.0
            tp2 = entry_price + risk * 2.0
            tp3 = entry_price + risk * 3.0

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

            tp1 = entry_price - risk * 1.0
            tp2 = entry_price - risk * 2.0
            tp3 = entry_price - risk * 3.0

        risk_percent = (risk / entry_price) * 100 if entry_price > 0 else 0
        rr_ratio = 2.0

        return TradeParams(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward_ratio=rr_ratio,
            risk_percent=round(risk_percent, 2),
            position_direction="long" if is_long else "short",
        )
    except Exception as e:
        logger.error("트레이드 파라미터 계산 오류: %s", e, exc_info=True)
        return None

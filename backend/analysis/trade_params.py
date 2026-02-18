"""
트레이드 파라미터 계산 모듈
진입가, 손절(SL), 익절(TP), 리스크/리워드 비율
"""
import logging
import pandas as pd
from dataclasses import dataclass, asdict
from typing import Optional

from .levels import PriceLevels

logger = logging.getLogger(__name__)


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
) -> Optional[TradeParams]:
    """
    시그널 타입과 가격 레벨을 기반으로 트레이드 파라미터 계산

    LONG:
      - Entry: 현재 종가
      - SL: max(가까운 지지선 - 0.5*ATR, entry - 1.5*ATR) (단, entry - 0.5*ATR 이상 떨어져야 함)
      - TP: entry + N * (entry - SL)

    SHORT:
      - Entry: 현재 종가
      - SL: min(가까운 저항선 + 0.5*ATR, entry + 1.5*ATR)
      - TP: entry - N * (SL - entry)
    """
    if signal_type in ("NEUTRAL",):
        return None

    try:
        current_price = float(df["close"].iloc[-1])
        atr = levels.atr

        if atr <= 0 or current_price <= 0:
            return None

        is_long = signal_type in ("STRONG_LONG", "LONG")

        if is_long:
            # 지지선 기반 SL 계산
            support_based_sl = None
            if levels.support_levels:
                nearest_support = levels.support_levels[0]  # 가장 가까운 지지선
                support_based_sl = nearest_support - 0.5 * atr

            # ATR 기반 SL (폴백)
            atr_based_sl = current_price - 1.5 * atr

            # 더 보수적인(가까운) SL 선택, 단 최소 0.5*ATR은 떨어져야 함
            min_sl = current_price - 0.5 * atr
            if support_based_sl is not None and support_based_sl < min_sl:
                stop_loss = max(support_based_sl, atr_based_sl)
            else:
                stop_loss = atr_based_sl

            # SL이 현재가와 너무 가까우면 1*ATR로 강제
            if current_price - stop_loss < 0.3 * atr:
                stop_loss = current_price - atr

            risk = current_price - stop_loss
            entry_price = current_price

            tp1 = entry_price + risk * 1.0
            tp2 = entry_price + risk * 2.0
            tp3 = entry_price + risk * 3.0

        else:  # SHORT
            # 저항선 기반 SL 계산
            resistance_based_sl = None
            if levels.resistance_levels:
                nearest_resistance = levels.resistance_levels[0]
                resistance_based_sl = nearest_resistance + 0.5 * atr

            atr_based_sl = current_price + 1.5 * atr
            max_sl = current_price + 0.5 * atr

            if resistance_based_sl is not None and resistance_based_sl > max_sl:
                stop_loss = min(resistance_based_sl, atr_based_sl)
            else:
                stop_loss = atr_based_sl

            if stop_loss - current_price < 0.3 * atr:
                stop_loss = current_price + atr

            risk = stop_loss - current_price
            entry_price = current_price

            tp1 = entry_price - risk * 1.0
            tp2 = entry_price - risk * 2.0
            tp3 = entry_price - risk * 3.0

        risk_percent = (risk / entry_price) * 100 if entry_price > 0 else 0
        # 기본 R:R은 2:1 (TP2 기준)
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

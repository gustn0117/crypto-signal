"""
몬테카를로 가격 예측 엔진
200회 랜덤워크 시뮬레이션 → 중앙값 = 예측선, 10/90 퍼센타일 = 신뢰 구간

지표 기반 드리프트, 레짐별 변동성 조정, 지지/저항 확률적 장벽,
과거 정확도 캘리브레이션 피드백을 반영한 정교한 예측 경로 생성.
"""
import logging
from datetime import datetime, timezone

import numpy as np

logger = logging.getLogger(__name__)

TF_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

NUM_SIMULATIONS = 200


def generate_prediction(
    signal_direction: str,
    confidence: float,
    entry_price: float,
    trade_params: dict | None,
    price_levels: dict,
    timeframe: str,
    horizon_candles: int = 24,
    indicator_snapshot: dict | None = None,
    regime: str | None = None,
    calibration: dict | None = None,
    sr_levels: list[float] | None = None,
) -> dict:
    """
    몬테카를로 시뮬레이션 기반 미래 가격 경로 생성.

    Args:
        signal_direction: STRONG_LONG/LONG/NEUTRAL/SHORT/STRONG_SHORT
        confidence: 시그널 신뢰도 (0~1)
        entry_price: 현재 진입 가격
        trade_params: SL/TP 정보 dict
        price_levels: ATR 등 가격 레벨 정보
        timeframe: 타임프레임 문자열
        horizon_candles: 예측 봉 수
        indicator_snapshot: RSI, MACD slope, BB position, volume_ratio 등
        regime: TRENDING_UP/TRENDING_DOWN/RANGING/VOLATILE
        calibration: 과거 정확도 피드백 {"avg_accuracy": float, "count": int}
        sr_levels: 지지/저항 가격 레벨 리스트

    Returns:
        dict with predicted_path, upper_bound_path, lower_bound_path, horizon_candles
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    candle_sec = TF_SECONDS.get(timeframe, 3600)
    atr = price_levels.get("atr", entry_price * 0.02)
    snap = indicator_snapshot or {}

    is_long = signal_direction in ("STRONG_LONG", "LONG")
    is_short = signal_direction in ("STRONG_SHORT", "SHORT")

    # ── 1. 드리프트 계산 (ATR 단위 / 스텝) ──
    drift = _calculate_drift(
        is_long, is_short, confidence, signal_direction, atr, snap
    )

    # ── 2. 레짐별 스텝 변동성 & 드리프트 보정 ──
    step_vol, drift = _apply_regime(regime, atr, drift)

    # ── 3. 캘리브레이션 (과거 정확도 피드백) ──
    cal_factor = 1.0
    if calibration and calibration.get("count", 0) >= 5:
        avg_acc = calibration.get("avg_accuracy", 0.5)
        cal_factor = 0.5 + avg_acc  # 정확도 높으면 드리프트 유지, 낮으면 약화
        drift *= cal_factor
        step_vol *= (2.0 - cal_factor)  # 정확도 낮으면 변동성 확대

    # ── 4. SL/TP 바운더리 ──
    sl_price = None
    tp3_price = None
    if trade_params:
        sl_price = trade_params.get("stop_loss")
        tp3_price = trade_params.get("take_profit_3")

    # ── 5. 지지/저항 레벨 준비 ──
    sr = sorted(sr_levels) if sr_levels else []

    # ── 6. 시뮬레이션 실행 ──
    rng = np.random.default_rng()
    all_paths = np.zeros((NUM_SIMULATIONS, horizon_candles + 1))
    all_paths[:, 0] = entry_price

    volume_ratio = snap.get("volume_ratio", 1.0)

    for sim in range(NUM_SIMULATIONS):
        price = entry_price
        for step in range(1, horizon_candles + 1):
            # 랜덤 변동
            noise = rng.normal(0, step_vol)

            # 시간 감쇠 드리프트 (후반부 약화)
            progress = step / horizon_candles
            time_decay = 1.0 - 0.3 * progress
            step_drift = drift * time_decay

            price = price + step_drift + noise

            # 지지/저항 장벽 처리
            if sr:
                price = _apply_sr_barrier(
                    price, price - step_drift - noise, sr,
                    drift, volume_ratio, atr, rng
                )

            # SL/TP 바운더리 소프트 클램핑
            if sl_price and tp3_price:
                price = _soft_clamp(price, sl_price, tp3_price, is_long)

            # 가격은 0 이하 불가
            price = max(price, entry_price * 0.5)

            all_paths[sim, step] = price

    # ── 7. 결과 추출: 중앙값 + 퍼센타일 ──
    median_path = np.median(all_paths, axis=0)
    upper_path = np.percentile(all_paths, 90, axis=0)
    lower_path = np.percentile(all_paths, 10, axis=0)

    # 시간 배열
    times = [now_ts + i * candle_sec for i in range(horizon_candles + 1)]

    predicted = [
        {"time": int(times[i]), "price": round(float(median_path[i]), 8)}
        for i in range(horizon_candles + 1)
    ]
    upper_bound = [
        {"time": int(times[i]), "price": round(float(upper_path[i]), 8)}
        for i in range(horizon_candles + 1)
    ]
    lower_bound = [
        {"time": int(times[i]), "price": round(float(lower_path[i]), 8)}
        for i in range(horizon_candles + 1)
    ]

    return {
        "predicted_path": predicted,
        "upper_bound_path": upper_bound,
        "lower_bound_path": lower_bound,
        "horizon_candles": horizon_candles,
    }


def _calculate_drift(
    is_long: bool,
    is_short: bool,
    confidence: float,
    signal_direction: str,
    atr: float,
    snap: dict,
) -> float:
    """지표 기반 스텝 드리프트 계산 (ATR 단위)."""
    if not is_long and not is_short:
        return 0.0

    # 기본 드리프트: 신뢰도 × ATR의 15%
    base = confidence * 0.15 * atr
    if "STRONG" in signal_direction:
        base *= 1.3

    direction = 1.0 if is_long else -1.0
    drift = base * direction

    # RSI 평균회귀 보정
    rsi = snap.get("rsi")
    if rsi is not None:
        if rsi < 30:
            drift += 0.10 * atr  # 과매도 → 상방 압력
        elif rsi > 70:
            drift -= 0.10 * atr  # 과매수 → 하방 압력
        elif rsi < 40:
            drift += 0.04 * atr
        elif rsi > 60:
            drift -= 0.04 * atr

    # MACD 히스토그램 가속
    macd_slope = snap.get("macd_hist_slope")
    if macd_slope is not None:
        drift += macd_slope * 0.05 * atr * 100  # slope를 ATR 단위로 변환

    # BB 위치 보정 (밴드 상/하단 근접 시 반대 압력)
    bb_pos = snap.get("bb_position")
    if bb_pos is not None:
        if bb_pos > 0.9:
            drift -= 0.06 * atr  # 상단 근접 → 하방 압력
        elif bb_pos < 0.1:
            drift += 0.06 * atr  # 하단 근접 → 상방 압력

    # 거래량 배율: 높은 거래량 → 드리프트 확신 강화
    vol_ratio = snap.get("volume_ratio", 1.0)
    vol_multiplier = 1.0 + min(max(vol_ratio - 1.0, 0), 1.0) * 0.3
    drift *= vol_multiplier

    return drift


def _apply_regime(regime: str | None, atr: float, drift: float) -> tuple[float, float]:
    """레짐별 스텝 변동성과 드리프트 조정."""
    if regime == "TRENDING_UP" or regime == "TRENDING_DOWN":
        step_vol = atr * 0.6
        drift *= 1.3
    elif regime == "RANGING":
        step_vol = atr * 0.8
        drift *= 0.5
    elif regime == "VOLATILE":
        step_vol = atr * 1.2
    else:
        step_vol = atr * 0.8  # 기본값

    return step_vol, drift


def _apply_sr_barrier(
    new_price: float,
    old_price: float,
    sr_levels: list[float],
    drift: float,
    volume_ratio: float,
    atr: float,
    rng: np.random.Generator,
) -> float:
    """지지/저항 레벨 돌파/반등 확률적 판정."""
    for level in sr_levels:
        # 이 스텝에서 레벨을 횡단했는지 확인
        crossed = (old_price < level <= new_price) or (old_price > level >= new_price)
        if not crossed:
            continue

        # 레벨과의 거리가 ATR의 20% 이내일 때만 적용
        if abs(new_price - level) > atr * 0.2:
            continue

        # 돌파 확률 = 0.3 + 0.4×|드리프트/ATR| + 0.2×거래량비율
        drift_strength = min(abs(drift) / atr, 1.0) if atr > 0 else 0
        breakout_prob = 0.3 + 0.4 * drift_strength + 0.2 * min(volume_ratio / 2.0, 1.0)
        breakout_prob = min(breakout_prob, 0.85)

        if rng.random() > breakout_prob:
            # 반등: 가격을 레벨로부터 반사
            overshoot = new_price - level
            new_price = level - overshoot * 0.5
        else:
            # 돌파: 속도 감속
            overshoot = new_price - level
            new_price = level + overshoot * 0.7

    return new_price


def _soft_clamp(
    price: float,
    sl: float,
    tp3: float,
    is_long: bool,
) -> float:
    """SL/TP3 근처에서 소프트 클램핑 (급격한 가격 절단 방지)."""
    if is_long:
        if price < sl:
            # SL 아래로 과도하게 벗어나지 않도록
            price = sl - (sl - price) * 0.3
        if price > tp3:
            price = tp3 + (price - tp3) * 0.3
    else:
        if price > sl:
            price = sl + (price - sl) * 0.3
        if price < tp3:
            price = tp3 - (tp3 - price) * 0.3

    return price

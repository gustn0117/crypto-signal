"""
몬테카를로 가격 예측 엔진 (v3)
2000회 시뮬레이션 → 중앙값 = 예측선, 10/90 퍼센타일 = 신뢰 구간

v3 개선:
- 시뮬레이션 횟수 500→2000 (서버 자원 최대 활용)
- 하이브리드 분포: 실제 과거 수익률 분포 + Student's t 폴백
- BTC 상관관계 드리프트 보정 (알트코인)
- 시간대별 변동성 프로필 (아시아/유럽/미국 세션)
"""
import logging
from datetime import datetime, timezone

import numpy as np
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

TF_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

NUM_SIMULATIONS = 2000

# Student's t 자유도 (fat tail 정도: 낮을수록 꼬리 두꺼움)
T_DISTRIBUTION_DF = 5

# 세션별 변동성 배율 (UTC 기준)
SESSION_VOLATILITY = {
    "asia": 0.85,      # 00:00-08:00 UTC (아시아: 상대적 낮은 변동성)
    "europe": 1.0,     # 08:00-16:00 UTC (유럽: 보통)
    "us": 1.2,         # 16:00-24:00 UTC (미국: 높은 변동성)
}


def _get_session_multiplier(hour_utc: int) -> float:
    """UTC 시간 기준 세션별 변동성 배율"""
    if 0 <= hour_utc < 8:
        return SESSION_VOLATILITY["asia"]
    elif 8 <= hour_utc < 16:
        return SESSION_VOLATILITY["europe"]
    else:
        return SESSION_VOLATILITY["us"]


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
    btc_signal_direction: str | None = None,
    is_altcoin: bool = False,
    historical_returns: np.ndarray | None = None,
) -> dict:
    """
    몬테카를로 시뮬레이션 기반 미래 가격 경로 생성 (v2).

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
        calibration: 과거 정확도 피드백
        sr_levels: 지지/저항 가격 레벨 리스트
        btc_signal_direction: BTC의 시그널 방향 (알트코인 상관관계 보정용)
        is_altcoin: 알트코인 여부
        historical_returns: 과거 캔들의 수익률 배열 (리샘플링용, 100개 이상 필요)

    Returns:
        dict with predicted_path, upper_bound_path, lower_bound_path, horizon_candles
    """
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    candle_sec = TF_SECONDS.get(timeframe, 3600)
    atr = price_levels.get("atr", entry_price * 0.02)
    snap = indicator_snapshot or {}

    is_long = signal_direction in ("STRONG_LONG", "LONG")
    is_short = signal_direction in ("STRONG_SHORT", "SHORT")

    # ── 1. 드리프트 계산 ──
    drift = _calculate_drift(is_long, is_short, confidence, signal_direction, atr, snap)

    # ── 2. 레짐별 변동성 & 드리프트 보정 ──
    step_vol, drift = _apply_regime(regime, atr, drift)

    # ── 3. 캘리브레이션 ──
    cal_factor = 1.0
    if calibration and calibration.get("count", 0) >= 5:
        avg_acc = min(max(calibration.get("avg_accuracy", 0.5), 0.0), 1.0)
        cal_factor = max(0.5, min(0.5 + avg_acc, 1.5))
        drift *= cal_factor
        step_vol *= max(0.5, 2.0 - cal_factor)

    # ── 4. BTC 상관관계 보정 (알트코인만) ──
    if is_altcoin and btc_signal_direction:
        drift = _apply_btc_correlation(drift, btc_signal_direction, is_long, is_short, atr)

    # ── 5. SL/TP 바운더리 ──
    sl_price = None
    tp3_price = None
    if trade_params:
        sl_price = trade_params.get("stop_loss")
        tp3_price = trade_params.get("take_profit_3")

    # ── 6. 지지/저항 레벨 ──
    sr = sorted(sr_levels) if sr_levels else []

    # ── 7. 시뮬레이션 실행 (하이브리드: 실제 수익률 분포 or Student's t) ──
    rng = np.random.default_rng()
    all_paths = np.zeros((NUM_SIMULATIONS, horizon_candles + 1))
    all_paths[:, 0] = entry_price

    # 실제 과거 수익률이 충분하면 리샘플링 사용
    use_historical = (historical_returns is not None and len(historical_returns) >= 100)
    if use_historical:
        hist_std = float(np.std(historical_returns))
        if hist_std <= 0:
            use_historical = False

    volume_ratio = snap.get("volume_ratio", 1.0)
    start_hour = now.hour

    for sim in range(NUM_SIMULATIONS):
        price = entry_price
        for step in range(1, horizon_candles + 1):
            if use_historical:
                # 실제 과거 수익률에서 리샘플링 → 가격 단위로 변환
                sampled_return = rng.choice(historical_returns)
                noise = sampled_return * entry_price * (step_vol / (hist_std * entry_price + 1e-12))
            else:
                # Fat-tail 노이즈 (Student's t)
                noise = scipy_stats.t.rvs(df=T_DISTRIBUTION_DF, random_state=rng) * step_vol

            # 시간대별 변동성 조정
            step_hour = (start_hour + int(step * candle_sec / 3600)) % 24
            session_mult = _get_session_multiplier(step_hour)
            noise *= session_mult

            # 시간 감쇠 드리프트
            progress = step / horizon_candles
            time_decay = max(0.0, 1.0 - 0.3 * progress)
            step_drift = drift * time_decay

            price = price + step_drift + noise

            # 지지/저항 장벽
            if sr:
                price = _apply_sr_barrier(
                    price, price - step_drift - noise, sr,
                    drift, volume_ratio, atr, rng
                )

            # SL/TP 소프트 클램핑
            if sl_price and tp3_price:
                price = _soft_clamp(price, sl_price, tp3_price, is_long)

            price = max(price, entry_price * 0.5)
            all_paths[sim, step] = price

    # ── 8. 결과 추출 ──
    median_path = np.median(all_paths, axis=0)
    upper_path = np.percentile(all_paths, 90, axis=0)
    lower_path = np.percentile(all_paths, 10, axis=0)

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

    base = confidence * 0.15 * atr
    if "STRONG" in signal_direction:
        base *= 1.3

    direction = 1.0 if is_long else -1.0
    drift = base * direction

    # RSI 평균회귀 보정
    rsi = snap.get("rsi")
    if rsi is not None:
        if rsi < 30:
            drift += 0.10 * atr
        elif rsi > 70:
            drift -= 0.10 * atr
        elif rsi < 40:
            drift += 0.04 * atr
        elif rsi > 60:
            drift -= 0.04 * atr

    # MACD 히스토그램 가속
    macd_slope = snap.get("macd_hist_slope")
    if macd_slope is not None:
        drift += macd_slope * 0.05 * atr * 100

    # BB 위치 보정
    bb_pos = snap.get("bb_position")
    if bb_pos is not None:
        if bb_pos > 0.9:
            drift -= 0.06 * atr
        elif bb_pos < 0.1:
            drift += 0.06 * atr

    # 거래량 배율
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
        step_vol = atr * 0.8

    return step_vol, drift


def _apply_btc_correlation(
    drift: float,
    btc_direction: str,
    is_long: bool,
    is_short: bool,
    atr: float,
) -> float:
    """BTC 시그널 방향을 알트코인 드리프트에 반영 (±10% 보정)"""
    btc_is_long = btc_direction in ("STRONG_LONG", "LONG")
    btc_is_short = btc_direction in ("STRONG_SHORT", "SHORT")

    if btc_is_long and is_long:
        drift *= 1.10  # BTC와 같은 방향 → 확신 강화
    elif btc_is_short and is_short:
        drift *= 1.10
    elif btc_is_long and is_short:
        drift *= 0.90  # BTC와 반대 → 확신 약화
    elif btc_is_short and is_long:
        drift *= 0.90

    return drift


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
        crossed = (old_price < level <= new_price) or (old_price > level >= new_price)
        if not crossed:
            continue

        if abs(new_price - level) > atr * 0.2:
            continue

        drift_strength = min(abs(drift) / atr, 1.0) if atr > 0 else 0
        breakout_prob = 0.3 + 0.4 * drift_strength + 0.2 * min(volume_ratio / 2.0, 1.0)
        breakout_prob = min(breakout_prob, 0.85)

        if rng.random() > breakout_prob:
            overshoot = new_price - level
            new_price = level - overshoot * 0.5
        else:
            overshoot = new_price - level
            new_price = level + overshoot * 0.7

    return new_price


def _soft_clamp(
    price: float,
    sl: float,
    tp3: float,
    is_long: bool,
) -> float:
    """SL/TP3 근처에서 소프트 클램핑."""
    if is_long:
        if price < sl:
            price = sl - (sl - price) * 0.3
        if price > tp3:
            price = tp3 + (price - tp3) * 0.3
    else:
        if price > sl:
            price = sl + (price - sl) * 0.3
        if price < tp3:
            price = tp3 - (tp3 - price) * 0.3

    return price

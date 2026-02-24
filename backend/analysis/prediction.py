"""
몬테카를로 가격 예측 엔진 (v4)
2000회 시뮬레이션 → 중앙값 = 예측선, 10/90 퍼센타일 = 신뢰 구간

v4 개선 (시그널 엔진 분석 결과 완전 통합):
- 카테고리 스코어(지표/캔들/차트/거래량/선물) → 드리프트 방향성 강화
- 오더북 불균형 → 단기 방향 압력
- 패턴 매칭 → 과거 유사 패턴 기반 드리프트 보정
- ML 예측 확률 → 앙상블 드리프트
- 이상치 탐지 → 변동성 확대
- MTF 합류 → 드리프트 확신도 강화
- 합류(Confluence) 보너스 → 방향 확신도 강화
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


# ── A1: 드리프트 스테이지별 / 전체 캡 ──
STAGE_DRIFT_CAP = 0.30   # 각 스테이지 최대 변동: ±0.30 ATR
TOTAL_DRIFT_CAP = 1.50   # 전체 누적 드리프트 최대: ±1.50 ATR


def _cap_drift_delta(before: float, after: float, atr: float, cap: float = STAGE_DRIFT_CAP) -> float:
    """드리프트 스테이지의 변동분을 ±cap*ATR로 제한."""
    if atr <= 0:
        return after
    delta = after - before
    max_delta = cap * atr
    clamped = max(-max_delta, min(max_delta, delta))
    return before + clamped


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
    몬테카를로 시뮬레이션 기반 미래 가격 경로 생성 (v4).

    indicator_snapshot에 포함된 확장 데이터:
    - category_scores: {indicator, candle_pattern, chart_pattern, volume, futures, total}
    - orderbook: {imbalance, signal, strength, bid_wall, ask_wall}
    - anomaly: {score, is_anomaly, vol_ratio, price_change_pct}
    - pattern_match: {total_matches, up_pct, avg_outcome_pct}
    - ml_prediction: {up, down, flat}
    - confluence_bonus, mtf_agreement, mtf_modifier
    """
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    candle_sec = TF_SECONDS.get(timeframe, 3600)
    atr = price_levels.get("atr", entry_price * 0.02)
    snap = indicator_snapshot or {}

    is_long = signal_direction in ("STRONG_LONG", "LONG")
    is_short = signal_direction in ("STRONG_SHORT", "SHORT")

    # ── 1. 기본 드리프트 (기술 지표 기반) ──
    drift = _calculate_base_drift(is_long, is_short, confidence, signal_direction, atr, snap)

    # ── 2. 카테고리 스코어 기반 드리프트 강화 (CAP 적용) ──
    prev = drift
    drift = _apply_category_scores(drift, snap, atr, is_long, is_short)
    drift = _cap_drift_delta(prev, drift, atr)

    # ── 3. 오더북 불균형 드리프트 (CAP 적용) ──
    prev = drift
    drift = _apply_orderbook_drift(drift, snap, atr, is_long, is_short)
    drift = _cap_drift_delta(prev, drift, atr)

    # ── 4. 패턴 매칭 기반 드리프트 (CAP 적용) ──
    prev = drift
    drift = _apply_pattern_drift(drift, snap, atr, is_long, is_short)
    drift = _cap_drift_delta(prev, drift, atr)

    # ── 5. ML 예측 앙상블 드리프트 (CAP 적용) ──
    prev = drift
    drift = _apply_ml_drift(drift, snap, atr, is_long, is_short)
    drift = _cap_drift_delta(prev, drift, atr)

    # ── 6. 합류 + MTF 확인 드리프트 (CAP 적용) ──
    prev = drift
    drift = _apply_confluence_mtf(drift, snap)
    drift = _cap_drift_delta(prev, drift, atr)

    # ── 7. 레짐별 변동성 & 드리프트 보정 (A5: soft score 지원) ──
    regime_scores = snap.get("regime_scores")
    step_vol, drift = _apply_regime(regime, atr, drift, regime_scores=regime_scores)

    # ── 전체 드리프트 총량 캡 ──
    if atr > 0:
        max_total = TOTAL_DRIFT_CAP * atr
        drift = max(-max_total, min(max_total, drift))

    # ── 8. 이상치 감지 → 변동성 확대 ──
    step_vol = _apply_anomaly_volatility(step_vol, snap)

    # ── 9. 캘리브레이션 ──
    cal_factor = 1.0
    if calibration and calibration.get("count", 0) >= 5:
        avg_acc = min(max(calibration.get("avg_accuracy", 0.5), 0.0), 1.0)
        cal_factor = max(0.5, min(0.5 + avg_acc, 1.5))
        drift *= cal_factor
        step_vol *= max(0.5, 2.0 - cal_factor)

    # ── 10. BTC 상관관계 보정 (알트코인만) ──
    if is_altcoin and btc_signal_direction:
        drift = _apply_btc_correlation(drift, btc_signal_direction, is_long, is_short, atr)

    # ── 11. SL/TP 바운더리 ──
    sl_price = None
    tp3_price = None
    if trade_params:
        sl_price = trade_params.get("stop_loss")
        tp3_price = trade_params.get("take_profit_3")

    # ── 12. 지지/저항 레벨 ──
    sr = sorted(sr_levels) if sr_levels else []

    # ── 13. 시뮬레이션 실행 ──
    rng = np.random.default_rng()
    all_paths = np.zeros((NUM_SIMULATIONS, horizon_candles + 1))
    all_paths[:, 0] = entry_price

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
                sampled_return = rng.choice(historical_returns)
                noise = sampled_return * entry_price * (step_vol / (hist_std * entry_price + 1e-12))
            else:
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

    # ── 14. 결과 추출 ──
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


# ────────────────────────────────────────────────────────
# C3: 실시간 예측 경로 재계산
# ────────────────────────────────────────────────────────

def recalculate_remaining_path(
    predicted_path: list[dict],
    upper_bound_path: list[dict],
    lower_bound_path: list[dict],
    current_price: float,
    current_time: int,
    atr: float,
) -> dict:
    """
    C3: 현재가 기준으로 남은 예측 경로를 재계산.

    이미 지난 구간은 실제가로 고정, 미래 구간은
    현재가→원래 목표가를 향해 보간하여 경로 수정.
    """
    if not predicted_path or len(predicted_path) < 2:
        return {
            "predicted_path": predicted_path,
            "upper_bound_path": upper_bound_path,
            "lower_bound_path": lower_bound_path,
        }

    # 현재 시간 이후의 첫 인덱스 찾기
    future_idx = 0
    for i, pt in enumerate(predicted_path):
        if pt["time"] >= current_time:
            future_idx = i
            break
    else:
        # 모든 경로가 과거 → 수정 불필요
        return {
            "predicted_path": predicted_path,
            "upper_bound_path": upper_bound_path,
            "lower_bound_path": lower_bound_path,
        }

    if future_idx == 0:
        future_idx = 1  # 최소 1개는 고정

    remaining = len(predicted_path) - future_idx
    if remaining < 2:
        return {
            "predicted_path": predicted_path,
            "upper_bound_path": upper_bound_path,
            "lower_bound_path": lower_bound_path,
        }

    # 현재가와 원래 경로의 차이 (drift correction)
    orig_now_price = predicted_path[future_idx]["price"]
    price_offset = current_price - orig_now_price

    # 차이가 ATR의 10% 미만이면 수정 불필요
    if atr > 0 and abs(price_offset) < atr * 0.10:
        return {
            "predicted_path": predicted_path,
            "upper_bound_path": upper_bound_path,
            "lower_bound_path": lower_bound_path,
        }

    # 미래 경로 재계산: 현재가에서 시작, 점진적으로 원래 목표가로 수렴
    new_predicted = predicted_path[:future_idx]
    new_upper = upper_bound_path[:future_idx] if upper_bound_path else []
    new_lower = lower_bound_path[:future_idx] if lower_bound_path else []

    for j in range(remaining):
        progress = j / (remaining - 1) if remaining > 1 else 1.0
        # 보정량이 점진적으로 감소 (현재가 영향 → 원래 목표가)
        blend = 1.0 - progress  # 1.0 at start, 0.0 at end
        offset_now = price_offset * blend

        idx = future_idx + j

        # 예측선
        new_p = predicted_path[idx]["price"] + offset_now
        new_predicted.append({
            "time": predicted_path[idx]["time"],
            "price": round(float(new_p), 8),
        })

        # 상한선
        if upper_bound_path and idx < len(upper_bound_path):
            new_u = upper_bound_path[idx]["price"] + offset_now
            new_upper.append({
                "time": upper_bound_path[idx]["time"],
                "price": round(float(new_u), 8),
            })

        # 하한선
        if lower_bound_path and idx < len(lower_bound_path):
            new_l = lower_bound_path[idx]["price"] + offset_now
            new_lower.append({
                "time": lower_bound_path[idx]["time"],
                "price": round(float(new_l), 8),
            })

    return {
        "predicted_path": new_predicted,
        "upper_bound_path": new_upper,
        "lower_bound_path": new_lower,
    }


# ────────────────────────────────────────────────────────
# 드리프트 계산 함수들
# ────────────────────────────────────────────────────────

def _calculate_base_drift(
    is_long: bool,
    is_short: bool,
    confidence: float,
    signal_direction: str,
    atr: float,
    snap: dict,
) -> float:
    """기본 지표(RSI, MACD, BB, 거래량) 기반 드리프트."""
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

    # ── 추가 지표 (v4) ──

    # ADX: 추세 강도 → 강한 추세(>25)면 드리프트 확대, 약한 추세(<15)면 축소
    adx = snap.get("adx")
    if adx is not None:
        if adx > 40:
            drift *= 1.25  # 매우 강한 추세
        elif adx > 25:
            drift *= 1.10  # 강한 추세
        elif adx < 15:
            drift *= 0.7   # 추세 없음 → 평균회귀 환경

    # 스토캐스틱: RSI와 함께 과매수/과매도 이중 확인
    stoch_k = snap.get("stoch_k")
    if stoch_k is not None:
        if stoch_k < 20 and (rsi is None or rsi < 35):
            drift += 0.05 * atr  # 이중 과매도 → 강한 반등 기대
        elif stoch_k > 80 and (rsi is None or rsi > 65):
            drift -= 0.05 * atr  # 이중 과매수 → 강한 조정 기대

    # MFI (거래량 가중 RSI): 자금 흐름 방향
    mfi = snap.get("mfi")
    if mfi is not None:
        if mfi < 20:
            drift += 0.04 * atr  # 극도의 매도 압력 후 반등
        elif mfi > 80:
            drift -= 0.04 * atr  # 극도의 매수 압력 후 조정
        elif is_long and mfi > 50:
            drift += 0.02 * atr  # 자금 유입 + LONG 시그널 합류
        elif is_short and mfi < 50:
            drift -= 0.02 * atr  # 자금 유출 + SHORT 시그널 합류

    # 일목균형 구름 위치
    ichi_pos = snap.get("ichimoku_position")
    if ichi_pos:
        if ichi_pos == "above" and is_long:
            drift *= 1.08  # 구름 위 + LONG → 확신 강화
        elif ichi_pos == "below" and is_short:
            drift *= 1.08  # 구름 아래 + SHORT → 확신 강화
        elif ichi_pos == "above" and is_short:
            drift *= 0.85  # 구름 위인데 SHORT → 역추세, 감쇠
        elif ichi_pos == "below" and is_long:
            drift *= 0.85  # 구름 아래인데 LONG → 역추세, 감쇠
        elif ichi_pos == "inside":
            drift *= 0.9   # 구름 안 = 불확실 → 드리프트 축소

    # EMA 기울기: 모멘텀 가속/감속
    ema_slope = snap.get("ema20_slope_pct")
    if ema_slope is not None:
        if is_long and ema_slope > 0.1:
            drift += min(ema_slope * 0.02, 0.06) * atr  # 상승 모멘텀
        elif is_short and ema_slope < -0.1:
            drift -= min(abs(ema_slope) * 0.02, 0.06) * atr  # 하락 모멘텀
        elif is_long and ema_slope < -0.2:
            drift *= 0.85  # 하락 모멘텀인데 LONG → 감쇠
        elif is_short and ema_slope > 0.2:
            drift *= 0.85  # 상승 모멘텀인데 SHORT → 감쇠

    # Fear & Greed 지수: 극단적 감성 → 평균회귀 또는 확신 강화
    fg = snap.get("fear_greed")
    if fg is not None:
        if fg <= 15:  # 극도의 공포
            drift += 0.04 * atr  # 반등 기대 (역발상)
        elif fg >= 85:  # 극도의 탐욕
            drift -= 0.04 * atr  # 조정 기대 (역발상)
        elif fg <= 30 and is_long:
            drift += 0.02 * atr  # 공포 속 LONG → 역발상 부스트
        elif fg >= 70 and is_short:
            drift -= 0.02 * atr  # 탐욕 속 SHORT → 역발상 부스트

    # 감성 점수 (뉴스): 시그널 방향과 일치하면 부스트
    sentiment = snap.get("sentiment_score")
    if sentiment is not None:
        if is_long and sentiment > 0.3:
            drift += min(sentiment * 0.04, 0.05) * atr
        elif is_short and sentiment < -0.3:
            drift -= min(abs(sentiment) * 0.04, 0.05) * atr

    return drift


def _apply_category_scores(
    drift: float, snap: dict, atr: float, is_long: bool, is_short: bool
) -> float:
    """카테고리 스코어(지표/캔들/차트/거래량/선물) 기반 드리프트 강화.

    total_score가 강하면(>0.3 or <-0.3) 드리프트를 최대 ±20% 증폭.
    개별 카테고리 합류 시 추가 부스트.
    """
    cs = snap.get("category_scores")
    if not cs:
        return drift

    total = cs.get("total", 0.0)

    # 전체 스코어 방향이 시그널과 일치하면 드리프트 강화
    if is_long and total > 0.15:
        drift *= 1.0 + min(total, 0.5) * 0.4  # 최대 1.2배
    elif is_short and total < -0.15:
        drift *= 1.0 + min(abs(total), 0.5) * 0.4
    elif is_long and total < -0.15:
        drift *= max(0.7, 1.0 - abs(total) * 0.3)  # 반대 방향이면 감쇠
    elif is_short and total > 0.15:
        drift *= max(0.7, 1.0 - total * 0.3)

    # 캔들 + 차트 패턴 합류 부스트
    candle = cs.get("candle_pattern", 0.0)
    chart = cs.get("chart_pattern", 0.0)
    if is_long and candle > 0.3 and chart > 0.3:
        drift += 0.03 * atr  # 캔들+차트 모두 강세 → 추가 부스트
    elif is_short and candle < -0.3 and chart < -0.3:
        drift -= 0.03 * atr

    # 선물 데이터 합류 (OI, 펀딩레이트 방향 일치)
    futures = cs.get("futures", 0.0)
    if is_long and futures > 0.3:
        drift += 0.02 * atr
    elif is_short and futures < -0.3:
        drift -= 0.02 * atr

    return drift


def _apply_orderbook_drift(
    drift: float, snap: dict, atr: float, is_long: bool, is_short: bool
) -> float:
    """오더북 불균형 기반 단기 방향 압력.

    매수/매도 불균형이 크면 해당 방향으로 드리프트 추가.
    벽(wall)이 있으면 해당 방향 지지/저항으로 작용.
    """
    ob = snap.get("orderbook")
    if not ob:
        return drift

    imbalance = ob.get("imbalance", 0.0)  # -1 ~ +1
    strength = ob.get("strength", 0.0)

    # 불균형 방향이 시그널과 일치하면 드리프트 부스트
    if is_long and imbalance > 0.2:
        drift += strength * 0.06 * atr  # 매수 우세 → LONG 부스트
    elif is_short and imbalance < -0.2:
        drift -= strength * 0.06 * atr  # 매도 우세 → SHORT 부스트
    elif is_long and imbalance < -0.3:
        drift *= 0.85  # 매도 우세인데 LONG → 감쇠
    elif is_short and imbalance > 0.3:
        drift *= 0.85  # 매수 우세인데 SHORT → 감쇠

    return drift


def _apply_pattern_drift(
    drift: float, snap: dict, atr: float, is_long: bool, is_short: bool
) -> float:
    """과거 유사 패턴 기반 드리프트 보정.

    유사 패턴의 상승/하락 비율로 드리프트 방향 확신도 조정.
    avg_outcome_pct로 기대 수익률 반영.
    """
    pm = snap.get("pattern_match")
    if not pm or pm.get("total_matches", 0) < 10:
        return drift

    up_pct = pm.get("up_pct", 0.5)
    avg_outcome = pm.get("avg_outcome_pct", 0.0)

    # 과거 패턴이 시그널 방향과 강하게 일치
    if is_long and up_pct > 0.65:
        pattern_boost = (up_pct - 0.5) * 0.15 * atr  # 최대 0.075 * atr
        drift += pattern_boost
        if avg_outcome > 0.5:  # 평균 수익률 0.5% 이상
            drift += min(avg_outcome * 0.01, 0.03) * atr
    elif is_short and up_pct < 0.35:
        pattern_boost = (0.5 - up_pct) * 0.15 * atr
        drift -= pattern_boost
        if avg_outcome < -0.5:
            drift -= min(abs(avg_outcome) * 0.01, 0.03) * atr

    # 과거 패턴이 시그널과 반대면 감쇠
    elif is_long and up_pct < 0.35:
        drift *= 0.8
    elif is_short and up_pct > 0.65:
        drift *= 0.8

    return drift


def _apply_ml_drift(
    drift: float, snap: dict, atr: float, is_long: bool, is_short: bool
) -> float:
    """ML(LSTM) 예측 확률 기반 앙상블 드리프트.

    ML이 높은 확률로 방향 예측 시 드리프트 강화/약화.
    ML 가중치: 전체 드리프트의 최대 ±15%.
    """
    ml = snap.get("ml_prediction")
    if not ml:
        return drift

    up_prob = ml.get("up", 0.33)
    down_prob = ml.get("down", 0.33)

    # ML이 강한 방향성을 보이면 (>0.5) 드리프트 조정
    if is_long and up_prob > 0.5:
        ml_boost = (up_prob - 0.33) * 0.22  # 최대 ~0.15
        drift *= (1.0 + ml_boost)
    elif is_short and down_prob > 0.5:
        ml_boost = (down_prob - 0.33) * 0.22
        drift *= (1.0 + ml_boost)
    elif is_long and down_prob > 0.5:
        ml_dampen = (down_prob - 0.33) * 0.15  # 최대 ~0.10
        drift *= max(0.75, 1.0 - ml_dampen)
    elif is_short and up_prob > 0.5:
        ml_dampen = (up_prob - 0.33) * 0.15
        drift *= max(0.75, 1.0 - ml_dampen)

    return drift


def _apply_confluence_mtf(drift: float, snap: dict) -> float:
    """합류(Confluence) 보너스 + 멀티타임프레임 확인 반영."""
    # 합류 보너스: 여러 지표가 같은 방향 → 드리프트 확신 강화
    confluence = snap.get("confluence_bonus", 0.0)
    if confluence > 0:
        drift *= (1.0 + confluence * 0.5)  # 최대 ~1.15배
    elif confluence < 0:
        drift *= max(0.85, 1.0 + confluence * 0.5)

    # MTF 합류: 상위 타임프레임도 같은 방향이면 부스트
    mtf_agrees = snap.get("mtf_agreement")
    mtf_mod = snap.get("mtf_modifier", 0.0)
    if mtf_agrees is True and mtf_mod > 0:
        drift *= (1.0 + mtf_mod * 0.3)  # 상위TF 동의 → 최대 ~1.06배
    elif mtf_agrees is False and mtf_mod < 0:
        drift *= max(0.85, 1.0 + mtf_mod * 0.3)  # 상위TF 반대 → 감쇠

    return drift


def _apply_anomaly_volatility(step_vol: float, snap: dict) -> float:
    """이상치 감지 + 볼린저 밴드 squeeze → 변동성 조정.

    이상치 = 비정상적 거래량/가격 변동 → 예측 불확실성 증가 → 신뢰 구간 확대.
    BB squeeze = 변동성 수축 후 확장 준비 → 폭발적 움직임 가능.
    """
    anomaly = snap.get("anomaly")
    if anomaly:
        if anomaly.get("is_anomaly"):
            score = abs(anomaly.get("score", 0.0))
            vol_expansion = 1.0 + min(score, 1.0) * 0.4  # 최대 1.4배
            step_vol *= vol_expansion
            logger.debug("이상치 감지: 변동성 %.1f%% 확대", (vol_expansion - 1) * 100)

        # 거래량 급등 (정상이라도) → 약간의 변동성 확대
        vol_ratio = anomaly.get("vol_ratio", 1.0)
        if vol_ratio > 2.0:
            step_vol *= 1.0 + min(vol_ratio - 2.0, 2.0) * 0.1  # 최대 1.2배

    # 볼린저 밴드 squeeze: 밴드 폭이 평균 대비 좁으면 곧 큰 움직임 가능
    bb_squeeze = snap.get("bb_squeeze")
    if bb_squeeze is not None:
        if bb_squeeze < 0.6:
            # 강한 squeeze: 변동성 수축 → 조만간 확장 예상 → 신뢰 구간 확대
            step_vol *= 1.25
        elif bb_squeeze < 0.8:
            step_vol *= 1.10
        elif bb_squeeze > 1.5:
            # 이미 변동성 확장 중: 현재 변동성 유지
            step_vol *= 1.05

    return step_vol


def _apply_regime(
    regime: str | None, atr: float, drift: float,
    regime_scores: dict | None = None,
) -> tuple[float, float]:
    """레짐별 스텝 변동성과 드리프트 조정.

    A5: regime_scores가 있으면 소프트 스코어 기반 연속 보간.
    {"trending": 0.6, "volatile": 0.2, "ranging": 0.2} 형태.
    """
    if regime_scores and sum(regime_scores.values()) > 0:
        # 소프트 스코어 기반: 각 레짐의 변동성/드리프트 배율을 가중 평균
        t = regime_scores.get("trending", 0.0)
        v = regime_scores.get("volatile", 0.0)
        r = regime_scores.get("ranging", 0.0)

        # 변동성: trending=0.6, ranging=0.8, volatile=1.2 의 가중 평균
        step_vol = atr * (t * 0.6 + r * 0.8 + v * 1.2)
        # 드리프트 배율: trending=1.3, ranging=0.5, volatile=1.0 의 가중 평균
        drift_mult = t * 1.3 + r * 0.5 + v * 1.0
        drift *= drift_mult
    elif regime == "TRENDING_UP" or regime == "TRENDING_DOWN":
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
        drift *= 1.10
    elif btc_is_short and is_short:
        drift *= 1.10
    elif btc_is_long and is_short:
        drift *= 0.90
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

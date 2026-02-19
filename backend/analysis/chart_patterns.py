"""
차트 패턴 인식 모듈 (v2 — 정확도 강화)
구조적/기하학적 멀티캔들 패턴: 쌍봉, 쌍바닥, 헤드앤숄더,
삼각수렴, 웨지, 플래그, 채널, 엘리엇 파동 등

v2 변경:
- 동적 강도 계산 (기하학 품질 + 거래량 확인)
- 임계값 강화 (오탐 감소)
- 충돌 패턴 제거
"""
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ChartPatternResult:
    """차트 패턴 분석 결과"""
    name: str
    signal: str       # "long", "short", "neutral"
    strength: float   # 0.0 ~ 1.0
    description: str


# ─── 유틸 ─────────────────────────────────────────────────

def _find_swings(series: np.ndarray, order: int = 3) -> Tuple[List[int], List[int]]:
    """
    Swing high/low 인덱스 탐색.
    order: 양옆 비교 봉 수 (클수록 큰 스윙만 잡힘)
    """
    highs, lows = [], []
    for i in range(order, len(series) - order):
        if all(series[i] > series[i - j] for j in range(1, order + 1)) and \
           all(series[i] > series[i + j] for j in range(1, order + 1)):
            highs.append(i)
        if all(series[i] < series[i - j] for j in range(1, order + 1)) and \
           all(series[i] < series[i + j] for j in range(1, order + 1)):
            lows.append(i)
    return highs, lows


def _pct_diff(a: float, b: float) -> float:
    """두 값의 비율 차이 (%)"""
    if b == 0:
        return 100.0
    return abs(a - b) / b * 100


def _linear_regression(values: np.ndarray) -> Tuple[float, float]:
    """단순 선형 회귀: (slope, r_squared)"""
    n = len(values)
    if n < 3:
        return 0.0, 0.0
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    predicted = slope * x + intercept
    ss_res = np.sum((values - predicted) ** 2)
    ss_tot = np.sum((values - np.mean(values)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, r2


def _geometry_score(
    symmetry_pct: float,
    depth_ratio: float = 0.5,
    time_symmetry: float = 1.0,
    max_symmetry_pct: float = 1.5,
) -> float:
    """
    패턴 기하학 품질 점수 (0.0 ~ 1.0)

    symmetry_pct: 두 고점/저점의 % 차이 (낮을수록 좋음)
    depth_ratio: 넥라인 깊이 / 전체 패턴 높이 (0.3~0.7이 이상적)
    time_symmetry: 좌/우 봉 수 비율 (1.0에 가까울수록 좋음)
    """
    sym_score = max(0.0, 1.0 - symmetry_pct / (max_symmetry_pct * 2))

    if 0.3 <= depth_ratio <= 0.7:
        depth_score = 1.0
    else:
        depth_score = max(0.0, 1.0 - abs(depth_ratio - 0.5) * 2)

    time_ratio = min(time_symmetry, 1.0 / time_symmetry) if time_symmetry > 0 else 0
    time_score = time_ratio

    return sym_score * 0.5 + depth_score * 0.3 + time_score * 0.2


def _volume_confirmation(df: pd.DataFrame, breakout_idx: int = -1, lookback: int = 20) -> float:
    """
    돌파 시점의 거래량 확인 (0.0 ~ 1.0)
    3x 이상 → 1.0, 2x → 0.85, 1.5x → 0.7, 1.2x → 0.55,
    평균 → 0.4, 0.5x 미만 → 0.1 (매우 약한 확인)
    """
    if "volume" not in df.columns or len(df) < lookback + 2:
        return 0.5

    vol = df["volume"].values
    if breakout_idx == -1:
        avg_vol = np.mean(vol[-(lookback + 1):-1])
        current_vol = vol[-1]
    else:
        start = max(0, breakout_idx - lookback)
        avg_vol = np.mean(vol[start:breakout_idx])
        current_vol = vol[breakout_idx]

    if avg_vol <= 0:
        return 0.5

    ratio = current_vol / avg_vol

    if ratio >= 3.0:
        return 1.0
    elif ratio >= 2.0:
        return 0.85 + (ratio - 2.0) / 1.0 * 0.15
    elif ratio >= 1.5:
        return 0.7 + (ratio - 1.5) / 0.5 * 0.15
    elif ratio >= 1.2:
        return 0.55 + (ratio - 1.2) / 0.3 * 0.15
    elif ratio >= 1.0:
        return 0.4 + (ratio - 1.0) / 0.2 * 0.15
    elif ratio >= 0.5:
        return 0.1 + (ratio - 0.5) / 0.5 * 0.3
    else:
        return 0.1  # 거래량 매우 부족: 패턴 신뢰도 크게 감소


def _calc_strength(geo_score: float, vol_factor: float) -> float:
    """기하학 점수 + 거래량 확인 → 최종 강도"""
    raw = geo_score * (0.6 + 0.4 * vol_factor)
    return max(0.3, min(0.95, raw))


# ─── 쌍봉 / 쌍바닥 ────────────────────────────────────────

def detect_double_top(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    쌍봉 (Double Top): 비슷한 고점 2개 + 사이 저점(넥라인)
    가격이 넥라인 아래로 하락하면 하락 시그널
    """
    if len(df) < 30:
        return None
    data = df.tail(60) if len(df) >= 60 else df
    highs_arr = data["high"].values
    close = data["close"].values[-1]

    swing_highs, _ = _find_swings(highs_arr, order=3)
    if len(swing_highs) < 2:
        return None

    h1_idx, h2_idx = swing_highs[-2], swing_highs[-1]
    h1, h2 = highs_arr[h1_idx], highs_arr[h2_idx]

    # 두 고점이 비슷한 레벨인지 (1.2% 이내)
    sym_pct = _pct_diff(h1, h2)
    if sym_pct > 1.2:
        return None

    # 최소 7봉 간격
    if h2_idx - h1_idx < 7:
        return None

    between = data["low"].values[h1_idx:h2_idx + 1]
    if len(between) < 2:
        return None
    neckline = float(np.min(between))

    peak_avg = (h1 + h2) / 2
    if close > peak_avg:
        return None

    # 기하학 품질
    pattern_height = peak_avg - neckline
    depth_ratio = pattern_height / peak_avg if peak_avg > 0 else 0
    remaining = max(1, len(data) - h2_idx)
    time_sym = (h2_idx - h1_idx) / remaining
    geo = _geometry_score(sym_pct, depth_ratio, time_sym, max_symmetry_pct=1.2)
    vol = _volume_confirmation(df)

    if close <= neckline * 1.005:
        strength = _calc_strength(geo, vol)
        return ChartPatternResult(
            name="쌍봉 (Double Top)",
            signal="short",
            strength=max(0.5, strength),
            description=f"넥라인(${neckline:.2f}) 하향 돌파 [품질:{geo:.0%}|거래량:{vol:.0%}] - 목표: ${neckline - pattern_height:.2f}"
        )
    elif close < peak_avg * 0.97:
        strength = _calc_strength(geo * 0.7, vol * 0.5)
        return ChartPatternResult(
            name="쌍봉 형성 중 (Double Top)",
            signal="short",
            strength=max(0.3, min(0.65, strength)),
            description=f"두 고점(${h1:.2f}, ${h2:.2f}) 형성, 넥라인 ${neckline:.2f} 주시"
        )
    return None


def detect_double_bottom(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    쌍바닥 (Double Bottom): 비슷한 저점 2개 + 사이 고점(넥라인)
    가격이 넥라인 위로 상승하면 상승 시그널
    """
    if len(df) < 30:
        return None
    data = df.tail(60) if len(df) >= 60 else df
    lows_arr = data["low"].values
    close = data["close"].values[-1]

    _, swing_lows = _find_swings(lows_arr, order=3)
    if len(swing_lows) < 2:
        _, swing_lows = _find_swings(data["low"].values, order=2)
        if len(swing_lows) < 2:
            return None

    l1_idx, l2_idx = swing_lows[-2], swing_lows[-1]
    l1, l2 = lows_arr[l1_idx], lows_arr[l2_idx]

    sym_pct = _pct_diff(l1, l2)
    if sym_pct > 1.2:
        return None

    if l2_idx - l1_idx < 7:
        return None

    between = data["high"].values[l1_idx:l2_idx + 1]
    if len(between) < 2:
        return None
    neckline = float(np.max(between))

    trough_avg = (l1 + l2) / 2
    if close < trough_avg:
        return None

    pattern_height = neckline - trough_avg
    depth_ratio = pattern_height / neckline if neckline > 0 else 0
    remaining = max(1, len(data) - l2_idx)
    time_sym = (l2_idx - l1_idx) / remaining
    geo = _geometry_score(sym_pct, depth_ratio, time_sym, max_symmetry_pct=1.2)
    vol = _volume_confirmation(df)

    if close >= neckline * 0.995:
        strength = _calc_strength(geo, vol)
        return ChartPatternResult(
            name="쌍바닥 (Double Bottom)",
            signal="long",
            strength=max(0.5, strength),
            description=f"넥라인(${neckline:.2f}) 상향 돌파 [품질:{geo:.0%}|거래량:{vol:.0%}] - 목표: ${neckline + pattern_height:.2f}"
        )
    elif close > trough_avg * 1.03:
        strength = _calc_strength(geo * 0.7, vol * 0.5)
        return ChartPatternResult(
            name="쌍바닥 형성 중 (Double Bottom)",
            signal="long",
            strength=max(0.3, min(0.65, strength)),
            description=f"두 저점(${l1:.2f}, ${l2:.2f}) 형성, 넥라인 ${neckline:.2f} 주시"
        )
    return None


# ─── 헤드앤숄더 ─────────────────────────────────────────

def detect_head_and_shoulders(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    헤드앤숄더 (H&S): 3개의 고점, 중앙이 가장 높음
    역헤드앤숄더: 3개의 저점, 중앙이 가장 낮음
    """
    if len(df) < 40:
        return None
    data = df.tail(120) if len(df) >= 120 else df
    highs_arr = data["high"].values
    lows_arr = data["low"].values
    close = data["close"].values[-1]

    # 정방향 H&S (하락 시그널)
    swing_highs, _ = _find_swings(highs_arr, order=3)
    if len(swing_highs) >= 3:
        s1_idx, h_idx, s2_idx = swing_highs[-3], swing_highs[-2], swing_highs[-1]
        left_shoulder = highs_arr[s1_idx]
        head = highs_arr[h_idx]
        right_shoulder = highs_arr[s2_idx]

        shoulder_sym = _pct_diff(left_shoulder, right_shoulder)
        head_prominence = (head - (left_shoulder + right_shoulder) / 2) / head * 100 if head > 0 else 0

        if (head > left_shoulder * 1.03 and head > right_shoulder * 1.03
                and shoulder_sym < 2.0 and head_prominence > 1.5):
            trough1 = float(np.min(lows_arr[s1_idx:h_idx + 1]))
            trough2 = float(np.min(lows_arr[h_idx:s2_idx + 1]))
            neckline = (trough1 + trough2) / 2
            neckline_tilt = _pct_diff(trough1, trough2)

            # 기하학 점수
            time_sym = (h_idx - s1_idx) / max(1, s2_idx - h_idx)
            geo = _geometry_score(shoulder_sym, min(1.0, head_prominence / 10), time_sym, max_symmetry_pct=2.0)
            if neckline_tilt > 2.0:
                geo *= 0.8
            vol = _volume_confirmation(df)

            if close <= neckline * 1.005:
                target = neckline - (head - neckline)
                strength = _calc_strength(geo, vol)
                return ChartPatternResult(
                    name="헤드앤숄더 (Head & Shoulders)",
                    signal="short",
                    strength=max(0.55, strength),
                    description=f"넥라인(${neckline:.2f}) 하향 돌파 [품질:{geo:.0%}] - 목표: ${target:.2f}"
                )
            elif close < right_shoulder:
                strength = _calc_strength(geo * 0.7, vol * 0.5)
                return ChartPatternResult(
                    name="헤드앤숄더 형성 중",
                    signal="short",
                    strength=max(0.35, min(0.6, strength)),
                    description=f"우측 어깨 완성, 넥라인 ${neckline:.2f} 하향 돌파 주시"
                )

    # 역헤드앤숄더 (상승 시그널)
    _, swing_lows = _find_swings(lows_arr, order=3)
    if len(swing_lows) >= 3:
        s1_idx, h_idx, s2_idx = swing_lows[-3], swing_lows[-2], swing_lows[-1]
        left_shoulder = lows_arr[s1_idx]
        head = lows_arr[h_idx]
        right_shoulder = lows_arr[s2_idx]

        shoulder_sym = _pct_diff(left_shoulder, right_shoulder)
        head_prominence = ((left_shoulder + right_shoulder) / 2 - head) / head * 100 if head > 0 else 0

        if (head < left_shoulder * 0.97 and head < right_shoulder * 0.97
                and shoulder_sym < 2.0 and head_prominence > 1.5):
            peak1 = float(np.max(highs_arr[s1_idx:h_idx + 1]))
            peak2 = float(np.max(highs_arr[h_idx:s2_idx + 1]))
            neckline = (peak1 + peak2) / 2
            neckline_tilt = _pct_diff(peak1, peak2)

            time_sym = (h_idx - s1_idx) / max(1, s2_idx - h_idx)
            geo = _geometry_score(shoulder_sym, min(1.0, head_prominence / 10), time_sym, max_symmetry_pct=2.0)
            if neckline_tilt > 2.0:
                geo *= 0.8
            vol = _volume_confirmation(df)

            if close >= neckline * 0.995:
                target = neckline + (neckline - head)
                strength = _calc_strength(geo, vol)
                return ChartPatternResult(
                    name="역헤드앤숄더 (Inverse H&S)",
                    signal="long",
                    strength=max(0.55, strength),
                    description=f"넥라인(${neckline:.2f}) 상향 돌파 [품질:{geo:.0%}] - 목표: ${target:.2f}"
                )
            elif close > right_shoulder:
                strength = _calc_strength(geo * 0.7, vol * 0.5)
                return ChartPatternResult(
                    name="역헤드앤숄더 형성 중",
                    signal="long",
                    strength=max(0.35, min(0.6, strength)),
                    description=f"우측 어깨 완성, 넥라인 ${neckline:.2f} 상향 돌파 주시"
                )
    return None


# ─── 삼각 수렴 (Triangle) ──────────────────────────────

def detect_triangle(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """삼각 수렴 패턴: 대칭/상승/하락 삼각형"""
    if len(df) < 30:
        return None
    data = df.tail(50) if len(df) >= 50 else df
    highs_arr = data["high"].values
    lows_arr = data["low"].values

    swing_highs, swing_lows = _find_swings(highs_arr, order=2)
    _, swing_lows2 = _find_swings(lows_arr, order=2)
    swing_lows = swing_lows2 if len(swing_lows2) > len(swing_lows) else swing_lows

    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    recent_highs = np.array([highs_arr[i] for i in swing_highs[-4:]])
    recent_lows = np.array([lows_arr[i] for i in swing_lows[-4:]])

    high_slope, high_r2 = _linear_regression(recent_highs)
    low_slope, low_r2 = _linear_regression(recent_lows)

    avg_price = (recent_highs.mean() + recent_lows.mean()) / 2
    if avg_price == 0:
        return None
    high_slope_pct = high_slope / avg_price * 100
    low_slope_pct = low_slope / avg_price * 100

    range_first = recent_highs[0] - recent_lows[0] if len(recent_lows) > 0 else 0
    range_last = recent_highs[-1] - recent_lows[-1] if len(recent_lows) > 0 else 0

    if range_first <= 0 or range_last <= 0:
        return None
    if range_last >= range_first * 0.9:
        return None

    # 트렌드라인 품질 기반 강도
    trendline_quality = (high_r2 + low_r2) / 2
    convergence_ratio = 1.0 - range_last / range_first

    # 돌파 위치: 삼각형 외곽에 있으면 보너스
    current_price = data["close"].values[-1]
    tri_top = recent_highs[-1]
    tri_bottom = recent_lows[-1]
    tri_range = tri_top - tri_bottom
    position_bonus = 0.2 if tri_range > 0 and (
        (current_price - tri_bottom) / tri_range > 0.85 or
        (current_price - tri_bottom) / tri_range < 0.15
    ) else 0.0

    geo = convergence_ratio * 0.4 + trendline_quality * 0.4 + position_bonus
    vol = _volume_confirmation(df)

    if abs(high_slope_pct) < 0.3 and low_slope_pct > 0.1 and low_r2 > 0.5:
        strength = _calc_strength(geo, vol)
        return ChartPatternResult(
            name="상승 삼각형 (Ascending Triangle)",
            signal="long",
            strength=strength,
            description=f"저항선 ${recent_highs[-1]:.2f} 수평 + 지지선 상승 [R²:{trendline_quality:.0%}] - 상방 돌파 기대"
        )

    if abs(low_slope_pct) < 0.3 and high_slope_pct < -0.1 and high_r2 > 0.5:
        strength = _calc_strength(geo, vol)
        return ChartPatternResult(
            name="하락 삼각형 (Descending Triangle)",
            signal="short",
            strength=strength,
            description=f"지지선 ${recent_lows[-1]:.2f} 수평 + 저항선 하락 [R²:{trendline_quality:.0%}] - 하방 돌파 기대"
        )

    if high_slope_pct < -0.1 and low_slope_pct > 0.1:
        strength = _calc_strength(geo * 0.8, vol)
        return ChartPatternResult(
            name="대칭 삼각형 (Symmetrical Triangle)",
            signal="neutral",
            strength=min(0.65, strength),
            description=f"수렴 진행 중 [수렴률:{convergence_ratio:.0%}] - 돌파 방향 주시"
        )

    return None


# ─── 웨지 (Wedge) ──────────────────────────────────────

def detect_wedge(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """웨지 패턴: 상승/하락 웨지"""
    if len(df) < 30:
        return None
    data = df.tail(50) if len(df) >= 50 else df
    highs_arr = data["high"].values
    lows_arr = data["low"].values

    swing_highs, _ = _find_swings(highs_arr, order=2)
    _, swing_lows = _find_swings(lows_arr, order=2)

    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    recent_highs = np.array([highs_arr[i] for i in swing_highs[-4:]])
    recent_lows = np.array([lows_arr[i] for i in swing_lows[-4:]])

    high_slope, high_r2 = _linear_regression(recent_highs)
    low_slope, low_r2 = _linear_regression(recent_lows)

    avg_price = (recent_highs.mean() + recent_lows.mean()) / 2
    if avg_price == 0:
        return None
    high_slope_pct = high_slope / avg_price * 100
    low_slope_pct = low_slope / avg_price * 100

    range_first = recent_highs[0] - recent_lows[0]
    range_last = recent_highs[-1] - recent_lows[-1]
    if range_first <= 0 or range_last >= range_first * 0.85:
        return None

    # R² 품질 요구
    if high_r2 < 0.5 or low_r2 < 0.5:
        return None

    trendline_quality = (high_r2 + low_r2) / 2
    convergence = 1.0 - range_last / range_first
    geo = trendline_quality * 0.5 + convergence * 0.5
    vol = _volume_confirmation(df)

    if high_slope_pct > 0.1 and low_slope_pct > 0.1:
        strength = _calc_strength(geo, vol)
        return ChartPatternResult(
            name="상승 웨지 (Rising Wedge)",
            signal="short",
            strength=strength,
            description=f"고점/저점 모두 상승 + 수렴 [R²:{trendline_quality:.0%}] - 하락 반전 가능"
        )

    if high_slope_pct < -0.1 and low_slope_pct < -0.1:
        strength = _calc_strength(geo, vol)
        return ChartPatternResult(
            name="하락 웨지 (Falling Wedge)",
            signal="long",
            strength=strength,
            description=f"고점/저점 모두 하락 + 수렴 [R²:{trendline_quality:.0%}] - 상승 반전 가능"
        )

    return None


# ─── 플래그 / 페넌트 ───────────────────────────────────

def detect_flag(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """플래그 패턴: 강한 추세 후 반대 방향 좁은 채널 형성"""
    if len(df) < 25:
        return None
    data = df.tail(40) if len(df) >= 40 else df
    close_arr = data["close"].values

    pole_len = min(10, len(close_arr) // 3)
    flag_len = min(15, len(close_arr) - pole_len)

    if flag_len < 5:
        return None

    pole = close_arr[:pole_len]
    flag_data = close_arr[-flag_len:]

    pole_change = (pole[-1] - pole[0]) / pole[0] * 100 if pole[0] > 0 else 0

    flag_slope, flag_r2 = _linear_regression(flag_data)
    flag_range = (flag_data.max() - flag_data.min()) / flag_data.mean() * 100 if flag_data.mean() > 0 else 0

    # 플래그 정돈도 확인
    if flag_r2 < 0.4:
        return None

    # 폴/플래그 거래량 비교
    vol_score = 0.5
    if "volume" in df.columns and len(df) >= pole_len + flag_len:
        vol_arr = df["volume"].values
        pole_vol = np.mean(vol_arr[:pole_len])
        flag_vol = np.mean(vol_arr[-flag_len:])
        if flag_vol > 0:
            vol_ratio = pole_vol / flag_vol
            vol_score = min(1.0, vol_ratio / 2.0)

    # 불 플래그: 강한 상승(>4%) 후 좁은 하향 조정(<2.5%)
    if pole_change > 4.0 and flag_slope < 0 and flag_range < 2.5:
        geo = 0.5 + flag_r2 * 0.3 + (1.0 - flag_range / 2.5) * 0.2
        strength = _calc_strength(geo, vol_score)
        return ChartPatternResult(
            name="불 플래그 (Bull Flag)",
            signal="long",
            strength=strength,
            description=f"급등({pole_change:.1f}%) 후 조정 [정돈도:{flag_r2:.0%}] - 상방 돌파 시 추세 지속"
        )

    if pole_change < -4.0 and flag_slope > 0 and flag_range < 2.5:
        geo = 0.5 + flag_r2 * 0.3 + (1.0 - flag_range / 2.5) * 0.2
        strength = _calc_strength(geo, vol_score)
        return ChartPatternResult(
            name="베어 플래그 (Bear Flag)",
            signal="short",
            strength=strength,
            description=f"급락({pole_change:.1f}%) 후 반등 [정돈도:{flag_r2:.0%}] - 하방 돌파 시 추세 지속"
        )

    return None


# ─── 채널 패턴 ─────────────────────────────────────────

def detect_channel(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """채널 패턴: 평행한 상/하 추세선"""
    if len(df) < 30:
        return None
    data = df.tail(50) if len(df) >= 50 else df
    highs_arr = data["high"].values
    lows_arr = data["low"].values
    close = data["close"].values[-1]

    high_slope, high_r2 = _linear_regression(highs_arr)
    low_slope, low_r2 = _linear_regression(lows_arr)

    if high_r2 < 0.6 or low_r2 < 0.6:
        return None

    avg_price = (highs_arr.mean() + lows_arr.mean()) / 2
    if avg_price == 0:
        return None

    high_slope_pct = high_slope / avg_price * 100
    low_slope_pct = low_slope / avg_price * 100

    if abs(high_slope_pct - low_slope_pct) > 0.5:
        return None

    avg_slope = (high_slope_pct + low_slope_pct) / 2

    channel_top = highs_arr[-1]
    channel_bottom = lows_arr[-1]
    channel_width = channel_top - channel_bottom
    if channel_width <= 0:
        return None
    position = (close - channel_bottom) / channel_width

    # 채널 품질 점수
    channel_quality = (high_r2 + low_r2) / 2
    vol = _volume_confirmation(df)

    if avg_slope > 0.1:
        if position > 0.85:
            strength = _calc_strength(channel_quality * 0.8, vol)
            return ChartPatternResult(
                name="상승 채널 상단 (Rising Channel)",
                signal="short",
                strength=strength,
                description=f"상승 채널 상단 접근 [R²:{channel_quality:.0%}] - 단기 조정 가능"
            )
        elif position < 0.15:
            strength = _calc_strength(channel_quality * 0.9, vol)
            return ChartPatternResult(
                name="상승 채널 하단 (Rising Channel)",
                signal="long",
                strength=strength,
                description=f"상승 채널 하단 지지 [R²:{channel_quality:.0%}] - 반등 기대"
            )
    elif avg_slope < -0.1:
        if position < 0.15:
            strength = _calc_strength(channel_quality * 0.8, vol)
            return ChartPatternResult(
                name="하락 채널 하단 (Falling Channel)",
                signal="long",
                strength=strength,
                description=f"하락 채널 하단 접근 [R²:{channel_quality:.0%}] - 단기 반등 가능"
            )
        elif position > 0.85:
            strength = _calc_strength(channel_quality * 0.9, vol)
            return ChartPatternResult(
                name="하락 채널 상단 (Falling Channel)",
                signal="short",
                strength=strength,
                description=f"하락 채널 상단 저항 [R²:{channel_quality:.0%}] - 재하락 기대"
            )

    return None


# ─── 컵앤핸들 ──────────────────────────────────────────

def detect_cup_and_handle(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """컵앤핸들 (Cup & Handle): U자형 바닥 + 작은 하락 조정(핸들)"""
    if len(df) < 40:
        return None
    data = df.tail(120) if len(df) >= 120 else df
    close = data["close"].values
    n = len(close)

    cup_start = 0
    cup_end = int(n * 0.75)
    handle_start = cup_end
    handle_end = n

    if cup_end - cup_start < 20 or handle_end - handle_start < 3:
        return None

    cup = close[cup_start:cup_end]
    handle = close[handle_start:handle_end]

    cup_min_idx = int(np.argmin(cup))
    cup_min = cup[cup_min_idx]
    left_rim = cup[0]
    right_rim = cup[-1]

    if cup_min >= left_rim * 0.97 or cup_min >= right_rim * 0.97:
        return None
    if _pct_diff(left_rim, right_rim) > 3.0:
        return None

    cup_depth = ((left_rim + right_rim) / 2) - cup_min
    handle_low = handle.min()
    handle_dip = right_rim - handle_low

    if cup_depth <= 0 or handle_dip > cup_depth * 0.5:
        return None
    if handle_dip < cup_depth * 0.1:
        return None

    neckline = (left_rim + right_rim) / 2

    # 기하학: 림 대칭, 컵 깊이, U자 위치
    rim_sym = _pct_diff(left_rim, right_rim)
    cup_position = cup_min_idx / max(1, len(cup))
    cup_shape_score = 1.0 - abs(cup_position - 0.5) * 2
    geo = _geometry_score(rim_sym, min(1.0, cup_depth / neckline * 5), cup_shape_score, max_symmetry_pct=3.0)
    vol = _volume_confirmation(df)

    if close[-1] >= neckline * 0.98:
        strength = _calc_strength(geo, vol)
        return ChartPatternResult(
            name="컵앤핸들 (Cup & Handle)",
            signal="long",
            strength=max(0.55, strength),
            description=f"컵앤핸들 완성 [품질:{geo:.0%}] - 넥라인 ${neckline:.2f} 돌파 시 목표: ${neckline + cup_depth:.2f}"
        )

    return None


# ─── 엘리엇 파동 ───────────────────────────────────────

def detect_elliott_wave(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """엘리엇 파동 (Elliott Wave) 감지 — 피보나치 비율 검증 포함"""
    if len(df) < 50:
        return None
    data = df.tail(150) if len(df) >= 150 else df
    close = data["close"].values
    highs = data["high"].values
    lows = data["low"].values

    swing_highs, swing_lows = _find_swings(close, order=3)

    result = _detect_impulse_up(close, highs, lows, swing_highs, swing_lows)
    if result:
        return result

    result = _detect_impulse_down(close, highs, lows, swing_highs, swing_lows)
    if result:
        return result

    result = _detect_abc_correction(close, highs, lows, swing_highs, swing_lows)
    if result:
        return result

    return None


def _fib_score(actual_ratio: float, ideal_ratio: float) -> float:
    """피보나치 비율 준수도 (0.0 ~ 1.0)"""
    if ideal_ratio <= 0:
        return 0.5
    deviation = abs(actual_ratio - ideal_ratio) / ideal_ratio
    return max(0.0, 1.0 - deviation)


def _detect_impulse_up(
    close: np.ndarray, highs: np.ndarray, lows: np.ndarray,
    swing_highs: List[int], swing_lows: List[int],
) -> Optional[ChartPatternResult]:
    """상승 5파 충격파 감지"""
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    try:
        pivots = _merge_swings(close, swing_highs, swing_lows)
        if len(pivots) < 6:
            return None

        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            if p[0][1] != "low":
                continue

            w0, w1, w2, w3, w4, w5 = p[0][2], p[1][2], p[2][2], p[3][2], p[4][2], p[5][2]

            if not (w1 > w0 and w2 < w1 and w3 > w1 and w4 < w3 and w5 > w3):
                continue

            if w2 <= w0:
                continue

            wave1 = w1 - w0
            wave3 = w3 - w2
            wave5 = w5 - w4
            if wave3 < wave1 and wave3 < wave5:
                continue

            if w4 <= w1:
                continue

            # 피보나치 비율 점수
            fib_3_1 = wave3 / wave1 if wave1 > 0 else 0
            fib_5_1 = wave5 / wave1 if wave1 > 0 else 0
            fib3_score = _fib_score(fib_3_1, 1.618)
            fib5_score = _fib_score(fib_5_1, 1.0)
            geo = (fib3_score + fib5_score) / 2

            current = close[-1]
            if current >= w5 * 0.98:
                strength = max(0.45, min(0.8, geo))
                return ChartPatternResult(
                    name="엘리엇 5파 완성 (상승)",
                    signal="short",
                    strength=strength,
                    description=f"상승 5파 완성 [피보나치 3/1:{fib_3_1:.2f}] - ABC 조정 예상"
                )
            elif current >= w3 and current < w5:
                strength = max(0.35, min(0.65, geo * 0.8))
                return ChartPatternResult(
                    name="엘리엇 5파 진행 중 (상승)",
                    signal="long",
                    strength=strength,
                    description="상승 5파 진행 중 - 추세 지속 가능"
                )
    except Exception:
        pass

    return None


def _detect_impulse_down(
    close: np.ndarray, highs: np.ndarray, lows: np.ndarray,
    swing_highs: List[int], swing_lows: List[int],
) -> Optional[ChartPatternResult]:
    """하락 5파 충격파 감지"""
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    try:
        pivots = _merge_swings(close, swing_highs, swing_lows)
        if len(pivots) < 6:
            return None

        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            if p[0][1] != "high":
                continue

            w0, w1, w2, w3, w4, w5 = p[0][2], p[1][2], p[2][2], p[3][2], p[4][2], p[5][2]

            if not (w1 < w0 and w2 > w1 and w3 < w1 and w4 > w3 and w5 < w3):
                continue
            if w2 >= w0:
                continue

            wave1 = w0 - w1
            wave3 = w2 - w3
            wave5 = w4 - w5
            if wave3 < wave1 and wave3 < wave5:
                continue
            if w4 >= w1:
                continue

            fib_3_1 = wave3 / wave1 if wave1 > 0 else 0
            fib_5_1 = wave5 / wave1 if wave1 > 0 else 0
            fib3_score = _fib_score(fib_3_1, 1.618)
            fib5_score = _fib_score(fib_5_1, 1.0)
            geo = (fib3_score + fib5_score) / 2

            current = close[-1]
            if current <= w5 * 1.02:
                strength = max(0.45, min(0.8, geo))
                return ChartPatternResult(
                    name="엘리엇 5파 완성 (하락)",
                    signal="long",
                    strength=strength,
                    description=f"하락 5파 완성 [피보나치 3/1:{fib_3_1:.2f}] - ABC 반등 예상"
                )
            elif current <= w3 and current > w5:
                strength = max(0.35, min(0.65, geo * 0.8))
                return ChartPatternResult(
                    name="엘리엇 5파 진행 중 (하락)",
                    signal="short",
                    strength=strength,
                    description="하락 5파 진행 중 - 추세 지속 가능"
                )
    except Exception:
        pass

    return None


def _detect_abc_correction(
    close: np.ndarray, highs: np.ndarray, lows: np.ndarray,
    swing_highs: List[int], swing_lows: List[int],
) -> Optional[ChartPatternResult]:
    """ABC 조정파 감지"""
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    try:
        pivots = _merge_swings(close, swing_highs, swing_lows)
        if len(pivots) < 4:
            return None

        # 하락 ABC
        for i in range(len(pivots) - 3):
            p = pivots[i:i + 4]
            if p[0][1] != "high":
                continue

            a_start, a_end, b_end, c_end = p[0][2], p[1][2], p[2][2], p[3][2]

            if a_end < a_start and b_end > a_end and c_end < a_end:
                a_wave = a_start - a_end
                c_wave = b_end - c_end
                ratio = c_wave / a_wave if a_wave > 0 else 0
                fib_score = _fib_score(ratio, 1.0) * 0.5 + _fib_score(ratio, 0.618) * 0.5

                if 0.5 < ratio < 2.0:
                    current = close[-1]
                    if current <= c_end * 1.02:
                        strength = max(0.45, min(0.75, fib_score))
                        return ChartPatternResult(
                            name="ABC 조정 완료 (하락)",
                            signal="long",
                            strength=strength,
                            description=f"ABC 조정 완료 (C/A: {ratio:.2f}) [피보나치:{fib_score:.0%}] - 상승 충격파 기대"
                        )

        # 상승 ABC
        for i in range(len(pivots) - 3):
            p = pivots[i:i + 4]
            if p[0][1] != "low":
                continue

            a_start, a_end, b_end, c_end = p[0][2], p[1][2], p[2][2], p[3][2]

            if a_end > a_start and b_end < a_end and c_end > a_end:
                a_wave = a_end - a_start
                c_wave = c_end - b_end
                ratio = c_wave / a_wave if a_wave > 0 else 0
                fib_score = _fib_score(ratio, 1.0) * 0.5 + _fib_score(ratio, 0.618) * 0.5

                if 0.5 < ratio < 2.0:
                    current = close[-1]
                    if current >= c_end * 0.98:
                        strength = max(0.45, min(0.75, fib_score))
                        return ChartPatternResult(
                            name="ABC 조정 완료 (상승)",
                            signal="short",
                            strength=strength,
                            description=f"ABC 반등 완료 (C/A: {ratio:.2f}) [피보나치:{fib_score:.0%}] - 하락 충격파 기대"
                        )
    except Exception:
        pass

    return None


def _merge_swings(
    close: np.ndarray,
    swing_highs: List[int],
    swing_lows: List[int],
) -> List[Tuple[int, str, float]]:
    """스윙 하이/로우를 시간순으로 병합: [(index, "high"/"low", price), ...]"""
    pivots = []
    for idx in swing_highs:
        pivots.append((idx, "high", float(close[idx])))
    for idx in swing_lows:
        pivots.append((idx, "low", float(close[idx])))

    pivots.sort(key=lambda x: x[0])

    if len(pivots) < 2:
        return pivots

    cleaned = [pivots[0]]
    for p in pivots[1:]:
        if p[1] == cleaned[-1][1]:
            if p[1] == "high" and p[2] > cleaned[-1][2]:
                cleaned[-1] = p
            elif p[1] == "low" and p[2] < cleaned[-1][2]:
                cleaned[-1] = p
        else:
            cleaned.append(p)

    return cleaned


# ─── 트리플 탑/바텀 ────────────────────────────────────

def detect_triple_top_bottom(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """트리플 탑/바텀: 3번의 비슷한 고점/저점"""
    if len(df) < 40:
        return None
    data = df.tail(120) if len(df) >= 120 else df
    highs_arr = data["high"].values
    lows_arr = data["low"].values
    close = data["close"].values[-1]

    swing_highs, swing_lows = _find_swings(highs_arr, order=3)

    # 트리플 탑
    if len(swing_highs) >= 3:
        idxs = swing_highs[-3:]
        tops = [highs_arr[i] for i in idxs]
        avg_top = np.mean(tops)

        # 최소 5봉 간격
        min_spacing = all(idxs[j + 1] - idxs[j] >= 5 for j in range(len(idxs) - 1))

        if min_spacing and all(_pct_diff(t, avg_top) < 1.5 for t in tops):
            neckline = float(np.min(lows_arr[idxs[0]:idxs[-1] + 1]))
            sym_pct = max(_pct_diff(tops[0], tops[1]), _pct_diff(tops[1], tops[2]))
            geo = _geometry_score(sym_pct, 0.5, 1.0, max_symmetry_pct=1.5)
            vol = _volume_confirmation(df)

            if close <= neckline * 1.005:
                strength = _calc_strength(geo, vol)
                return ChartPatternResult(
                    name="트리플 탑 (Triple Top)",
                    signal="short",
                    strength=max(0.6, strength),
                    description=f"3중 천정(${avg_top:.2f}) 확인 [품질:{geo:.0%}] - 강한 하락 시그널"
                )

    # 트리플 바텀
    _, swing_lows2 = _find_swings(lows_arr, order=3)
    if len(swing_lows2) >= 3:
        idxs = swing_lows2[-3:]
        bottoms = [lows_arr[i] for i in idxs]
        avg_bottom = np.mean(bottoms)

        min_spacing = all(idxs[j + 1] - idxs[j] >= 5 for j in range(len(idxs) - 1))

        if min_spacing and all(_pct_diff(b, avg_bottom) < 1.5 for b in bottoms):
            neckline = float(np.max(highs_arr[idxs[0]:idxs[-1] + 1]))
            sym_pct = max(_pct_diff(bottoms[0], bottoms[1]), _pct_diff(bottoms[1], bottoms[2]))
            geo = _geometry_score(sym_pct, 0.5, 1.0, max_symmetry_pct=1.5)
            vol = _volume_confirmation(df)

            if close >= neckline * 0.995:
                strength = _calc_strength(geo, vol)
                return ChartPatternResult(
                    name="트리플 바텀 (Triple Bottom)",
                    signal="long",
                    strength=max(0.6, strength),
                    description=f"3중 바닥(${avg_bottom:.2f}) 확인 [품질:{geo:.0%}] - 강한 상승 시그널"
                )

    return None


# ─── 충돌 패턴 제거 ────────────────────────────────────

# ─── 신규 패턴: Rectangle/Range ──────────────────────────

def detect_rectangle(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """사각형(박스권): 수평 지지/저항에 2+ 터치"""
    if len(df) < 40:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    lookback = min(60, len(df))
    recent_h = high[-lookback:]
    recent_l = low[-lookback:]

    swing_highs, swing_lows = _find_swings(close[-lookback:], order=2)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    # 고점 클러스터링 (1.5% 이내)
    h_prices = [float(recent_h[i]) for i in swing_highs]
    l_prices = [float(recent_l[i]) for i in swing_lows]

    avg_h = np.mean(h_prices)
    avg_l = np.mean(l_prices)
    if avg_l <= 0 or avg_h <= avg_l:
        return None

    h_spread = max(h_prices) - min(h_prices)
    l_spread = max(l_prices) - min(l_prices)
    range_height = avg_h - avg_l
    range_pct = range_height / avg_l * 100

    # 고점/저점이 각각 1.5% 이내에 클러스터
    if h_spread / avg_h * 100 > 1.5 or l_spread / avg_l * 100 > 1.5:
        return None

    # 범위가 너무 좁거나 넓으면 제외
    if range_pct < 1.0 or range_pct > 15.0:
        return None

    # 현재 가격 위치
    curr = close[-1]
    pos_in_range = (curr - avg_l) / range_height

    vol = _volume_confirmation(df)
    touch_count = len(swing_highs) + len(swing_lows)
    geo = min(1.0, touch_count / 8)  # 터치 많을수록 신뢰
    strength = _calc_strength(geo, vol)

    if pos_in_range > 0.85:
        return ChartPatternResult(
            "사각형 (상단)", "short", strength,
            f"박스권 상단 근접 ({range_pct:.1f}% 범위, {touch_count}회 터치)"
        )
    elif pos_in_range < 0.15:
        return ChartPatternResult(
            "사각형 (하단)", "long", strength,
            f"박스권 하단 근접 ({range_pct:.1f}% 범위, {touch_count}회 터치)"
        )
    else:
        return ChartPatternResult(
            "사각형 (박스권)", "neutral", strength * 0.6,
            f"박스권 내부 ({range_pct:.1f}% 범위, 위치 {pos_in_range:.0%})"
        )


# ─── 신규 패턴: Pennant ───────────────────────────────────

def detect_pennant(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """페넌트: 강한 폴 + 수렴하는 삼각형 컨솔리데이션"""
    if len(df) < 25:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    pole_len = min(15, len(df) // 3)
    flag_len = min(15, len(df) // 3)
    if pole_len < 5 or flag_len < 5:
        return None

    pole_start = -(pole_len + flag_len)
    pole_end = -flag_len

    pole_move = (close[pole_end] - close[pole_start]) / close[pole_start] * 100

    if abs(pole_move) < 4.0:
        return None

    flag_high = high[-flag_len:]
    flag_low = low[-flag_len:]

    h_slope, h_r2 = _linear_regression(flag_high)
    l_slope, l_r2 = _linear_regression(flag_low)

    # 수렴 확인: 슬로프가 서로 반대 방향
    if h_slope * l_slope > 0:
        return None  # 같은 방향이면 플래그 또는 채널

    # 수렴 범위 감소 확인
    range_start = flag_high[0] - flag_low[0]
    range_end = flag_high[-1] - flag_low[-1]
    if range_start <= 0 or range_end / range_start > 0.8:
        return None

    # 컨솔리데이션 범위가 폴 대비 적절
    flag_range_pct = (max(flag_high) - min(flag_low)) / close[pole_start] * 100
    if flag_range_pct > abs(pole_move) * 0.5:
        return None

    vol = _volume_confirmation(df)
    convergence = 1.0 - range_end / range_start
    geo = min(1.0, convergence + 0.3)
    strength = _calc_strength(geo, vol)

    if pole_move > 0:
        return ChartPatternResult(
            "상승 페넌트", "long", strength,
            f"강한 상승 폴({pole_move:.1f}%) + 수렴 컨솔리데이션"
        )
    else:
        return ChartPatternResult(
            "하락 페넌트", "short", strength,
            f"강한 하락 폴({pole_move:.1f}%) + 수렴 컨솔리데이션"
        )


# ─── 신규 패턴: Gap Analysis ─────────────────────────────

def detect_gaps(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """갭 분석: Breakaway, Exhaustion, Island Reversal"""
    if len(df) < 20:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    vol = df["volume"].values if "volume" in df.columns else None

    lookback = min(15, len(df) - 1)
    best_gap = None
    best_pct = 0.0

    for i in range(-lookback, 0):
        idx = len(df) + i
        if idx < 1:
            continue
        # 갭 업: 현재 low > 이전 high
        if low[idx] > high[idx - 1]:
            gap_pct = (low[idx] - high[idx - 1]) / high[idx - 1] * 100
            if gap_pct > best_pct:
                best_pct = gap_pct
                best_gap = ("up", idx, gap_pct)
        # 갭 다운: 현재 high < 이전 low
        elif high[idx] < low[idx - 1]:
            gap_pct = (low[idx - 1] - high[idx]) / low[idx - 1] * 100
            if gap_pct > best_pct:
                best_pct = gap_pct
                best_gap = ("down", idx, gap_pct)

    if not best_gap or best_pct < 0.5:
        return None

    direction, gap_idx, gap_pct = best_gap

    # 갭이 최근 3봉 이내인지 확인 (아일랜드 리버설 후보)
    recency = len(df) - gap_idx
    vol_factor = 0.5
    if vol is not None and gap_idx >= 2:
        avg = np.mean(vol[max(0, gap_idx - 20):gap_idx])
        if avg > 0:
            vol_factor = min(1.0, vol[gap_idx] / avg / 2.0)

    strength = _calc_strength(min(1.0, gap_pct / 3.0), vol_factor)

    # 갭 미충전 + 최근 → 강한 시그널
    if recency <= 3:
        strength = min(0.95, strength * 1.2)

    if direction == "up":
        if recency <= 5:
            return ChartPatternResult(
                "돌파 갭 (상승)", "long", strength,
                f"상승 갭 {gap_pct:.2f}% (미충전, {recency}봉 전)"
            )
        else:
            return ChartPatternResult(
                "갭 (상승)", "long", strength * 0.7,
                f"상승 갭 {gap_pct:.2f}% ({recency}봉 전)"
            )
    else:
        if recency <= 5:
            return ChartPatternResult(
                "돌파 갭 (하락)", "short", strength,
                f"하락 갭 {gap_pct:.2f}% (미충전, {recency}봉 전)"
            )
        else:
            return ChartPatternResult(
                "갭 (하락)", "short", strength * 0.7,
                f"하락 갭 {gap_pct:.2f}% ({recency}봉 전)"
            )


# ─── 신규 패턴: Broadening Formation ─────────────────────

def detect_broadening_formation(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """확장 패턴 (메가폰): 발산하는 고점+저점"""
    if len(df) < 40:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    lookback = min(50, len(df))
    swing_highs, swing_lows = _find_swings(close[-lookback:], order=2)

    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    h_prices = np.array([float(high[-lookback + i]) for i in swing_highs])
    l_prices = np.array([float(low[-lookback + i]) for i in swing_lows])

    h_slope, h_r2 = _linear_regression(h_prices)
    l_slope, l_r2 = _linear_regression(l_prices)

    # 고점은 상승, 저점은 하락 (발산)
    if not (h_slope > 0 and l_slope < 0):
        return None

    if h_r2 < 0.3 or l_r2 < 0.3:
        return None

    # 범위 확장 확인
    range_start = h_prices[0] - l_prices[0] if len(h_prices) > 0 and len(l_prices) > 0 else 0
    range_end = h_prices[-1] - l_prices[-1]
    if range_start <= 0 or range_end / range_start < 1.3:
        return None

    vol = _volume_confirmation(df)
    divergence = range_end / range_start
    geo = min(1.0, (h_r2 + l_r2) / 2 * divergence * 0.6)
    strength = _calc_strength(geo, vol)

    # 현재 위치 기반 시그널
    curr = close[-1]
    mid = (h_prices[-1] + l_prices[-1]) / 2

    if curr > mid:
        return ChartPatternResult(
            "확장 패턴 (상단)", "short", strength,
            f"메가폰 상단 (확장비 {divergence:.1f}x, R² h={h_r2:.2f} l={l_r2:.2f})"
        )
    else:
        return ChartPatternResult(
            "확장 패턴 (하단)", "long", strength,
            f"메가폰 하단 (확장비 {divergence:.1f}x, R² h={h_r2:.2f} l={l_r2:.2f})"
        )


# ─── 신규 패턴: Diamond ──────────────────────────────────

def detect_diamond(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """다이아몬드 패턴: 전반부 확장 + 후반부 수축"""
    if len(df) < 40:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    lookback = min(50, len(df))
    mid = lookback // 2

    recent_h = high[-lookback:]
    recent_l = low[-lookback:]

    # 전반부/후반부 범위 비교
    first_half_ranges = recent_h[:mid] - recent_l[:mid]
    second_half_ranges = recent_h[mid:] - recent_l[mid:]

    if len(first_half_ranges) < 5 or len(second_half_ranges) < 5:
        return None

    # 전반부: 범위 확대
    fh_slope, fh_r2 = _linear_regression(first_half_ranges)
    # 후반부: 범위 축소
    sh_slope, sh_r2 = _linear_regression(second_half_ranges)

    if not (fh_slope > 0 and sh_slope < 0):
        return None

    # 중간 지점이 최대 범위
    mid_range = np.max(first_half_ranges[-3:])
    start_range = np.mean(first_half_ranges[:3])
    end_range = np.mean(second_half_ranges[-3:])

    if start_range <= 0 or mid_range / start_range < 1.3:
        return None
    if mid_range <= 0 or end_range / mid_range > 0.7:
        return None

    vol = _volume_confirmation(df)
    geo = min(1.0, (fh_r2 + sh_r2) / 2 * 1.2)
    strength = _calc_strength(geo, vol)

    # 다이아몬드 전 추세에 따라 방향 결정
    pre_trend = close[-lookback] - close[-lookback - min(20, lookback)]
    if pre_trend > 0:
        return ChartPatternResult(
            "다이아몬드 탑", "short", strength,
            f"상승 후 다이아몬드 형성 (확장→수축)"
        )
    else:
        return ChartPatternResult(
            "다이아몬드 바텀", "long", strength,
            f"하락 후 다이아몬드 형성 (확장→수축)"
        )


# ─── 신규 패턴: Rounding Bottom ──────────────────────────

def detect_rounding_bottom(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """라운딩 바텀 (소서): U자형 점진적 반전"""
    if len(df) < 60:
        return None

    close = df["close"].values
    lookback = min(80, len(df))
    recent = close[-lookback:]

    # 2차 회귀
    x = np.arange(len(recent), dtype=float)
    coeffs = np.polyfit(x, recent, 2)
    a, b, c = coeffs

    # a > 0 (위로 볼록) → 라운딩 바텀
    if a <= 0:
        return None

    # R² 확인
    predicted = np.polyval(coeffs, x)
    ss_res = np.sum((recent - predicted) ** 2)
    ss_tot = np.sum((recent - np.mean(recent)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    if r2 < 0.5:
        return None

    # 최저점이 중간 1/3에 위치
    min_idx = np.argmin(recent)
    if min_idx < len(recent) * 0.2 or min_idx > len(recent) * 0.8:
        return None

    # 현재 가격이 시작점 근처 또는 위에 (림 돌파)
    rim_price = max(recent[0], recent[1])
    curr = close[-1]
    rim_break = curr > rim_price

    vol = _volume_confirmation(df)
    geo = r2 * (1.2 if rim_break else 0.8)
    strength = _calc_strength(min(1.0, geo), vol)

    if rim_break:
        return ChartPatternResult(
            "라운딩 바텀 (돌파)", "long", strength,
            f"U자형 반전 완성, 림 돌파 (R²={r2:.2f})"
        )
    else:
        return ChartPatternResult(
            "라운딩 바텀 (형성)", "long", strength * 0.7,
            f"U자형 반전 형성 중 (R²={r2:.2f})"
        )


# ─── 신규 패턴: Harmonic Patterns ────────────────────────

def detect_harmonic_pattern(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """하모닉 패턴: Gartley, Butterfly, Bat (XABCD 피보나치)"""
    if len(df) < 40:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    swing_highs, swing_lows = _find_swings(close, order=2)
    pivots = _merge_swings(close, swing_highs, swing_lows)

    if len(pivots) < 5:
        return None

    # 마지막 5개 피벗 사용
    best_result = None
    best_score = 0.0

    for start in range(max(0, len(pivots) - 8), len(pivots) - 4):
        xabcd = pivots[start:start + 5]
        if len(xabcd) < 5:
            continue

        x_price = xabcd[0][2]
        a_price = xabcd[1][2]
        b_price = xabcd[2][2]
        c_price = xabcd[3][2]
        d_price = xabcd[4][2]

        xa = abs(a_price - x_price)
        ab = abs(b_price - a_price)
        bc = abs(c_price - b_price)
        cd = abs(d_price - c_price)

        if xa == 0 or ab == 0 or bc == 0:
            continue

        ab_xa = ab / xa  # AB retracement of XA
        bc_ab = bc / ab  # BC retracement of AB
        cd_bc = cd / bc  # CD extension of BC
        ad_xa = abs(d_price - x_price) / xa  # AD retracement of XA

        # Gartley: AB=0.618, BC=0.382-0.886, CD=1.272-1.618, AD=0.786
        gartley_score = (
            _fib_score(ab_xa, 0.618) * 0.3 +
            max(_fib_score(bc_ab, 0.382), _fib_score(bc_ab, 0.886)) * 0.2 +
            max(_fib_score(cd_bc, 1.272), _fib_score(cd_bc, 1.618)) * 0.2 +
            _fib_score(ad_xa, 0.786) * 0.3
        )

        # Butterfly: AB=0.786, BC=0.382-0.886, CD=1.618-2.618, AD=1.272
        butterfly_score = (
            _fib_score(ab_xa, 0.786) * 0.3 +
            max(_fib_score(bc_ab, 0.382), _fib_score(bc_ab, 0.886)) * 0.2 +
            max(_fib_score(cd_bc, 1.618), _fib_score(cd_bc, 2.618)) * 0.2 +
            _fib_score(ad_xa, 1.272) * 0.3
        )

        # Bat: AB=0.382-0.5, BC=0.382-0.886, CD=1.618-2.618, AD=0.886
        bat_score = (
            max(_fib_score(ab_xa, 0.382), _fib_score(ab_xa, 0.5)) * 0.3 +
            max(_fib_score(bc_ab, 0.382), _fib_score(bc_ab, 0.886)) * 0.2 +
            max(_fib_score(cd_bc, 1.618), _fib_score(cd_bc, 2.618)) * 0.2 +
            _fib_score(ad_xa, 0.886) * 0.3
        )

        patterns = [
            ("Gartley", gartley_score),
            ("Butterfly", butterfly_score),
            ("Bat", bat_score),
        ]
        best_name, score = max(patterns, key=lambda x: x[1])

        if score > best_score and score > 0.55:
            best_score = score
            # D 지점에서 반전 예상
            is_bullish = xabcd[0][1] == "low"  # X가 저점이면 bullish
            vol = _volume_confirmation(df)
            strength = _calc_strength(score, vol)

            if is_bullish:
                best_result = ChartPatternResult(
                    f"하모닉 {best_name} (상승)", "long", strength,
                    f"{best_name} 패턴 D점 반전 (점수 {score:.2f})"
                )
            else:
                best_result = ChartPatternResult(
                    f"하모닉 {best_name} (하락)", "short", strength,
                    f"{best_name} 패턴 D점 반전 (점수 {score:.2f})"
                )

    return best_result


# ─── 신규 패턴: Three Drives ─────────────────────────────

def detect_three_drives(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """쓰리 드라이브: 3연속 피보나치 확장 드라이브"""
    if len(df) < 40:
        return None

    close = df["close"].values
    swing_highs, swing_lows = _find_swings(close, order=2)
    pivots = _merge_swings(close, swing_highs, swing_lows)

    if len(pivots) < 6:
        return None

    # 마지막 7개 피벗 시도 (3 drives + 2 corrections + start)
    for start in range(max(0, len(pivots) - 9), len(pivots) - 5):
        segment = pivots[start:start + 7]
        if len(segment) < 6:
            segment = pivots[start:start + 6]
        if len(segment) < 6:
            continue

        # 상승 쓰리 드라이브: low-high-low-high-low-high (3 highs ascending)
        if segment[0][1] == "low" and len(segment) >= 6:
            drives_up = True
            for i in range(0, min(6, len(segment)), 2):
                if segment[i][1] != "low":
                    drives_up = False
                    break
            for i in range(1, min(6, len(segment)), 2):
                if segment[i][1] != "high":
                    drives_up = False
                    break

            if drives_up and len(segment) >= 6:
                d1 = segment[1][2] - segment[0][2]  # Drive 1
                c1 = segment[1][2] - segment[2][2]  # Correction 1
                d2 = segment[3][2] - segment[2][2]  # Drive 2
                c2 = segment[3][2] - segment[4][2]  # Correction 2
                d3 = segment[5][2] - segment[4][2]  # Drive 3

                if d1 <= 0 or c1 <= 0 or d2 <= 0:
                    continue

                # 보정: 61.8%~78.6% 되돌림
                ret1 = c1 / d1
                ret2 = c2 / d2 if d2 > 0 else 0

                score1 = max(_fib_score(ret1, 0.618), _fib_score(ret1, 0.786))
                score2 = max(_fib_score(ret2, 0.618), _fib_score(ret2, 0.786))

                # 드라이브 확장: ~127.2%
                ext1 = d2 / c1 if c1 > 0 else 0
                ext2 = d3 / c2 if c2 > 0 else 0
                ext_score1 = _fib_score(ext1, 1.272)
                ext_score2 = _fib_score(ext2, 1.272)

                total = (score1 + score2 + ext_score1 + ext_score2) / 4

                if total > 0.45:
                    vol = _volume_confirmation(df)
                    strength = _calc_strength(total, vol)
                    return ChartPatternResult(
                        "쓰리 드라이브 (하락 반전)", "short", strength,
                        f"3연속 상승 드라이브 완성 (점수 {total:.2f})"
                    )

        # 하락 쓰리 드라이브: high-low-high-low-high-low (3 lows descending)
        if segment[0][1] == "high" and len(segment) >= 6:
            drives_down = True
            for i in range(0, min(6, len(segment)), 2):
                if segment[i][1] != "high":
                    drives_down = False
                    break
            for i in range(1, min(6, len(segment)), 2):
                if segment[i][1] != "low":
                    drives_down = False
                    break

            if drives_down and len(segment) >= 6:
                d1 = segment[0][2] - segment[1][2]
                c1 = segment[2][2] - segment[1][2]
                d2 = segment[2][2] - segment[3][2]
                c2 = segment[4][2] - segment[3][2]
                d3 = segment[4][2] - segment[5][2]

                if d1 <= 0 or c1 <= 0 or d2 <= 0:
                    continue

                ret1 = c1 / d1
                ret2 = c2 / d2 if d2 > 0 else 0
                score1 = max(_fib_score(ret1, 0.618), _fib_score(ret1, 0.786))
                score2 = max(_fib_score(ret2, 0.618), _fib_score(ret2, 0.786))

                ext1 = d2 / c1 if c1 > 0 else 0
                ext2 = d3 / c2 if c2 > 0 else 0
                ext_score1 = _fib_score(ext1, 1.272)
                ext_score2 = _fib_score(ext2, 1.272)

                total = (score1 + score2 + ext_score1 + ext_score2) / 4

                if total > 0.45:
                    vol = _volume_confirmation(df)
                    strength = _calc_strength(total, vol)
                    return ChartPatternResult(
                        "쓰리 드라이브 (상승 반전)", "long", strength,
                        f"3연속 하락 드라이브 완성 (점수 {total:.2f})"
                    )

    return None


# ─── 패턴 신선도 점수 ────────────────────────────────────

def _recency_boost(strength: float, lookback_used: int, total_candles: int) -> float:
    """최근 패턴일수록 강도 부스트"""
    if total_candles <= 0:
        return strength
    recency = lookback_used / total_candles
    if recency <= 0.1:
        return min(0.95, strength * 1.15)
    elif recency <= 0.3:
        return strength
    else:
        return strength * 0.85


# ─── 중복 제거 (확장) ────────────────────────────────────

def _deduplicate_patterns(patterns: List[ChartPatternResult]) -> List[ChartPatternResult]:
    """중복/충돌 패턴 제거 (18개 패턴 대응)"""
    if len(patterns) <= 1:
        return patterns

    long_patterns = sorted([p for p in patterns if p.signal == "long"], key=lambda p: p.strength, reverse=True)
    short_patterns = sorted([p for p in patterns if p.signal == "short"], key=lambda p: p.strength, reverse=True)
    neutral_patterns = [p for p in patterns if p.signal == "neutral"]

    # 유사 패턴 충돌 해소: 더 구체적인 것 유지
    SIMILAR_GROUPS = [
        {"삼각형", "페넌트", "웨지"},  # 수렴 패턴끼리
        {"플래그", "페넌트"},  # 연속 패턴끼리
    ]

    def _filter_similar(pats: list) -> list:
        kept = []
        used_groups: set = set()
        for p in pats:
            dominated = False
            for gi, group in enumerate(SIMILAR_GROUPS):
                # 이미 이 그룹에서 더 강한 것이 있으면 스킵
                if gi in used_groups:
                    for k in kept:
                        if any(g in k.name for g in group) and any(g in p.name for g in group):
                            dominated = True
                            break
            if not dominated:
                kept.append(p)
                for gi, group in enumerate(SIMILAR_GROUPS):
                    if any(g in p.name for g in group):
                        used_groups.add(gi)
        return kept

    long_filtered = _filter_similar(long_patterns)[:3]
    short_filtered = _filter_similar(short_patterns)[:3]

    result = long_filtered + short_filtered + neutral_patterns[:1]

    # 충돌: 롱과 숏 동시 + 강도 차이 작으면 모두 제거
    if long_filtered and short_filtered:
        max_long = long_filtered[0].strength
        max_short = short_filtered[0].strength
        if abs(max_long - max_short) < 0.15:
            return neutral_patterns[:1]

    return result


# ─── 메인 함수 ─────────────────────────────────────────

def analyze_chart_patterns(df: pd.DataFrame) -> List[ChartPatternResult]:
    """모든 차트 패턴 분석을 수행하고 감지된 패턴 목록 반환"""
    if len(df) < 25:
        return []

    detectors = [
        # 기존 10개
        detect_double_top,
        detect_double_bottom,
        detect_head_and_shoulders,
        detect_triangle,
        detect_wedge,
        detect_flag,
        detect_channel,
        detect_cup_and_handle,
        detect_triple_top_bottom,
        detect_elliott_wave,
        # 신규 8개
        detect_rectangle,
        detect_pennant,
        detect_gaps,
        detect_broadening_formation,
        detect_diamond,
        detect_rounding_bottom,
        detect_harmonic_pattern,
        detect_three_drives,
    ]

    patterns = []
    for detector in detectors:
        try:
            result = detector(df)
            if result is not None:
                patterns.append(result)
        except Exception as e:
            logger.error("차트 패턴 감지 오류 (%s): %s", detector.__name__, e, exc_info=True)

    return _deduplicate_patterns(patterns)

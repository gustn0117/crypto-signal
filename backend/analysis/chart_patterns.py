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
    2x 이상 → 1.0, 1.2x → 0.5, 평균 이하 → 0.0~0.5
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

    if ratio >= 2.0:
        return 1.0
    elif ratio >= 1.2:
        return 0.5 + (ratio - 1.2) / 0.8 * 0.5
    else:
        return max(0.0, ratio / 1.2 * 0.5)


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

def _deduplicate_patterns(patterns: List[ChartPatternResult]) -> List[ChartPatternResult]:
    """중복/충돌 패턴 제거"""
    if len(patterns) <= 1:
        return patterns

    long_patterns = sorted([p for p in patterns if p.signal == "long"], key=lambda p: p.strength, reverse=True)
    short_patterns = sorted([p for p in patterns if p.signal == "short"], key=lambda p: p.strength, reverse=True)
    neutral_patterns = [p for p in patterns if p.signal == "neutral"]

    # 같은 방향: 강한 2개만 유지
    result = long_patterns[:2] + short_patterns[:2] + neutral_patterns[:1]

    # 충돌: 롱과 숏 동시 + 강도 차이 작으면 약한 쪽 제거
    if long_patterns and short_patterns:
        max_long = long_patterns[0].strength
        max_short = short_patterns[0].strength
        if abs(max_long - max_short) < 0.15:
            return neutral_patterns[:1]

    return result


# ─── 메인 함수 ─────────────────────────────────────────

def analyze_chart_patterns(df: pd.DataFrame) -> List[ChartPatternResult]:
    """모든 차트 패턴 분석을 수행하고 감지된 패턴 목록 반환"""
    if len(df) < 25:
        return []

    detectors = [
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

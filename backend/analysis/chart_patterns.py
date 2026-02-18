"""
차트 패턴 인식 모듈
구조적/기하학적 멀티캔들 패턴: 쌍봉, 쌍바닥, 헤드앤숄더,
삼각수렴, 웨지, 플래그, 채널, 엘리엇 파동 등
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

    # 최근 2개 스윙 하이
    h1_idx, h2_idx = swing_highs[-2], swing_highs[-1]
    h1, h2 = highs_arr[h1_idx], highs_arr[h2_idx]

    # 두 고점이 비슷한 레벨인지 (2% 이내)
    if _pct_diff(h1, h2) > 2.0:
        return None

    # 사이 저점 (넥라인)
    between = data["low"].values[h1_idx:h2_idx + 1]
    if len(between) < 2:
        return None
    neckline = float(np.min(between))

    # 현재 가격이 넥라인 근처 또는 아래
    peak_avg = (h1 + h2) / 2
    if close > peak_avg:
        return None  # 아직 패턴 미완성

    if close <= neckline * 1.01:
        return ChartPatternResult(
            name="쌍봉 (Double Top)",
            signal="short",
            strength=0.85,
            description=f"넥라인(${neckline:.2f}) 하향 돌파 - 하락 목표: ${neckline - (peak_avg - neckline):.2f}"
        )
    elif close < peak_avg * 0.98:
        return ChartPatternResult(
            name="쌍봉 형성 중 (Double Top)",
            signal="short",
            strength=0.6,
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
        # high 배열 기준 스윙로우도 시도
        _, swing_lows = _find_swings(data["low"].values, order=2)
        if len(swing_lows) < 2:
            return None

    l1_idx, l2_idx = swing_lows[-2], swing_lows[-1]
    l1, l2 = lows_arr[l1_idx], lows_arr[l2_idx]

    if _pct_diff(l1, l2) > 2.0:
        return None

    between = data["high"].values[l1_idx:l2_idx + 1]
    if len(between) < 2:
        return None
    neckline = float(np.max(between))

    trough_avg = (l1 + l2) / 2
    if close < trough_avg:
        return None

    if close >= neckline * 0.99:
        return ChartPatternResult(
            name="쌍바닥 (Double Bottom)",
            signal="long",
            strength=0.85,
            description=f"넥라인(${neckline:.2f}) 상향 돌파 - 상승 목표: ${neckline + (neckline - trough_avg):.2f}"
        )
    elif close > trough_avg * 1.02:
        return ChartPatternResult(
            name="쌍바닥 형성 중 (Double Bottom)",
            signal="long",
            strength=0.6,
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

        # 헤드가 양 어깨보다 높고, 양 어깨가 비슷한 레벨
        if head > left_shoulder and head > right_shoulder and _pct_diff(left_shoulder, right_shoulder) < 3.0:
            # 넥라인: 두 어깨 사이 저점 연결
            trough1 = float(np.min(lows_arr[s1_idx:h_idx + 1]))
            trough2 = float(np.min(lows_arr[h_idx:s2_idx + 1]))
            neckline = (trough1 + trough2) / 2

            if close <= neckline * 1.01:
                target = neckline - (head - neckline)
                return ChartPatternResult(
                    name="헤드앤숄더 (Head & Shoulders)",
                    signal="short",
                    strength=0.9,
                    description=f"넥라인(${neckline:.2f}) 하향 돌파 - 하락 목표: ${target:.2f}"
                )
            elif close < right_shoulder:
                return ChartPatternResult(
                    name="헤드앤숄더 형성 중",
                    signal="short",
                    strength=0.65,
                    description=f"우측 어깨 완성, 넥라인 ${neckline:.2f} 하향 돌파 주시"
                )

    # 역헤드앤숄더 (상승 시그널)
    _, swing_lows = _find_swings(lows_arr, order=3)
    if len(swing_lows) >= 3:
        s1_idx, h_idx, s2_idx = swing_lows[-3], swing_lows[-2], swing_lows[-1]
        left_shoulder = lows_arr[s1_idx]
        head = lows_arr[h_idx]
        right_shoulder = lows_arr[s2_idx]

        if head < left_shoulder and head < right_shoulder and _pct_diff(left_shoulder, right_shoulder) < 3.0:
            peak1 = float(np.max(highs_arr[s1_idx:h_idx + 1]))
            peak2 = float(np.max(highs_arr[h_idx:s2_idx + 1]))
            neckline = (peak1 + peak2) / 2

            if close >= neckline * 0.99:
                target = neckline + (neckline - head)
                return ChartPatternResult(
                    name="역헤드앤숄더 (Inverse H&S)",
                    signal="long",
                    strength=0.9,
                    description=f"넥라인(${neckline:.2f}) 상향 돌파 - 상승 목표: ${target:.2f}"
                )
            elif close > right_shoulder:
                return ChartPatternResult(
                    name="역헤드앤숄더 형성 중",
                    signal="long",
                    strength=0.65,
                    description=f"우측 어깨 완성, 넥라인 ${neckline:.2f} 상향 돌파 주시"
                )
    return None


# ─── 삼각 수렴 (Triangle) ──────────────────────────────

def detect_triangle(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    삼각 수렴 패턴:
    - 대칭 삼각형: 고점 하락 + 저점 상승 (방향 불확실)
    - 상승 삼각형: 고점 수평 + 저점 상승 (상승)
    - 하락 삼각형: 저점 수평 + 고점 하락 (하락)
    """
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

    # 최근 스윙 하이/로우의 추세
    recent_highs = np.array([highs_arr[i] for i in swing_highs[-4:]])
    recent_lows = np.array([lows_arr[i] for i in swing_lows[-4:]])

    high_slope, _ = _linear_regression(recent_highs)
    low_slope, _ = _linear_regression(recent_lows)

    # 기울기를 가격 대비 정규화
    avg_price = (recent_highs.mean() + recent_lows.mean()) / 2
    if avg_price == 0:
        return None
    high_slope_pct = high_slope / avg_price * 100
    low_slope_pct = low_slope / avg_price * 100

    # 수렴 확인: 고점과 저점이 좁혀지는지
    range_first = recent_highs[0] - recent_lows[0] if len(recent_lows) > 0 else 0
    range_last = recent_highs[-1] - recent_lows[-1] if len(recent_lows) > 0 else 0

    if range_first <= 0 or range_last <= 0:
        return None

    if range_last >= range_first * 0.9:
        return None  # 수렴하지 않음

    # 상승 삼각형: 고점 수평(-0.3%~0.3%), 저점 상승
    if abs(high_slope_pct) < 0.3 and low_slope_pct > 0.1:
        return ChartPatternResult(
            name="상승 삼각형 (Ascending Triangle)",
            signal="long",
            strength=0.75,
            description=f"저항선 ${recent_highs[-1]:.2f} 수평 + 지지선 상승 중 - 상방 돌파 기대"
        )

    # 하락 삼각형: 저점 수평, 고점 하락
    if abs(low_slope_pct) < 0.3 and high_slope_pct < -0.1:
        return ChartPatternResult(
            name="하락 삼각형 (Descending Triangle)",
            signal="short",
            strength=0.75,
            description=f"지지선 ${recent_lows[-1]:.2f} 수평 + 저항선 하락 중 - 하방 돌파 기대"
        )

    # 대칭 삼각형: 고점 하락 + 저점 상승
    if high_slope_pct < -0.1 and low_slope_pct > 0.1:
        return ChartPatternResult(
            name="대칭 삼각형 (Symmetrical Triangle)",
            signal="neutral",
            strength=0.6,
            description="수렴 진행 중 - 돌파 방향에 따라 큰 움직임 예상"
        )

    return None


# ─── 웨지 (Wedge) ──────────────────────────────────────

def detect_wedge(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    웨지 패턴:
    - 상승 웨지: 고점과 저점 모두 상승하지만 수렴 (하락 반전)
    - 하락 웨지: 고점과 저점 모두 하락하지만 수렴 (상승 반전)
    """
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

    high_slope, _ = _linear_regression(recent_highs)
    low_slope, _ = _linear_regression(recent_lows)

    avg_price = (recent_highs.mean() + recent_lows.mean()) / 2
    if avg_price == 0:
        return None
    high_slope_pct = high_slope / avg_price * 100
    low_slope_pct = low_slope / avg_price * 100

    # 수렴 확인
    range_first = recent_highs[0] - recent_lows[0]
    range_last = recent_highs[-1] - recent_lows[-1]
    if range_first <= 0 or range_last >= range_first * 0.95:
        return None

    # 상승 웨지: 둘 다 상승 + 수렴
    if high_slope_pct > 0.1 and low_slope_pct > 0.1:
        return ChartPatternResult(
            name="상승 웨지 (Rising Wedge)",
            signal="short",
            strength=0.75,
            description="고점과 저점 모두 상승하나 수렴 중 - 하락 반전 가능성"
        )

    # 하락 웨지: 둘 다 하락 + 수렴
    if high_slope_pct < -0.1 and low_slope_pct < -0.1:
        return ChartPatternResult(
            name="하락 웨지 (Falling Wedge)",
            signal="long",
            strength=0.75,
            description="고점과 저점 모두 하락하나 수렴 중 - 상승 반전 가능성"
        )

    return None


# ─── 플래그 / 페넌트 ───────────────────────────────────

def detect_flag(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    플래그 패턴: 강한 추세 후 반대 방향 좁은 채널 형성
    - 불 플래그: 급등 후 하향 채널 → 상방 돌파
    - 베어 플래그: 급락 후 상향 채널 → 하방 돌파
    """
    if len(df) < 25:
        return None
    data = df.tail(40) if len(df) >= 40 else df
    close = data["close"].values

    # 최근 구간을 폴(pole)과 플래그로 분리
    pole_len = min(10, len(close) // 3)
    flag_len = min(15, len(close) - pole_len)

    if flag_len < 5:
        return None

    pole = close[:pole_len]
    flag_data = close[-flag_len:]

    # 폴 움직임
    pole_change = (pole[-1] - pole[0]) / pole[0] * 100 if pole[0] > 0 else 0

    # 플래그 움직임
    flag_slope, _ = _linear_regression(flag_data)
    flag_range = (flag_data.max() - flag_data.min()) / flag_data.mean() * 100 if flag_data.mean() > 0 else 0

    # 불 플래그: 강한 상승(>3%) 후 좁은 하향 조정(<3%)
    if pole_change > 3.0 and flag_slope < 0 and flag_range < 3.0:
        return ChartPatternResult(
            name="불 플래그 (Bull Flag)",
            signal="long",
            strength=0.75,
            description=f"급등({pole_change:.1f}%) 후 조정 중 - 상방 돌파 시 추세 지속"
        )

    # 베어 플래그: 강한 하락 후 좁은 상향 반등
    if pole_change < -3.0 and flag_slope > 0 and flag_range < 3.0:
        return ChartPatternResult(
            name="베어 플래그 (Bear Flag)",
            signal="short",
            strength=0.75,
            description=f"급락({pole_change:.1f}%) 후 반등 중 - 하방 돌파 시 추세 지속"
        )

    return None


# ─── 채널 패턴 ─────────────────────────────────────────

def detect_channel(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    채널 패턴: 평행한 상/하 추세선
    - 상승 채널: 채널 상단에서 매도 시그널
    - 하락 채널: 채널 하단에서 매수 시그널
    """
    if len(df) < 30:
        return None
    data = df.tail(50) if len(df) >= 50 else df
    highs_arr = data["high"].values
    lows_arr = data["low"].values
    close = data["close"].values[-1]

    high_slope, high_r2 = _linear_regression(highs_arr)
    low_slope, low_r2 = _linear_regression(lows_arr)

    # 채널 조건: R² 높고 기울기 비슷
    if high_r2 < 0.6 or low_r2 < 0.6:
        return None

    avg_price = (highs_arr.mean() + lows_arr.mean()) / 2
    if avg_price == 0:
        return None

    high_slope_pct = high_slope / avg_price * 100
    low_slope_pct = low_slope / avg_price * 100

    # 기울기가 비슷한지 (평행)
    if abs(high_slope_pct - low_slope_pct) > 0.5:
        return None

    avg_slope = (high_slope_pct + low_slope_pct) / 2

    # 현재 가격의 채널 내 위치
    channel_top = highs_arr[-1]
    channel_bottom = lows_arr[-1]
    channel_width = channel_top - channel_bottom
    if channel_width <= 0:
        return None
    position = (close - channel_bottom) / channel_width

    if avg_slope > 0.1:  # 상승 채널
        if position > 0.85:
            return ChartPatternResult(
                name="상승 채널 상단 (Rising Channel)",
                signal="short",
                strength=0.65,
                description="상승 채널 상단 접근 - 단기 조정 가능성"
            )
        elif position < 0.15:
            return ChartPatternResult(
                name="상승 채널 하단 (Rising Channel)",
                signal="long",
                strength=0.7,
                description="상승 채널 하단 지지 - 반등 기대"
            )
    elif avg_slope < -0.1:  # 하락 채널
        if position < 0.15:
            return ChartPatternResult(
                name="하락 채널 하단 (Falling Channel)",
                signal="long",
                strength=0.65,
                description="하락 채널 하단 접근 - 단기 반등 가능성"
            )
        elif position > 0.85:
            return ChartPatternResult(
                name="하락 채널 상단 (Falling Channel)",
                signal="short",
                strength=0.7,
                description="하락 채널 상단 저항 - 재하락 기대"
            )

    return None


# ─── 컵앤핸들 ──────────────────────────────────────────

def detect_cup_and_handle(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    컵앤핸들 (Cup & Handle): U자형 바닥 + 작은 하락 조정(핸들)
    강한 상승 시그널
    """
    if len(df) < 40:
        return None
    data = df.tail(120) if len(df) >= 120 else df
    close = data["close"].values
    n = len(close)

    # 컵: 전반 1/3 ~ 2/3 구간에서 저점, 양쪽이 높은 U자형
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

    # U자형 확인: 양쪽 림이 중앙 저점보다 높고, 비슷한 레벨
    if cup_min >= left_rim * 0.97 or cup_min >= right_rim * 0.97:
        return None
    if _pct_diff(left_rim, right_rim) > 5.0:
        return None

    # 핸들: 작은 하락 조정 (컵 깊이의 1/3 이하)
    cup_depth = ((left_rim + right_rim) / 2) - cup_min
    handle_low = handle.min()
    handle_dip = right_rim - handle_low

    if cup_depth <= 0 or handle_dip > cup_depth * 0.5:
        return None
    if handle_dip < cup_depth * 0.05:
        return None  # 핸들이 없음

    neckline = (left_rim + right_rim) / 2
    if close[-1] >= neckline * 0.98:
        return ChartPatternResult(
            name="컵앤핸들 (Cup & Handle)",
            signal="long",
            strength=0.85,
            description=f"컵앤핸들 완성 - 넥라인 ${neckline:.2f} 돌파 시 목표: ${neckline + cup_depth:.2f}"
        )

    return None


# ─── 엘리엇 파동 ───────────────────────────────────────

def detect_elliott_wave(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    엘리엇 파동 (Elliott Wave) 기본 패턴 감지:
    - 충격파 5파 (1-2-3-4-5): 추세 방향
    - 조정파 3파 (A-B-C): 추세 반대 방향

    규칙:
    1. 파동2는 파동1의 시작점 아래로 내려가지 않음
    2. 파동3은 파동1,3,5 중 가장 짧지 않음
    3. 파동4는 파동1의 영역에 겹치지 않음
    """
    if len(df) < 50:
        return None
    data = df.tail(150) if len(df) >= 150 else df
    close = data["close"].values
    highs = data["high"].values
    lows = data["low"].values

    swing_highs, swing_lows = _find_swings(close, order=3)

    # 상승 5파 시도
    result = _detect_impulse_up(close, highs, lows, swing_highs, swing_lows)
    if result:
        return result

    # 하락 5파 시도
    result = _detect_impulse_down(close, highs, lows, swing_highs, swing_lows)
    if result:
        return result

    # ABC 조정 패턴
    result = _detect_abc_correction(close, highs, lows, swing_highs, swing_lows)
    if result:
        return result

    return None


def _detect_impulse_up(
    close: np.ndarray, highs: np.ndarray, lows: np.ndarray,
    swing_highs: List[int], swing_lows: List[int],
) -> Optional[ChartPatternResult]:
    """상승 5파 충격파 감지"""
    # 교대하는 스윙: low(0), high(1), low(2), high(3), low(4), high(5)
    # 즉 스윙로우와 스윙하이를 번갈아 최소 5개 필요
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    # 최근 스윙들로 5파 구성 시도
    # 1파: low→high, 2파: high→low, 3파: low→high, 4파: high→low, 5파: low→high
    try:
        # 가장 최근 스윙들에서 역추적
        pivots = _merge_swings(close, swing_highs, swing_lows)
        if len(pivots) < 6:
            return None

        # 마지막 6개 피벗에서 5파 구조 검증
        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            # 상승파: 첫 피벗이 저점이어야 함
            if p[0][1] != "low":
                continue

            w0 = p[0][2]  # 파동1 시작
            w1 = p[1][2]  # 파동1 끝 / 파동2 시작
            w2 = p[2][2]  # 파동2 끝 / 파동3 시작
            w3 = p[3][2]  # 파동3 끝 / 파동4 시작
            w4 = p[4][2]  # 파동4 끝 / 파동5 시작
            w5 = p[5][2]  # 파동5 끝

            # 기본 상승 구조 확인
            if not (w1 > w0 and w2 < w1 and w3 > w1 and w4 < w3 and w5 > w3):
                continue

            # 엘리엇 규칙 검증
            # 규칙1: 파동2는 파동1 시작 아래로 안 내려감
            if w2 <= w0:
                continue

            # 규칙2: 파동3은 가장 짧은 충격파가 아님
            wave1 = w1 - w0
            wave3 = w3 - w2
            wave5 = w5 - w4
            if wave3 < wave1 and wave3 < wave5:
                continue

            # 규칙3: 파동4는 파동1의 고점 아래로 안 내려감
            if w4 <= w1:
                continue

            # 현재 위치 판단
            current = close[-1]
            if current >= w5 * 0.98:
                # 5파 완성 → 조정 예상
                return ChartPatternResult(
                    name="엘리엇 5파 완성 (상승)",
                    signal="short",
                    strength=0.7,
                    description="상승 5파 완성 - ABC 조정파 시작 가능성"
                )
            elif current >= w3 and current < w5:
                # 5파 진행 중
                return ChartPatternResult(
                    name="엘리엇 5파 진행 중 (상승)",
                    signal="long",
                    strength=0.6,
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

            w0 = p[0][2]
            w1 = p[1][2]
            w2 = p[2][2]
            w3 = p[3][2]
            w4 = p[4][2]
            w5 = p[5][2]

            # 하락 구조
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

            current = close[-1]
            if current <= w5 * 1.02:
                return ChartPatternResult(
                    name="엘리엇 5파 완성 (하락)",
                    signal="long",
                    strength=0.7,
                    description="하락 5파 완성 - ABC 반등 시작 가능성"
                )
            elif current <= w3 and current > w5:
                return ChartPatternResult(
                    name="엘리엇 5파 진행 중 (하락)",
                    signal="short",
                    strength=0.6,
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

        # 하락 ABC (이전 상승 후)
        for i in range(len(pivots) - 3):
            p = pivots[i:i + 4]
            if p[0][1] != "high":
                continue

            a_start = p[0][2]
            a_end = p[1][2]
            b_end = p[2][2]
            c_end = p[3][2]

            # ABC 하락: A하락, B반등, C하락
            if a_end < a_start and b_end > a_end and c_end < a_end:
                # C파가 A파의 0.618~1.618 비율
                a_wave = a_start - a_end
                c_wave = b_end - c_end
                ratio = c_wave / a_wave if a_wave > 0 else 0

                if 0.5 < ratio < 2.0:
                    current = close[-1]
                    if current <= c_end * 1.02:
                        return ChartPatternResult(
                            name="ABC 조정 완료 (하락)",
                            signal="long",
                            strength=0.7,
                            description=f"ABC 조정파 완료 (C/A 비율: {ratio:.2f}) - 새로운 상승 충격파 기대"
                        )

        # 상승 ABC (이전 하락 후)
        for i in range(len(pivots) - 3):
            p = pivots[i:i + 4]
            if p[0][1] != "low":
                continue

            a_start = p[0][2]
            a_end = p[1][2]
            b_end = p[2][2]
            c_end = p[3][2]

            if a_end > a_start and b_end < a_end and c_end > a_end:
                a_wave = a_end - a_start
                c_wave = c_end - b_end
                ratio = c_wave / a_wave if a_wave > 0 else 0

                if 0.5 < ratio < 2.0:
                    current = close[-1]
                    if current >= c_end * 0.98:
                        return ChartPatternResult(
                            name="ABC 조정 완료 (상승)",
                            signal="short",
                            strength=0.7,
                            description=f"ABC 반등 완료 (C/A 비율: {ratio:.2f}) - 새로운 하락 충격파 기대"
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

    # 연속 같은 방향 제거 (가장 극단값만 유지)
    if len(pivots) < 2:
        return pivots

    cleaned = [pivots[0]]
    for p in pivots[1:]:
        if p[1] == cleaned[-1][1]:
            # 같은 방향: 더 극단적인 값 유지
            if p[1] == "high" and p[2] > cleaned[-1][2]:
                cleaned[-1] = p
            elif p[1] == "low" and p[2] < cleaned[-1][2]:
                cleaned[-1] = p
        else:
            cleaned.append(p)

    return cleaned


# ─── 트리플 탑/바텀 ────────────────────────────────────

def detect_triple_top_bottom(df: pd.DataFrame) -> Optional[ChartPatternResult]:
    """
    트리플 탑/바텀: 3번의 비슷한 고점/저점
    쌍봉/쌍바닥보다 강한 시그널
    """
    if len(df) < 40:
        return None
    data = df.tail(120) if len(df) >= 120 else df
    highs_arr = data["high"].values
    lows_arr = data["low"].values
    close = data["close"].values[-1]

    swing_highs, swing_lows = _find_swings(highs_arr, order=3)

    # 트리플 탑
    if len(swing_highs) >= 3:
        tops = [highs_arr[i] for i in swing_highs[-3:]]
        avg_top = np.mean(tops)
        if all(_pct_diff(t, avg_top) < 1.5 for t in tops):
            neckline = float(np.min(lows_arr[swing_highs[-3]:swing_highs[-1] + 1]))
            if close <= neckline * 1.01:
                return ChartPatternResult(
                    name="트리플 탑 (Triple Top)",
                    signal="short",
                    strength=0.9,
                    description=f"3중 천정(${avg_top:.2f}) 확인 - 매우 강한 하락 시그널"
                )

    # 트리플 바텀
    _, swing_lows2 = _find_swings(lows_arr, order=3)
    if len(swing_lows2) >= 3:
        bottoms = [lows_arr[i] for i in swing_lows2[-3:]]
        avg_bottom = np.mean(bottoms)
        if all(_pct_diff(b, avg_bottom) < 1.5 for b in bottoms):
            neckline = float(np.max(highs_arr[swing_lows2[-3]:swing_lows2[-1] + 1]))
            if close >= neckline * 0.99:
                return ChartPatternResult(
                    name="트리플 바텀 (Triple Bottom)",
                    signal="long",
                    strength=0.9,
                    description=f"3중 바닥(${avg_bottom:.2f}) 확인 - 매우 강한 상승 시그널"
                )

    return None


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

    return patterns

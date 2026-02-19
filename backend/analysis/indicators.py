"""
기술적 지표 분석 모듈
RSI, MACD, 볼린저밴드, EMA, Stochastic, ADX, VWAP, Ichimoku,
Williams %R, CCI, MFI, CMF 등 12개 지표 계산
"""
import logging
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── 타임프레임별 지표 파라미터 ─────────────────────────────
TF_CATEGORY = {
    "1m": "scalp", "5m": "scalp",
    "15m": "swing", "30m": "swing", "1h": "swing",
    "4h": "position", "1d": "position",
}

INDICATOR_PARAMS = {
    "scalp": {
        "rsi_period": 9, "macd_fast": 8, "macd_slow": 17, "macd_signal": 9,
        "bb_period": 15, "bb_std": 2.0, "ema_short": 5, "ema_long": 13,
        "stoch_k": 9, "stoch_d": 3, "stoch_smooth": 3,
        "adx_period": 10, "williams_period": 10, "cci_period": 14,
        "mfi_period": 10, "cmf_period": 14,
    },
    "swing": {
        "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "bb_period": 20, "bb_std": 2.0, "ema_short": 9, "ema_long": 21,
        "stoch_k": 14, "stoch_d": 3, "stoch_smooth": 3,
        "adx_period": 14, "williams_period": 14, "cci_period": 20,
        "mfi_period": 14, "cmf_period": 20,
    },
    "position": {
        "rsi_period": 21, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "bb_period": 20, "bb_std": 2.0, "ema_short": 12, "ema_long": 26,
        "stoch_k": 14, "stoch_d": 3, "stoch_smooth": 3,
        "adx_period": 14, "williams_period": 14, "cci_period": 20,
        "mfi_period": 14, "cmf_period": 20,
    },
}


def get_params(timeframe: str = "1h") -> dict:
    """타임프레임에 맞는 지표 파라미터 반환."""
    category = TF_CATEGORY.get(timeframe, "swing")
    return INDICATOR_PARAMS[category]


@dataclass
class IndicatorResult:
    """개별 지표 분석 결과"""
    name: str
    signal: str  # "long", "short", "neutral"
    strength: float  # 0.0 ~ 1.0
    value: float
    description: str


def analyze_rsi(df: pd.DataFrame, period: int = 14, timeframe: str = "1h") -> IndicatorResult:
    """RSI (Relative Strength Index) 분석"""
    try:
        p = get_params(timeframe)
        period = p["rsi_period"]
        rsi = ta.rsi(df["close"], length=period)
        if rsi is None or rsi.empty:
            return IndicatorResult("RSI", "neutral", 0.0, 0.0, "데이터 부족")

        current_rsi = rsi.iloc[-1]

        if current_rsi <= 30:
            signal = "long"
            strength = (30 - current_rsi) / 30
            desc = f"RSI {current_rsi:.1f} - 과매도 구간 (롱 기회)"
        elif current_rsi >= 70:
            signal = "short"
            strength = (current_rsi - 70) / 30
            desc = f"RSI {current_rsi:.1f} - 과매수 구간 (숏 기회)"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"RSI {current_rsi:.1f} - 중립 구간"

        return IndicatorResult("RSI", signal, min(strength, 1.0), current_rsi, desc)
    except Exception as e:
        logger.error("RSI 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("RSI", "neutral", 0.0, 0.0, "분석 오류")


def analyze_macd(df: pd.DataFrame, timeframe: str = "1h") -> IndicatorResult:
    """MACD 분석 (크로스오버 + 히스토그램)"""
    try:
        p = get_params(timeframe)
        macd_df = ta.macd(df["close"], fast=p["macd_fast"], slow=p["macd_slow"], signal=p["macd_signal"])
        if macd_df is None or macd_df.empty:
            return IndicatorResult("MACD", "neutral", 0.0, 0.0, "데이터 부족")

        macd_line = macd_df.iloc[:, 0]
        signal_line = macd_df.iloc[:, 1]
        histogram = macd_df.iloc[:, 2]

        if len(macd_line.dropna()) < 2:
            return IndicatorResult("MACD", "neutral", 0.0, 0.0, "데이터 부족")

        curr_macd = macd_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        curr_signal = signal_line.iloc[-1]
        prev_signal = signal_line.iloc[-2]
        curr_hist = histogram.iloc[-1]

        if prev_macd <= prev_signal and curr_macd > curr_signal:
            signal = "long"
            strength = 0.8
            desc = "MACD 골든크로스 발생 (강한 롱 시그널)"
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            signal = "short"
            strength = 0.8
            desc = "MACD 데드크로스 발생 (강한 숏 시그널)"
        elif curr_hist > 0:
            signal = "long"
            strength = min(abs(curr_hist) / abs(curr_macd + 1e-10) * 0.5, 0.5)
            desc = f"MACD 히스토그램 양수 ({curr_hist:.4f})"
        elif curr_hist < 0:
            signal = "short"
            strength = min(abs(curr_hist) / abs(curr_macd + 1e-10) * 0.5, 0.5)
            desc = f"MACD 히스토그램 음수 ({curr_hist:.4f})"
        else:
            signal = "neutral"
            strength = 0.0
            desc = "MACD 중립"

        return IndicatorResult("MACD", signal, strength, curr_macd, desc)
    except Exception as e:
        logger.error("MACD 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("MACD", "neutral", 0.0, 0.0, "분석 오류")


def analyze_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0, timeframe: str = "1h") -> IndicatorResult:
    """볼린저밴드 분석"""
    try:
        p = get_params(timeframe)
        period = p["bb_period"]
        std = p["bb_std"]
        bbands = ta.bbands(df["close"], length=period, std=std)
        if bbands is None or bbands.empty:
            return IndicatorResult("BB", "neutral", 0.0, 0.0, "데이터 부족")

        lower = bbands.iloc[:, 0].iloc[-1]
        upper = bbands.iloc[:, 2].iloc[-1]
        current_price = df["close"].iloc[-1]

        band_width = upper - lower
        if band_width == 0:
            return IndicatorResult("BB", "neutral", 0.0, current_price, "밴드 폭 0")

        position = (current_price - lower) / band_width

        if position <= 0.05:
            signal = "long"
            strength = 0.9
            desc = "가격이 하단밴드 터치 (강한 반등 기대)"
        elif position <= 0.2:
            signal = "long"
            strength = 0.5
            desc = "가격이 하단밴드 근접"
        elif position >= 0.95:
            signal = "short"
            strength = 0.9
            desc = "가격이 상단밴드 터치 (하락 전환 가능)"
        elif position >= 0.8:
            signal = "short"
            strength = 0.5
            desc = "가격이 상단밴드 근접"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"가격이 밴드 중간 위치 ({position:.0%})"

        return IndicatorResult("BB", signal, strength, current_price, desc)
    except Exception as e:
        logger.error("BB 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("BB", "neutral", 0.0, 0.0, "분석 오류")


def analyze_ema_cross(df: pd.DataFrame, short_period: int = 9, long_period: int = 21, timeframe: str = "1h") -> IndicatorResult:
    """EMA 크로스 분석"""
    try:
        p = get_params(timeframe)
        short_period = p["ema_short"]
        long_period = p["ema_long"]
        ema_short = ta.ema(df["close"], length=short_period)
        ema_long = ta.ema(df["close"], length=long_period)

        if ema_short is None or ema_long is None:
            return IndicatorResult("EMA", "neutral", 0.0, 0.0, "데이터 부족")

        if len(ema_short.dropna()) < 2 or len(ema_long.dropna()) < 2:
            return IndicatorResult("EMA", "neutral", 0.0, 0.0, "데이터 부족")

        curr_short = ema_short.iloc[-1]
        prev_short = ema_short.iloc[-2]
        curr_long = ema_long.iloc[-1]
        prev_long = ema_long.iloc[-2]

        if prev_short <= prev_long and curr_short > curr_long:
            signal = "long"
            strength = 0.7
            desc = f"EMA{short_period}/{long_period} 골든크로스"
        elif prev_short >= prev_long and curr_short < curr_long:
            signal = "short"
            strength = 0.7
            desc = f"EMA{short_period}/{long_period} 데드크로스"
        elif curr_short > curr_long:
            signal = "long"
            strength = 0.3
            desc = f"EMA{short_period} > EMA{long_period} (상승 추세)"
        else:
            signal = "short"
            strength = 0.3
            desc = f"EMA{short_period} < EMA{long_period} (하락 추세)"

        return IndicatorResult("EMA", signal, strength, curr_short, desc)
    except Exception as e:
        logger.error("EMA 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("EMA", "neutral", 0.0, 0.0, "분석 오류")


def analyze_stochastic(df: pd.DataFrame, timeframe: str = "1h") -> IndicatorResult:
    """스토캐스틱 분석"""
    try:
        p = get_params(timeframe)
        stoch = ta.stoch(df["high"], df["low"], df["close"], k=p["stoch_k"], d=p["stoch_d"], smooth_k=p["stoch_smooth"])
        if stoch is None or stoch.empty:
            return IndicatorResult("STOCH", "neutral", 0.0, 0.0, "데이터 부족")

        k = stoch.iloc[:, 0].iloc[-1]
        d = stoch.iloc[:, 1].iloc[-1]

        if k <= 20 and d <= 20:
            signal = "long"
            strength = 0.7
            desc = f"스토캐스틱 과매도 (K:{k:.1f}, D:{d:.1f})"
        elif k >= 80 and d >= 80:
            signal = "short"
            strength = 0.7
            desc = f"스토캐스틱 과매수 (K:{k:.1f}, D:{d:.1f})"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"스토캐스틱 중립 (K:{k:.1f}, D:{d:.1f})"

        return IndicatorResult("STOCH", signal, strength, k, desc)
    except Exception as e:
        logger.error("STOCH 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("STOCH", "neutral", 0.0, 0.0, "분석 오류")


# ─── 새 지표 7개 ──────────────────────────────────────────


def analyze_adx(df: pd.DataFrame, period: int = 14, timeframe: str = "1h") -> IndicatorResult:
    """ADX (Average Directional Index) — 추세 강도"""
    try:
        p = get_params(timeframe)
        period = p["adx_period"]
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=period)
        if adx_df is None or adx_df.empty:
            return IndicatorResult("ADX", "neutral", 0.0, 0.0, "데이터 부족")

        adx_col = [c for c in adx_df.columns if "ADX" in c and "DM" not in c]
        dmp_col = [c for c in adx_df.columns if "DMP" in c]
        dmn_col = [c for c in adx_df.columns if "DMN" in c]

        if not adx_col or not dmp_col or not dmn_col:
            return IndicatorResult("ADX", "neutral", 0.0, 0.0, "컬럼 없음")

        adx_val = float(adx_df[adx_col[0]].dropna().iloc[-1])
        dmp = float(adx_df[dmp_col[0]].dropna().iloc[-1])
        dmn = float(adx_df[dmn_col[0]].dropna().iloc[-1])

        if adx_val < 20:
            return IndicatorResult("ADX", "neutral", 0.0, adx_val,
                                   f"ADX {adx_val:.1f} - 추세 약함 (횡보)")

        strength = min((adx_val - 20) / 40, 1.0)
        if dmp > dmn:
            return IndicatorResult("ADX", "long", strength, adx_val,
                                   f"ADX {adx_val:.1f} - 강한 상승 추세 (DI+ {dmp:.1f} > DI- {dmn:.1f})")
        else:
            return IndicatorResult("ADX", "short", strength, adx_val,
                                   f"ADX {adx_val:.1f} - 강한 하락 추세 (DI- {dmn:.1f} > DI+ {dmp:.1f})")
    except Exception as e:
        logger.error("ADX 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("ADX", "neutral", 0.0, 0.0, "분석 오류")


def analyze_vwap(df: pd.DataFrame) -> IndicatorResult:
    """VWAP (Volume Weighted Average Price) — 기관 매매 기준선"""
    try:
        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        if vwap is None or vwap.empty:
            return IndicatorResult("VWAP", "neutral", 0.0, 0.0, "데이터 부족")

        current_price = df["close"].iloc[-1]
        current_vwap = float(vwap.dropna().iloc[-1])
        deviation = (current_price - current_vwap) / current_vwap * 100

        if deviation > 2.0:
            signal = "short"
            strength = min(deviation / 5.0, 0.8)
            desc = f"VWAP 위 +{deviation:.1f}% — 과매수 (VWAP 회귀 가능)"
        elif deviation < -2.0:
            signal = "long"
            strength = min(abs(deviation) / 5.0, 0.8)
            desc = f"VWAP 아래 {deviation:.1f}% — 과매도 (VWAP 회귀 가능)"
        elif deviation > 0.5:
            signal = "long"
            strength = 0.3
            desc = f"VWAP 위 +{deviation:.1f}% — 약한 상승 모멘텀"
        elif deviation < -0.5:
            signal = "short"
            strength = 0.3
            desc = f"VWAP 아래 {deviation:.1f}% — 약한 하락 모멘텀"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"VWAP 근접 ({deviation:+.1f}%)"

        return IndicatorResult("VWAP", signal, strength, current_vwap, desc)
    except Exception as e:
        logger.error("VWAP 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("VWAP", "neutral", 0.0, 0.0, "분석 오류")


def analyze_ichimoku(df: pd.DataFrame) -> IndicatorResult:
    """Ichimoku Cloud — 구름대 위치 기반 추세 판단"""
    try:
        ichi = ta.ichimoku(df["high"], df["low"], df["close"])
        if ichi is None or len(ichi) < 2:
            return IndicatorResult("Ichimoku", "neutral", 0.0, 0.0, "데이터 부족")

        ichi_df = ichi[0]
        if ichi_df is None or ichi_df.empty:
            return IndicatorResult("Ichimoku", "neutral", 0.0, 0.0, "데이터 부족")

        current_price = df["close"].iloc[-1]

        span_a_col = [c for c in ichi_df.columns if "ISA" in c]
        span_b_col = [c for c in ichi_df.columns if "ISB" in c]

        if not span_a_col or not span_b_col:
            return IndicatorResult("Ichimoku", "neutral", 0.0, 0.0, "컬럼 없음")

        span_a = float(ichi_df[span_a_col[0]].dropna().iloc[-1])
        span_b = float(ichi_df[span_b_col[0]].dropna().iloc[-1])
        cloud_top = max(span_a, span_b)
        cloud_bottom = min(span_a, span_b)

        if current_price > cloud_top:
            dist = (current_price - cloud_top) / cloud_top * 100
            strength = min(0.4 + dist * 0.1, 0.8)
            return IndicatorResult("Ichimoku", "long", strength, current_price,
                                   f"구름대 위 — 상승 추세 (+{dist:.1f}%)")
        elif current_price < cloud_bottom:
            dist = (cloud_bottom - current_price) / cloud_bottom * 100
            strength = min(0.4 + dist * 0.1, 0.8)
            return IndicatorResult("Ichimoku", "short", strength, current_price,
                                   f"구름대 아래 — 하락 추세 (-{dist:.1f}%)")
        else:
            return IndicatorResult("Ichimoku", "neutral", 0.2, current_price,
                                   "구름대 내부 — 방향 불확실")
    except Exception as e:
        logger.error("Ichimoku 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("Ichimoku", "neutral", 0.0, 0.0, "분석 오류")


def analyze_williams_r(df: pd.DataFrame, period: int = 14, timeframe: str = "1h") -> IndicatorResult:
    """Williams %R — 과매수/과매도 오실레이터"""
    try:
        p = get_params(timeframe)
        period = p["williams_period"]
        willr = ta.willr(df["high"], df["low"], df["close"], length=period)
        if willr is None or willr.empty:
            return IndicatorResult("W%R", "neutral", 0.0, 0.0, "데이터 부족")

        val = float(willr.dropna().iloc[-1])

        if val <= -80:
            strength = min((-80 - val) / 20 * 0.5 + 0.5, 1.0)
            return IndicatorResult("W%R", "long", strength, val,
                                   f"W%R {val:.1f} - 과매도 구간 (반등 기대)")
        elif val >= -20:
            strength = min((val + 20) / 20 * 0.5 + 0.5, 1.0)
            return IndicatorResult("W%R", "short", strength, val,
                                   f"W%R {val:.1f} - 과매수 구간 (하락 가능)")
        else:
            return IndicatorResult("W%R", "neutral", 0.0, val,
                                   f"W%R {val:.1f} - 중립 구간")
    except Exception as e:
        logger.error("W%%R 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("W%R", "neutral", 0.0, 0.0, "분석 오류")


def analyze_cci(df: pd.DataFrame, period: int = 20, timeframe: str = "1h") -> IndicatorResult:
    """CCI (Commodity Channel Index) — 가격 이탈 감지"""
    try:
        p = get_params(timeframe)
        period = p["cci_period"]
        cci = ta.cci(df["high"], df["low"], df["close"], length=period)
        if cci is None or cci.empty:
            return IndicatorResult("CCI", "neutral", 0.0, 0.0, "데이터 부족")

        val = float(cci.dropna().iloc[-1])

        if val <= -200:
            return IndicatorResult("CCI", "long", 0.9, val,
                                   f"CCI {val:.0f} - 극단적 과매도 (강한 반등 기대)")
        elif val <= -100:
            return IndicatorResult("CCI", "long", 0.6, val,
                                   f"CCI {val:.0f} - 과매도 구간")
        elif val >= 200:
            return IndicatorResult("CCI", "short", 0.9, val,
                                   f"CCI {val:.0f} - 극단적 과매수 (강한 하락 가능)")
        elif val >= 100:
            return IndicatorResult("CCI", "short", 0.6, val,
                                   f"CCI {val:.0f} - 과매수 구간")
        else:
            return IndicatorResult("CCI", "neutral", 0.0, val,
                                   f"CCI {val:.0f} - 중립 구간")
    except Exception as e:
        logger.error("CCI 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("CCI", "neutral", 0.0, 0.0, "분석 오류")


def analyze_mfi(df: pd.DataFrame, period: int = 14, timeframe: str = "1h") -> IndicatorResult:
    """MFI (Money Flow Index) — 거래량 가중 RSI"""
    try:
        p = get_params(timeframe)
        period = p["mfi_period"]
        mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=period)
        if mfi is None or mfi.empty:
            return IndicatorResult("MFI", "neutral", 0.0, 0.0, "데이터 부족")

        val = float(mfi.dropna().iloc[-1])

        if val <= 20:
            strength = min((20 - val) / 20 * 0.5 + 0.5, 1.0)
            return IndicatorResult("MFI", "long", strength, val,
                                   f"MFI {val:.1f} - 자금 유출 과도 (반등 기대)")
        elif val >= 80:
            strength = min((val - 80) / 20 * 0.5 + 0.5, 1.0)
            return IndicatorResult("MFI", "short", strength, val,
                                   f"MFI {val:.1f} - 자금 유입 과도 (하락 가능)")
        else:
            return IndicatorResult("MFI", "neutral", 0.0, val,
                                   f"MFI {val:.1f} - 중립 구간")
    except Exception as e:
        logger.error("MFI 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("MFI", "neutral", 0.0, 0.0, "분석 오류")


def analyze_cmf(df: pd.DataFrame, period: int = 20, timeframe: str = "1h") -> IndicatorResult:
    """CMF (Chaikin Money Flow) — 자금 유입/유출 방향"""
    try:
        p = get_params(timeframe)
        period = p["cmf_period"]
        cmf = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=period)
        if cmf is None or cmf.empty:
            return IndicatorResult("CMF", "neutral", 0.0, 0.0, "데이터 부족")

        val = float(cmf.dropna().iloc[-1])

        if val > 0.15:
            return IndicatorResult("CMF", "long", min(val / 0.3, 0.9), val,
                                   f"CMF {val:.3f} - 강한 매수세 유입")
        elif val > 0.05:
            return IndicatorResult("CMF", "long", 0.4, val,
                                   f"CMF {val:.3f} - 약한 매수세")
        elif val < -0.15:
            return IndicatorResult("CMF", "short", min(abs(val) / 0.3, 0.9), val,
                                   f"CMF {val:.3f} - 강한 매도세 유출")
        elif val < -0.05:
            return IndicatorResult("CMF", "short", 0.4, val,
                                   f"CMF {val:.3f} - 약한 매도세")
        else:
            return IndicatorResult("CMF", "neutral", 0.0, val,
                                   f"CMF {val:.3f} - 중립")
    except Exception as e:
        logger.error("CMF 분석 오류: %s", e, exc_info=True)
        return IndicatorResult("CMF", "neutral", 0.0, 0.0, "분석 오류")

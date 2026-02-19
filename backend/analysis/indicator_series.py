"""
기술적 지표 시계열 계산 모듈
차트 오버레이/서브패널용 전체 시계열 반환
"""
import logging
import numpy as np
import pandas as pd
import pandas_ta as ta
from .indicators import get_params

logger = logging.getLogger(__name__)


def _series_to_points(series: pd.Series, timestamps: pd.Series) -> list[dict]:
    """pandas Series → [{"time": unix, "value": float}]"""
    mask = series.notna()
    return [
        {"time": int(t), "value": round(float(v), 8)}
        for t, v in zip(timestamps[mask], series[mask])
    ]


# ─── 오버레이 지표 (메인 차트 위) ────────────────────────────


def compute_ema_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    short = ta.ema(df["close"], length=p["ema_short"])
    long_ = ta.ema(df["close"], length=p["ema_long"])
    result = {}
    if short is not None:
        result["ema_short"] = _series_to_points(short, ts)
    if long_ is not None:
        result["ema_long"] = _series_to_points(long_, ts)
    return result


def compute_bb_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    bbands = ta.bbands(df["close"], length=p["bb_period"], std=p["bb_std"])
    if bbands is None or bbands.empty:
        return {}
    cols = bbands.columns.tolist()
    # pandas_ta bbands: BBL, BBM, BBU, BBB, BBP
    return {
        "bb_lower": _series_to_points(bbands[cols[0]], ts),
        "bb_middle": _series_to_points(bbands[cols[1]], ts),
        "bb_upper": _series_to_points(bbands[cols[2]], ts),
    }


def compute_vwap_series(df: pd.DataFrame) -> dict:
    ts = df["time"] if "time" in df.columns else df.index
    vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    if vwap is None or vwap.empty:
        return {}
    return {"vwap": _series_to_points(vwap, ts)}


def compute_ichimoku_series(df: pd.DataFrame) -> dict:
    ts = df["time"] if "time" in df.columns else df.index
    ichi = ta.ichimoku(df["high"], df["low"], df["close"])
    if ichi is None or len(ichi) < 2:
        return {}
    ichi_df = ichi[0]
    if ichi_df is None or ichi_df.empty:
        return {}

    result = {}
    for col in ichi_df.columns:
        key = col.split("_")[0].lower()  # ISA_9 → isa, ISB_26 → isb, etc.
        if "ISA" in col:
            result["isa"] = _series_to_points(ichi_df[col], ts)
        elif "ISB" in col:
            result["isb"] = _series_to_points(ichi_df[col], ts)
        elif "ITS" in col:
            result["tenkan"] = _series_to_points(ichi_df[col], ts)
        elif "IKS" in col:
            result["kijun"] = _series_to_points(ichi_df[col], ts)
    return result


# ─── 오실레이터 지표 (차트 아래 서브패널) ──────────────────────


def compute_rsi_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    rsi = ta.rsi(df["close"], length=p["rsi_period"])
    if rsi is None or rsi.empty:
        return {}
    return {"rsi": _series_to_points(rsi, ts)}


def compute_macd_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    macd_df = ta.macd(df["close"], fast=p["macd_fast"], slow=p["macd_slow"], signal=p["macd_signal"])
    if macd_df is None or macd_df.empty:
        return {}
    cols = macd_df.columns.tolist()
    return {
        "macd_line": _series_to_points(macd_df[cols[0]], ts),
        "signal_line": _series_to_points(macd_df[cols[1]], ts),
        "histogram": _series_to_points(macd_df[cols[2]], ts),
    }


def compute_stoch_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    stoch = ta.stoch(df["high"], df["low"], df["close"],
                     k=p["stoch_k"], d=p["stoch_d"], smooth_k=p["stoch_smooth"])
    if stoch is None or stoch.empty:
        return {}
    cols = stoch.columns.tolist()
    return {
        "stoch_k": _series_to_points(stoch[cols[0]], ts),
        "stoch_d": _series_to_points(stoch[cols[1]], ts),
    }


def compute_adx_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=p["adx_period"])
    if adx_df is None or adx_df.empty:
        return {}
    result = {}
    for col in adx_df.columns:
        if "ADX" in col and "DM" not in col:
            result["adx"] = _series_to_points(adx_df[col], ts)
        elif "DMP" in col:
            result["dmp"] = _series_to_points(adx_df[col], ts)
        elif "DMN" in col:
            result["dmn"] = _series_to_points(adx_df[col], ts)
    return result


def compute_williams_r_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    willr = ta.willr(df["high"], df["low"], df["close"], length=p["williams_period"])
    if willr is None or willr.empty:
        return {}
    return {"williams_r": _series_to_points(willr, ts)}


def compute_cci_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    cci = ta.cci(df["high"], df["low"], df["close"], length=p["cci_period"])
    if cci is None or cci.empty:
        return {}
    return {"cci": _series_to_points(cci, ts)}


def compute_mfi_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    mfi = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=p["mfi_period"])
    if mfi is None or mfi.empty:
        return {}
    return {"mfi": _series_to_points(mfi, ts)}


def compute_cmf_series(df: pd.DataFrame, timeframe: str = "1h") -> dict:
    p = get_params(timeframe)
    ts = df["time"] if "time" in df.columns else df.index
    cmf = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=p["cmf_period"])
    if cmf is None or cmf.empty:
        return {}
    return {"cmf": _series_to_points(cmf, ts)}


# ─── 디스패치 맵 ─────────────────────────────────────────────

INDICATOR_COMPUTE_MAP = {
    "ema": compute_ema_series,
    "bb": compute_bb_series,
    "vwap": compute_vwap_series,
    "ichimoku": compute_ichimoku_series,
    "rsi": compute_rsi_series,
    "macd": compute_macd_series,
    "stoch": compute_stoch_series,
    "adx": compute_adx_series,
    "williams_r": compute_williams_r_series,
    "cci": compute_cci_series,
    "mfi": compute_mfi_series,
    "cmf": compute_cmf_series,
}

# vwap, ichimoku는 timeframe 파라미터 불필요
NO_TIMEFRAME = {"vwap", "ichimoku"}


def compute_indicator_series(
    df: pd.DataFrame,
    indicators: list[str],
    timeframe: str = "1h",
) -> dict:
    """여러 지표의 시계열을 한번에 계산."""
    result = {}
    for name in indicators:
        fn = INDICATOR_COMPUTE_MAP.get(name)
        if not fn:
            continue
        try:
            if name in NO_TIMEFRAME:
                result[name] = fn(df)
            else:
                result[name] = fn(df, timeframe)
        except Exception as e:
            logger.warning("지표 시계열 계산 실패 [%s]: %s", name, e)
            result[name] = {}
    return result

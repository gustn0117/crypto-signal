"""
매크로 데이터 모듈
DXY(달러 인덱스), S&P500 선물, 금리 데이터 수집
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 캐시
_macro_cache: dict = {"data": None, "updated_at": None}
MACRO_CACHE_TTL = 1800  # 30분


async def fetch_macro_data() -> dict:
    """
    무료 API로 매크로 데이터 수집.
    - DXY 근사치 (Yahoo Finance 대안)
    - S&P500 데이터
    - Fear & Greed (주식 시장)
    """
    now = datetime.now(timezone.utc)
    if (
        _macro_cache["data"]
        and _macro_cache["updated_at"]
        and (now - _macro_cache["updated_at"]).total_seconds() < MACRO_CACHE_TTL
    ):
        return _macro_cache["data"]

    data: dict = {}
    async with httpx.AsyncClient(timeout=15) as client:
        # 1) Yahoo Finance API (비공식) - S&P500, DXY
        for ticker, key in [("^GSPC", "sp500"), ("DX-Y.NYB", "dxy")]:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    result = resp.json().get("chart", {}).get("result", [])
                    if result:
                        meta = result[0].get("meta", {})
                        price = meta.get("regularMarketPrice", 0)
                        prev_close = meta.get("previousClose", 0)
                        if price and prev_close:
                            change_pct = ((price - prev_close) / prev_close) * 100
                            data[key] = {
                                "price": round(price, 2),
                                "change_pct": round(change_pct, 2),
                            }
            except Exception:
                pass

        # 2) FRED API (금리) - 무료 키 불요 시리즈
        try:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": "DFF",  # Federal Funds Rate
                "api_key": "DEMO_KEY",
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            }
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                obs = resp.json().get("observations", [])
                if obs:
                    rate = obs[0].get("value", ".")
                    if rate != ".":
                        data["fed_rate"] = float(rate)
        except Exception:
            pass

        # 3) VIX (공포 지수) - Yahoo Finance
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=2d"
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                result = resp.json().get("chart", {}).get("result", [])
                if result:
                    meta = result[0].get("meta", {})
                    vix = meta.get("regularMarketPrice", 0)
                    if vix:
                        data["vix"] = round(vix, 2)
        except Exception:
            pass

    _macro_cache["data"] = data
    _macro_cache["updated_at"] = now
    logger.debug("매크로 데이터 업데이트: %s", list(data.keys()))
    return data


def get_macro_modifier(macro_data: dict) -> float:
    """
    매크로 데이터 기반 시장 보정값.
    - DXY 강세(상승) → 크립토 약세 편향 (-0.02)
    - VIX 높음(>30) → 리스크 오프 (-0.02)
    - DXY 약세(하락) → 크립토 강세 편향 (+0.01)
    """
    if not macro_data:
        return 0.0

    modifier = 0.0

    # DXY 보정
    dxy = macro_data.get("dxy", {})
    dxy_change = dxy.get("change_pct", 0) if isinstance(dxy, dict) else 0
    if dxy_change > 0.5:
        modifier -= 0.02  # 달러 강세 → 크립토 약세
    elif dxy_change < -0.5:
        modifier += 0.01  # 달러 약세 → 크립토 강세

    # VIX 보정
    vix = macro_data.get("vix", 0)
    if vix > 30:
        modifier -= 0.02  # 공포 → 리스크 오프
    elif vix > 25:
        modifier -= 0.01

    return modifier


def get_macro_summary(macro_data: dict) -> dict:
    """API용 매크로 데이터 요약."""
    if not macro_data:
        return {"available": False}

    return {
        "available": True,
        "sp500": macro_data.get("sp500"),
        "dxy": macro_data.get("dxy"),
        "vix": macro_data.get("vix"),
        "fed_rate": macro_data.get("fed_rate"),
    }

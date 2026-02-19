"""
시장 맥락 분석 모듈
BTC 도미넌스, 시장 전체 모멘텀, 공포탐욕지수
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas_ta as ta

logger = logging.getLogger(__name__)

# Fear & Greed 캐시 (1일 1회)
_fg_cache: dict = {"value": None, "fetched_at": None}
FG_CACHE_TTL = 3600  # 1시간


async def fetch_fear_greed_index() -> int | None:
    """
    공포탐욕지수 조회 (alternative.me 무료 API)
    0 = Extreme Fear, 100 = Extreme Greed
    """
    now = datetime.now(timezone.utc)
    if (_fg_cache["value"] is not None
            and _fg_cache["fetched_at"]
            and (now - _fg_cache["fetched_at"]).total_seconds() < FG_CACHE_TTL):
        return _fg_cache["value"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.alternative.me/fng/?limit=1")
            data = resp.json()
            value = int(data["data"][0]["value"])
            _fg_cache["value"] = value
            _fg_cache["fetched_at"] = now
            logger.info("공포탐욕지수 갱신: %d", value)
            return value
    except Exception as e:
        logger.warning("공포탐욕지수 조회 실패: %s", e)
        return _fg_cache.get("value")


def calculate_market_momentum(signals: list[dict]) -> float | None:
    """
    시장 전체 모멘텀: 전체 코인 중 롱 시그널 비율
    0.0 = 전부 숏, 1.0 = 전부 롱
    """
    if not signals:
        return None

    non_neutral = [s for s in signals if s.get("signal") != "NEUTRAL"]
    if not non_neutral:
        return 0.5

    long_count = sum(1 for s in non_neutral if "LONG" in s.get("signal", ""))
    return round(long_count / len(non_neutral), 3)


def calculate_btc_dominance_change(
    btc_change_24h: float | None,
    market_avg_change_24h: float | None,
) -> float | None:
    """
    BTC 도미넌스 변화율 추정
    BTC가 시장 평균 대비 얼마나 강세/약세인지
    양수 = BTC 강세 (알트 약세 가능)
    음수 = BTC 약세 (알트 강세 가능)
    """
    if btc_change_24h is None or market_avg_change_24h is None:
        return None
    return round(btc_change_24h - market_avg_change_24h, 2)


async def build_market_context(
    latest_signals: list[dict],
    btc_ticker: dict | None = None,
    all_tickers: list[dict] | None = None,
    sentiment_api_key: str = "",
) -> dict:
    """
    시장 맥락 데이터 수집 및 통합.
    signal_engine에 전달하여 신뢰도 보정에 사용.
    """
    context = {}

    # 1. Fear & Greed
    fg = await fetch_fear_greed_index()
    if fg is not None:
        context["fear_greed"] = fg

    # 2. 시장 모멘텀
    momentum = calculate_market_momentum(latest_signals)
    if momentum is not None:
        context["market_momentum"] = momentum

    # 3. BTC 도미넌스 변화
    if btc_ticker and all_tickers and len(all_tickers) > 0:
        btc_change = btc_ticker.get("change_24h", 0) or 0
        avg_change = sum(t.get("change_24h", 0) or 0 for t in all_tickers) / len(all_tickers)
        dom_change = calculate_btc_dominance_change(btc_change, avg_change)
        if dom_change is not None:
            context["btc_dominance_change"] = dom_change

    # 4. BTC 시그널 방향 (알트코인 상관관계용)
    for sig in latest_signals:
        if sig.get("symbol") == "BTC/USDT":
            context["btc_signal"] = sig.get("signal", "NEUTRAL")
            break

    # 5. 뉴스 감성 분석
    if sentiment_api_key:
        try:
            from .sentiment import fetch_crypto_sentiment
            sentiment = await fetch_crypto_sentiment(sentiment_api_key)
            if sentiment and sentiment.get("sentiment_score") is not None:
                context["sentiment_score"] = sentiment["sentiment_score"]
                context["sentiment_detail"] = sentiment
        except Exception as e:
            logger.debug("감성 분석 실패: %s", e)

    # 6. 온체인 데이터
    try:
        from .onchain import fetch_onchain_data, get_onchain_modifier
        onchain = await fetch_onchain_data()
        if onchain:
            context["onchain"] = onchain
            context["onchain_modifier"] = get_onchain_modifier(onchain)
    except Exception as e:
        logger.debug("온체인 데이터 실패: %s", e)

    return context

"""
감성 분석 모듈
CryptoPanic 뉴스 감성 + 소셜 데이터 기반 시장 심리 분석
"""
import logging
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

# 캐시
_sentiment_cache: dict = {"score": 0.0, "data": None, "updated_at": None}
SENTIMENT_CACHE_TTL = 300  # 5분


async def fetch_crypto_sentiment(api_key: str = "") -> dict:
    """
    CryptoPanic API로 크립토 뉴스 감성 수집.
    api_key 없으면 무료 공개 피드 사용 (제한적).
    Returns: {"score": float (-1~+1), "bullish": int, "bearish": int, "total": int}
    """
    now = datetime.now(timezone.utc)
    if (
        _sentiment_cache["updated_at"]
        and (now - _sentiment_cache["updated_at"]).total_seconds() < SENTIMENT_CACHE_TTL
    ):
        return _sentiment_cache

    try:
        url = "https://cryptopanic.com/api/free/v1/posts/"
        params = {"auth_token": api_key, "filter": "important", "kind": "news"}
        if not api_key:
            # 무료 엔드포인트 (토큰 없이도 기본 데이터 제공)
            url = "https://cryptopanic.com/api/free/v1/posts/"
            params = {"filter": "important"}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)

        if resp.status_code != 200:
            logger.debug("CryptoPanic API 응답: %d", resp.status_code)
            return _sentiment_cache

        data = resp.json()
        posts = data.get("results", [])

        if not posts:
            return _sentiment_cache

        bullish = 0
        bearish = 0
        for post in posts[:30]:  # 최근 30개 뉴스
            votes = post.get("votes", {})
            positive = votes.get("positive", 0) + votes.get("important", 0)
            negative = votes.get("negative", 0) + votes.get("toxic", 0)
            if positive > negative:
                bullish += 1
            elif negative > positive:
                bearish += 1

        total = bullish + bearish
        score = (bullish - bearish) / total if total > 0 else 0.0

        _sentiment_cache.update({
            "score": round(score, 3),
            "bullish": bullish,
            "bearish": bearish,
            "total": len(posts),
            "updated_at": now,
        })
        logger.debug("감성 분석: score=%.3f (긍정 %d / 부정 %d)", score, bullish, bearish)
        return _sentiment_cache

    except Exception as e:
        logger.debug("감성 분석 실패: %s", e)
        return _sentiment_cache


def get_sentiment_modifier(sentiment_score: float, signal: str) -> float:
    """
    감성 점수 기반 신뢰도 보정값 반환.
    강한 긍정(>0.5): LONG +0.03, SHORT -0.02
    강한 부정(<-0.5): SHORT +0.03, LONG -0.02
    """
    is_long = signal in ("LONG", "STRONG_LONG")
    is_short = signal in ("SHORT", "STRONG_SHORT")

    if sentiment_score > 0.5:
        return 0.03 if is_long else (-0.02 if is_short else 0.0)
    elif sentiment_score < -0.5:
        return 0.03 if is_short else (-0.02 if is_long else 0.0)
    elif sentiment_score > 0.3:
        return 0.01 if is_long else 0.0
    elif sentiment_score < -0.3:
        return 0.01 if is_short else 0.0
    return 0.0

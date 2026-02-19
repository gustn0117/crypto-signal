"""
온체인 데이터 모듈
BTC/ETH 기본 온체인 지표 (무료 API)
"""
import logging
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

# 캐시
_onchain_cache: dict = {"data": None, "updated_at": None}
ONCHAIN_CACHE_TTL = 600  # 10분


async def fetch_onchain_data() -> dict:
    """
    무료 API로 기본 온체인 데이터 수집.
    - BTC 해시레이트 (blockchain.info)
    - BTC 멤풀 크기 (blockchain.info)
    - ETH gas 가격 (etherscan 불필요, 공개 API)
    """
    now = datetime.now(timezone.utc)
    if (
        _onchain_cache["updated_at"]
        and (now - _onchain_cache["updated_at"]).total_seconds() < ONCHAIN_CACHE_TTL
    ):
        return _onchain_cache.get("data", {})

    data = {}
    async with httpx.AsyncClient(timeout=10) as client:
        # BTC 해시레이트
        try:
            resp = await client.get("https://blockchain.info/q/hashrate")
            if resp.status_code == 200:
                data["btc_hashrate"] = float(resp.text)
        except Exception:
            pass

        # BTC 미확인 트랜잭션 수 (멤풀)
        try:
            resp = await client.get("https://blockchain.info/q/unconfirmedcount")
            if resp.status_code == 200:
                data["btc_mempool_count"] = int(resp.text)
        except Exception:
            pass

        # BTC 24h 거래량 (USD)
        try:
            resp = await client.get("https://blockchain.info/q/24hrtransactioncount")
            if resp.status_code == 200:
                data["btc_tx_count_24h"] = int(resp.text)
        except Exception:
            pass

        # ETH gas 가격 (Blocknative public API)
        try:
            resp = await client.get(
                "https://api.blocknative.com/gasprices/blockprices",
                headers={"Authorization": ""},  # 무료 요청
            )
            if resp.status_code == 200:
                block_prices = resp.json().get("blockPrices", [])
                if block_prices:
                    est = block_prices[0].get("estimatedPrices", [])
                    if est:
                        data["eth_gas_gwei"] = est[0].get("price", 0)
        except Exception:
            pass

    _onchain_cache["data"] = data
    _onchain_cache["updated_at"] = now
    logger.debug("온체인 데이터 업데이트: %s", list(data.keys()))
    return data


def get_onchain_modifier(onchain_data: dict) -> float:
    """
    온체인 데이터 기반 시장 보정값.
    - 멤풀 과다(>50000) → 네트워크 혼잡 → 약한 부정 -0.01
    - 해시레이트 정상 → 0.0
    """
    if not onchain_data:
        return 0.0

    modifier = 0.0
    mempool = onchain_data.get("btc_mempool_count", 0)
    if mempool > 50000:
        modifier -= 0.01  # 네트워크 혼잡

    return modifier

"""
OHLCV 데이터 수집기
바이낸스에서 항상 최신 캔들을 가져와 SQLite에 저장
"""
import asyncio
import logging

from exchange import AsyncBinanceClient
from db.candle_repo import CandleRepo

logger = logging.getLogger(__name__)


class DataCollector:
    def __init__(self, client: AsyncBinanceClient, candle_repo: CandleRepo):
        self.client = client
        self.repo = candle_repo

    async def collect(self, symbol: str, timeframe: str,
                       limit: int = 200) -> int:
        """
        항상 거래소에서 최신 캔들 데이터를 가져와 DB에 저장.
        매번 최신 limit개를 수집하므로 실시간 데이터 보장.
        """
        try:
            raw = await self.client.fetch_ohlcv_raw(
                symbol, timeframe, limit=limit
            )
        except Exception as e:
            logger.error(f"[{symbol}/{timeframe}] 수집 실패: {e}")
            return 0

        if not raw:
            return 0

        count = await self.repo.upsert_candles(symbol, timeframe, raw)
        return count

    async def collect_many(self, symbols: list[str], timeframe: str,
                            concurrency: int = 10,
                            limit: int = 200) -> dict[str, int]:
        """
        여러 심볼 병렬 수집. Semaphore로 동시 API 호출 제한.
        """
        semaphore = asyncio.Semaphore(concurrency)
        results: dict[str, int] = {}

        async def _collect_one(sym: str):
            async with semaphore:
                try:
                    count = await self.collect(sym, timeframe, limit)
                    results[sym] = count
                except Exception as e:
                    logger.warning(f"[{sym}/{timeframe}] 수집 실패: {e}")
                    results[sym] = 0

        tasks = [_collect_one(s) for s in symbols]
        await asyncio.gather(*tasks)
        return results

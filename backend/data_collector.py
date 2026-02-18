"""
OHLCV 데이터 수집기
바이낸스에서 캔들 데이터를 수집하여 DB에 저장
- 실시간 수집 (스캔용)
- 히스토리 백필 (과거 데이터 대량 다운로드)
- 증분 수집 (빈 구간 채우기)
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

from exchange import AsyncBinanceClient
from db.candle_repo import CandleRepo

logger = logging.getLogger(__name__)

# 타임프레임 → 밀리초 변환
TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


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

    # ─── 히스토리 백필 ─────────────────────────────────────

    async def backfill_symbol(
        self,
        symbol: str,
        timeframe: str,
        days: int = 730,
        batch_size: int = 1000,
    ) -> int:
        """
        단일 심볼의 과거 데이터를 페이지네이션으로 전부 다운로드.

        1. DB에 저장된 가장 오래된 타임스탬프 확인
        2. 그보다 더 과거 데이터가 있으면 역방향으로 수집
        3. DB에 저장된 가장 최신 타임스탬프부터 현재까지 빈 구간 수집

        Returns: 총 저장된 캔들 수
        """
        tf_ms = TF_MS.get(timeframe, 3_600_000)
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (days * 86_400_000)
        total_saved = 0

        # DB에서 기존 데이터 범위 확인
        oldest_ts = await self.repo.get_oldest_timestamp(symbol, timeframe)
        latest_ts = await self.repo.get_latest_timestamp(symbol, timeframe)

        if oldest_ts and latest_ts:
            # 이미 데이터가 있음 - 양쪽으로 확장
            # 1) 과거 방향: start_ms → oldest_ts
            if start_ms < oldest_ts - tf_ms:
                logger.info(
                    "[%s/%s] 과거 백필: %s ~ %s",
                    symbol, timeframe,
                    datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                    datetime.fromtimestamp(oldest_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                )
                saved = await self._fetch_range(
                    symbol, timeframe, start_ms, oldest_ts, batch_size
                )
                total_saved += saved

            # 2) 최신 방향: latest_ts → now
            if now_ms > latest_ts + tf_ms:
                saved = await self._fetch_range(
                    symbol, timeframe, latest_ts + tf_ms, now_ms, batch_size
                )
                total_saved += saved
        else:
            # 데이터 없음 - 처음부터 전부 수집
            logger.info(
                "[%s/%s] 전체 백필: %s ~ 현재",
                symbol, timeframe,
                datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            )
            saved = await self._fetch_range(
                symbol, timeframe, start_ms, now_ms, batch_size
            )
            total_saved += saved

        return total_saved

    async def _fetch_range(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
        batch_size: int = 1000,
    ) -> int:
        """start_ms부터 end_ms까지 페이지네이션으로 수집."""
        tf_ms = TF_MS.get(timeframe, 3_600_000)
        cursor = start_ms
        total = 0
        consecutive_empty = 0

        while cursor < end_ms:
            try:
                raw = await self.client.fetch_ohlcv_raw(
                    symbol, timeframe, since=cursor, limit=batch_size
                )
            except Exception as e:
                logger.warning("[%s/%s] 백필 API 실패 (cursor=%d): %s", symbol, timeframe, cursor, e)
                # 레이트 리밋일 수 있으므로 잠시 대기 후 재시도
                await asyncio.sleep(2)
                try:
                    raw = await self.client.fetch_ohlcv_raw(
                        symbol, timeframe, since=cursor, limit=batch_size
                    )
                except Exception:
                    # 2번째도 실패하면 다음 구간으로 스킵
                    cursor += batch_size * tf_ms
                    continue

            if not raw:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                cursor += batch_size * tf_ms
                continue

            consecutive_empty = 0

            # 범위 내 데이터만 필터
            filtered = [c for c in raw if c[0] < end_ms]
            if filtered:
                count = await self.repo.upsert_candles(symbol, timeframe, filtered)
                total += count

            # 다음 페이지: 마지막 캔들의 다음 타임스탬프
            last_ts = raw[-1][0]
            if last_ts <= cursor:
                # 진행 안 됨 → 강제 전진
                cursor += batch_size * tf_ms
            else:
                cursor = last_ts + tf_ms

            # API 레이트 리밋 보호 (ccxt enableRateLimit 외 추가 보호)
            await asyncio.sleep(0.15)

        return total

    async def backfill_all(
        self,
        symbols: list[str],
        timeframes: list[str],
        days: int = 730,
        batch_size: int = 1000,
        concurrency: int = 3,
    ) -> dict:
        """
        전체 심볼 × 타임프레임 백필.
        동시 심볼 수를 제한하여 API 레이트 리밋 방지.
        """
        semaphore = asyncio.Semaphore(concurrency)
        results: dict[str, dict[str, int]] = {}
        lock = asyncio.Lock()

        async def _backfill_one(sym: str, tf: str):
            async with semaphore:
                try:
                    count = await self.backfill_symbol(sym, tf, days, batch_size)
                    async with lock:
                        if sym not in results:
                            results[sym] = {}
                        results[sym][tf] = count
                    if count > 0:
                        logger.info("[%s/%s] 백필 완료: %d개 캔들", sym, tf, count)
                except Exception as e:
                    logger.error("[%s/%s] 백필 실패: %s", sym, tf, e)
                    async with lock:
                        if sym not in results:
                            results[sym] = {}
                        results[sym][tf] = 0

        # 타임프레임별로 순차 (큰 TF부터 → API 호출 수 적음)
        tf_order = sorted(timeframes, key=lambda t: TF_MS.get(t, 0), reverse=True)

        for tf in tf_order:
            logger.info("=== 백필 시작: %s (대상: %d개 심볼) ===", tf, len(symbols))
            tasks = [_backfill_one(sym, tf) for sym in symbols]
            await asyncio.gather(*tasks)

        # 총 요약
        total_candles = sum(
            count for sym_data in results.values() for count in sym_data.values()
        )
        logger.info(
            "전체 백필 완료: %d개 심볼 × %d개 타임프레임, 총 %d개 캔들",
            len(symbols), len(timeframes), total_candles,
        )
        return results

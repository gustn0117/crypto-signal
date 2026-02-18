"""
OHLCV 캔들 데이터 저장소 (Supabase PostgREST)
"""
import pandas as pd
from typing import Optional
from supabase import AsyncClient


class CandleRepo:
    def __init__(self, client: AsyncClient, schema: str = "coin"):
        self._client = client
        self._schema = schema

    def _table(self):
        return self._client.schema(self._schema).table("ohlcv")

    async def upsert_candles(self, symbol: str, timeframe: str,
                              candles: list[list]) -> int:
        """
        ccxt raw 포맷 [[timestamp_ms, o, h, l, c, v], ...] 일괄 upsert.
        """
        rows = [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp_ms": int(c[0]),
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
            }
            for c in candles
        ]
        if not rows:
            return 0

        await (
            self._table()
            .upsert(rows, on_conflict="symbol,timeframe,timestamp_ms")
            .execute()
        )
        return len(rows)

    async def get_candles(self, symbol: str, timeframe: str,
                           limit: int = 200) -> pd.DataFrame:
        """
        DB에서 최신 limit개 캔들을 DataFrame으로 반환.
        """
        resp = await (
            self._table()
            .select("timestamp_ms, open, high, low, close, volume")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .order("timestamp_ms", desc=True)
            .limit(limit)
            .execute()
        )

        rows = resp.data
        if not rows:
            return pd.DataFrame()

        rows = list(reversed(rows))
        df = pd.DataFrame(rows)
        df.rename(columns={"timestamp_ms": "timestamp"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    async def get_latest_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """증분 수집용: 마지막 캔들의 timestamp_ms 반환."""
        resp = await (
            self._table()
            .select("timestamp_ms")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .order("timestamp_ms", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["timestamp_ms"]
        return None

    async def get_oldest_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """백필용: 가장 오래된 캔들의 timestamp_ms 반환."""
        resp = await (
            self._table()
            .select("timestamp_ms")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .order("timestamp_ms", desc=False)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["timestamp_ms"]
        return None

    async def get_candle_count(self, symbol: str, timeframe: str) -> int:
        """저장된 캔들 수 조회."""
        resp = await (
            self._table()
            .select("timestamp_ms", count="exact")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .execute()
        )
        return resp.count or 0

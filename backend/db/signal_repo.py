"""
시그널 히스토리 저장소 (Supabase PostgREST)
"""
from supabase import AsyncClient


class SignalRepo:
    def __init__(self, client: AsyncClient, schema: str = "coin"):
        self._client = client
        self._schema = schema

    def _table(self):
        return self._client.schema(self._schema).table("signals")

    async def save_signals_batch(self, signals: list[dict], scan_id: str):
        """스캔 결과 시그널을 일괄 저장."""
        rows = [
            {
                "symbol": s["symbol"],
                "timeframe": s["timeframe"],
                "signal": s["signal"],
                "confidence": s["confidence"],
                "current_price": s["current_price"],
                "indicators": s["indicators"],
                "candle_patterns": s["candle_patterns"],
                "volume_signals": s["volume_signals"],
                "summary": s["summary"],
                "created_at": s["timestamp"],
                "scan_id": scan_id,
            }
            for s in signals
        ]
        if not rows:
            return

        await self._table().insert(rows).execute()

    async def get_signal_history(self, symbol: str = None,
                                  timeframe: str = None,
                                  limit: int = 100,
                                  offset: int = 0) -> list[dict]:
        """히스토리 조회 (필터 선택적)."""
        query = self._table().select("*")

        if symbol:
            query = query.eq("symbol", symbol)
        if timeframe:
            query = query.eq("timeframe", timeframe)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        resp = await query.execute()
        return [self._row_to_dict(row) for row in resp.data]

    def _row_to_dict(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "signal": row["signal"],
            "confidence": row["confidence"],
            "current_price": row["current_price"],
            "indicators": row["indicators"],
            "candle_patterns": row["candle_patterns"],
            "volume_signals": row["volume_signals"],
            "summary": row["summary"],
            "timestamp": row["created_at"],
            "scan_id": row["scan_id"],
        }

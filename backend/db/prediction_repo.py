"""
가격 예측 저장소 (Supabase PostgREST)
"""
from datetime import datetime, timezone
from supabase import AsyncClient


class PredictionRepo:
    def __init__(self, client: AsyncClient, schema: str = "coin"):
        self._client = client
        self._schema = schema

    def _table(self):
        return self._client.schema(self._schema).table("predictions")

    async def create_prediction(
        self,
        symbol: str,
        timeframe: str,
        signal_direction: str,
        confidence: float,
        entry_price: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float,
        take_profit_3: float,
        atr: float,
        atr_percent: float,
        predicted_path: list[dict],
        upper_bound_path: list[dict],
        lower_bound_path: list[dict],
        horizon_candles: int = 24,
        auto_generated: bool = False,
        regime: str | None = None,
        num_simulations: int = 200,
        calibration_factor: float = 1.0,
    ) -> int:
        """새 예측 생성. 기존 ACTIVE 예측은 EXPIRED 처리."""
        # 기존 활성 예측 만료
        await (
            self._table()
            .update({"status": "EXPIRED"})
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .eq("status", "ACTIVE")
            .execute()
        )

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "signal_direction": signal_direction,
            "confidence": confidence,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "take_profit_3": take_profit_3,
            "atr": atr,
            "atr_percent": atr_percent,
            "predicted_path": predicted_path,
            "upper_bound_path": upper_bound_path,
            "lower_bound_path": lower_bound_path,
            "horizon_candles": horizon_candles,
            "created_at": now,
            "status": "ACTIVE",
            "auto_generated": 1 if auto_generated else 0,
            "regime": regime,
            "num_simulations": num_simulations,
            "calibration_factor": calibration_factor,
        }

        resp = await self._table().insert(data).execute()
        if not resp.data:
            raise RuntimeError(f"예측 생성 실패: {symbol}/{timeframe}")
        return resp.data[0]["id"]

    async def get_active_prediction(self, symbol: str, timeframe: str) -> dict | None:
        """심볼+타임프레임의 활성 예측 조회 (가장 최근 1개)"""
        resp = await (
            self._table()
            .select("*")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .eq("status", "ACTIVE")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    async def get_prediction_by_id(self, prediction_id: int) -> dict | None:
        resp = await (
            self._table()
            .select("*")
            .eq("id", prediction_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    async def get_predictions_history(
        self,
        symbol: str = None,
        status: str = None,
        direction: str = None,
        timeframe: str = None,
        result: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """예측 히스토리 조회 (필터 확장)"""
        query = self._table().select("*")
        if symbol:
            query = query.eq("symbol", symbol)
        if status:
            query = query.eq("status", status)
        if direction:
            query = query.eq("signal_direction", direction)
        if timeframe:
            query = query.eq("timeframe", timeframe)
        if result:
            query = query.eq("result", result)
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        resp = await query.execute()
        return resp.data

    async def get_predictions_count(
        self,
        symbol: str = None,
        status: str = None,
        direction: str = None,
        timeframe: str = None,
        result: str = None,
    ) -> int:
        """예측 총 개수 (페이지네이션용)"""
        query = self._table().select("id", count="exact")
        if symbol:
            query = query.eq("symbol", symbol)
        if status:
            query = query.eq("status", status)
        if direction:
            query = query.eq("signal_direction", direction)
        if timeframe:
            query = query.eq("timeframe", timeframe)
        if result:
            query = query.eq("result", result)
        resp = await query.execute()
        return resp.count or 0

    async def get_pending_verifications(self) -> list[dict]:
        """검증 대기 중인 활성 예측 조회"""
        resp = await (
            self._table()
            .select("*")
            .eq("status", "ACTIVE")
            .order("created_at")
            .execute()
        )
        return resp.data

    async def update_verification(
        self,
        prediction_id: int,
        status: str,
        actual_path: list[dict],
        result: str,
        accuracy_score: float,
        max_favorable: float,
        max_adverse: float,
        final_price: float,
        notes: str = None,
    ) -> None:
        """예측 검증 결과 업데이트"""
        now = datetime.now(timezone.utc).isoformat()
        await (
            self._table()
            .update({
                "status": status,
                "verified_at": now,
                "actual_path": actual_path,
                "result": result,
                "accuracy_score": accuracy_score,
                "max_favorable": max_favorable,
                "max_adverse": max_adverse,
                "final_price": final_price,
                "notes": notes,
            })
            .eq("id", prediction_id)
            .execute()
        )

    async def get_accuracy_stats(self, symbol: str = None) -> dict:
        """정확도 통계 (RPC 함수 사용)"""
        resp = await (
            self._client.schema(self._schema)
            .rpc("get_accuracy_stats", {"p_symbol": symbol})
            .execute()
        )
        if resp.data:
            return resp.data
        return {
            "total_predictions": 0,
            "avg_accuracy_score": 0,
            "tp_hit_rate": 0,
            "sl_hit_rate": 0,
            "avg_max_favorable_excursion": 0,
            "avg_max_adverse_excursion": 0,
        }

    async def get_all_active_predictions(self) -> list[dict]:
        """모든 심볼의 ACTIVE 예측 조회 (실시간 추적용)."""
        resp = await (
            self._table()
            .select("*")
            .eq("status", "ACTIVE")
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data

    async def update_progress(
        self,
        prediction_id: int,
        pnl_pct: float,
        rr_current: float,
        time_pct: float,
        path_accuracy: float,
    ) -> None:
        """실시간 진행 데이터 업데이트."""
        now = datetime.now(timezone.utc).isoformat()
        await (
            self._table()
            .update({
                "progress_pnl_pct": pnl_pct,
                "progress_rr_current": rr_current,
                "progress_time_pct": time_pct,
                "progress_path_accuracy": path_accuracy,
                "progress_updated_at": now,
            })
            .eq("id", prediction_id)
            .execute()
        )

    async def get_global_prediction_stats(self) -> dict:
        """대시보드용 전체 예측 통계 (RPC 함수 사용)."""
        resp = await (
            self._client.schema(self._schema)
            .rpc("get_global_prediction_stats", {})
            .execute()
        )
        if resp.data:
            return resp.data
        return {
            "total_predictions": 0,
            "active_predictions": 0,
            "avg_accuracy": 0,
            "win_rate": 0,
            "leaderboard": [],
            "recent_results": [],
        }

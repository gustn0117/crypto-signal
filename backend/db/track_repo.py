"""
시그널 트랙 저장소 - 점진적 확인 시스템용 (Supabase PostgREST)
"""
from datetime import datetime, timezone
from supabase import AsyncClient


class SignalTrackRepo:
    def __init__(self, client: AsyncClient, schema: str = "coin"):
        self._client = client
        self._schema = schema

    def _tracks(self):
        return self._client.schema(self._schema).table("signal_tracks")

    def _transitions(self):
        return self._client.schema(self._schema).table("signal_transitions")

    async def get_active_track(self, symbol: str, timeframe: str) -> dict | None:
        """활성 트랙 조회 (EXPIRED 제외)"""
        resp = await (
            self._tracks()
            .select("*")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .neq("state", "EXPIRED")
            .order("last_updated_at", desc=True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    async def get_active_tracks(self, timeframe: str = None,
                                 state_filter: str = None) -> list[dict]:
        """전체 활성 트랙 목록"""
        query = self._tracks().select("*").neq("state", "EXPIRED")

        if timeframe:
            query = query.eq("timeframe", timeframe)
        if state_filter:
            query = query.eq("state", state_filter)

        query = query.order("confidence", desc=True)
        resp = await query.execute()
        return resp.data

    async def create_track(self, symbol: str, timeframe: str,
                            direction: str, signal: str,
                            confidence: float, price: float) -> int:
        """FORMING 상태로 새 트랙 생성"""
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "state": "FORMING",
            "current_signal": signal,
            "confidence": confidence,
            "peak_confidence": confidence,
            "consecutive_scans": 1,
            "weak_scans": 0,
            "first_detected_at": now,
            "last_updated_at": now,
            "first_price": price,
            "current_price": price,
        }
        resp = await self._tracks().insert(data).execute()
        if not resp.data:
            raise RuntimeError(f"트랙 생성 실패: {symbol}/{timeframe}")
        track_id = resp.data[0]["id"]

        # 전환 로그 (None → FORMING)
        await self._log_transition(
            track_id, symbol, timeframe, None, "FORMING",
            direction, confidence, price
        )
        return track_id

    async def transition_track(self, track_id: int, new_state: str,
                                signal: str, confidence: float,
                                price: float) -> None:
        """트랙 상태 전환 + 전환 로그"""
        resp = await (
            self._tracks()
            .select("*")
            .eq("id", track_id)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return

        track = resp.data[0]
        now = datetime.now(timezone.utc).isoformat()

        peak = max(track["peak_confidence"], confidence)
        consecutive = track["consecutive_scans"] + 1 if new_state != "EXPIRED" else track["consecutive_scans"]
        weak_scans = 0

        if new_state == "WEAKENING":
            weak_scans = track["weak_scans"] + 1
        elif new_state == "CONFIRMED" and track["state"] == "WEAKENING":
            weak_scans = 0

        confirmed_at = track["confirmed_at"]
        if new_state == "CONFIRMED" and not confirmed_at:
            confirmed_at = now

        await (
            self._tracks()
            .update({
                "state": new_state,
                "current_signal": signal,
                "confidence": confidence,
                "peak_confidence": peak,
                "consecutive_scans": consecutive,
                "weak_scans": weak_scans,
                "last_updated_at": now,
                "confirmed_at": confirmed_at,
                "current_price": price,
            })
            .eq("id", track_id)
            .execute()
        )

        # 전환 로그
        await self._log_transition(
            track_id, track["symbol"], track["timeframe"],
            track["state"], new_state, track["direction"],
            confidence, price
        )

    async def update_track_stats(self, track_id: int, signal: str,
                                  confidence: float, price: float) -> None:
        """상태 변경 없이 통계만 업데이트"""
        # peak_confidence: MAX 계산을 위해 현재값 조회
        resp = await (
            self._tracks()
            .select("peak_confidence, consecutive_scans")
            .eq("id", track_id)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return

        current = resp.data[0]
        now = datetime.now(timezone.utc).isoformat()

        await (
            self._tracks()
            .update({
                "current_signal": signal,
                "confidence": confidence,
                "peak_confidence": max(current["peak_confidence"], confidence),
                "consecutive_scans": current["consecutive_scans"] + 1,
                "last_updated_at": now,
                "current_price": price,
            })
            .eq("id", track_id)
            .execute()
        )

    async def get_recent_transitions(self, limit: int = 50,
                                      symbol: str = None) -> list[dict]:
        """최근 상태 전환 로그"""
        query = self._transitions().select("*")
        if symbol:
            query = query.eq("symbol", symbol)
        query = query.order("created_at", desc=True).limit(limit)
        resp = await query.execute()
        return resp.data

    async def cleanup_expired(self, older_than_hours: int = 48) -> int:
        """오래된 EXPIRED 트랙 + 관련 transition 삭제 (RPC 함수 사용)"""
        resp = await self._client.schema(self._schema).rpc(
            "cleanup_expired_tracks", {"p_hours": older_than_hours}
        ).execute()
        return resp.data if isinstance(resp.data, int) else 0

    async def _log_transition(self, track_id: int, symbol: str,
                               timeframe: str, from_state: str | None,
                               to_state: str, direction: str,
                               confidence: float, price: float) -> None:
        """상태 전환 로그 기록"""
        now = datetime.now(timezone.utc).isoformat()
        await (
            self._transitions()
            .insert({
                "track_id": track_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "from_state": from_state,
                "to_state": to_state,
                "direction": direction,
                "confidence": confidence,
                "current_price": price,
                "created_at": now,
            })
            .execute()
        )

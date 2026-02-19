"""
알림 DB 영구 저장소
인메모리 대신 Supabase에 알림을 저장하여 서버 재시작 시에도 유지
"""
import logging
from datetime import datetime, timezone
from supabase import AsyncClient

logger = logging.getLogger(__name__)


class AlertRepo:
    """알림 CRUD - Supabase 영구 저장"""

    def __init__(self, client: AsyncClient, schema: str = "coin"):
        self._client = client
        self._schema = schema

    def _table(self):
        return self._client.schema(self._schema).table("alerts")

    async def save_alert(self, alert: dict) -> int | None:
        """알림 저장 (반환: 생성된 ID)"""
        try:
            row = {
                "symbol": alert.get("symbol"),
                "signal": alert.get("signal"),
                "confidence": alert.get("confidence", 0),
                "current_price": alert.get("current_price", 0),
                "summary": alert.get("summary", ""),
                "trade_params": alert.get("trade_params"),
                "timestamp": alert.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "read": False,
                "transition": alert.get("transition", ""),
            }
            resp = await self._table().insert(row).execute()
            if resp.data:
                return resp.data[0].get("id")
            return None
        except Exception as e:
            logger.error("알림 저장 실패: %s", e)
            return None

    async def get_alerts(self, limit: int = 50, unread_only: bool = False) -> dict:
        """알림 목록 조회"""
        try:
            query = self._table().select("*").order("timestamp", desc=True)
            if unread_only:
                query = query.eq("read", False)
            query = query.limit(limit)
            resp = await query.execute()
            alerts = resp.data or []

            # 총 개수 & 읽지 않은 수
            total_resp = await self._table().select("id", count="exact").execute()
            total = total_resp.count or len(alerts)

            unread_resp = await self._table().select("id", count="exact").eq("read", False).execute()
            unread = unread_resp.count or 0

            return {
                "alerts": alerts,
                "total": total,
                "unread": unread,
            }
        except Exception as e:
            logger.error("알림 조회 실패: %s", e)
            return {"alerts": [], "total": 0, "unread": 0}

    async def mark_read(self, alert_ids: list[int] | None = None) -> bool:
        """알림 읽음 처리 (ids가 None이면 전부)"""
        try:
            if alert_ids:
                await self._table().update({"read": True}).in_("id", alert_ids).execute()
            else:
                await self._table().update({"read": True}).eq("read", False).execute()
            return True
        except Exception as e:
            logger.error("알림 읽음 처리 실패: %s", e)
            return False

    async def get_unread_count(self) -> int:
        """읽지 않은 알림 수"""
        try:
            resp = await self._table().select("id", count="exact").eq("read", False).execute()
            return resp.count or 0
        except Exception as e:
            logger.error("미읽은 알림 수 조회 실패: %s", e)
            return 0

    async def check_cooldown(self, cooldown_key: str, cooldown_minutes: int) -> bool:
        """쿨다운 체크 (최근 N분 이내 동일 키로 알림이 있는지)"""
        try:
            cutoff = datetime.now(timezone.utc)
            # 최근 알림에서 transition 필드로 쿨다운 키 검색
            resp = (
                await self._table()
                .select("timestamp")
                .eq("transition", cooldown_key)
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if not resp.data:
                return False  # 쿨다운 아님 → 알림 발송 가능

            raw_ts = resp.data[0]["timestamp"]
            if raw_ts.endswith("Z"):
                raw_ts = raw_ts[:-1] + "+00:00"
            last_ts = datetime.fromisoformat(raw_ts)
            elapsed = (cutoff - last_ts).total_seconds()
            return elapsed < cooldown_minutes * 60  # True면 쿨다운 중
        except Exception as e:
            logger.debug("쿨다운 체크 실패: %s", e)
            return False

    async def cleanup_old(self, keep_count: int = 500):
        """오래된 알림 정리 (최근 N개만 유지)"""
        try:
            resp = (
                await self._table()
                .select("id")
                .order("timestamp", desc=True)
                .range(keep_count, keep_count + 1000)
                .execute()
            )
            if resp.data:
                old_ids = [r["id"] for r in resp.data]
                await self._table().delete().in_("id", old_ids).execute()
                logger.info("오래된 알림 %d개 정리", len(old_ids))
        except Exception as e:
            logger.debug("알림 정리 실패: %s", e)

"""
시그널 상태 머신 - 점진적 확인 시스템

상태 흐름:
  FORMING → CONFIRMING → CONFIRMED → WEAKENING → EXPIRED
"""
import logging
from db.track_repo import SignalTrackRepo

logger = logging.getLogger(__name__)

# 확정 전환 조건
CONFIRM_MIN_SCANS = 3
CONFIRM_MIN_CONFIDENCE = 0.45
# 약화 판단: peak 대비 이 비율 미만이면 약화
WEAKENING_THRESHOLD = 0.8
# WEAKENING 상태에서 이 횟수 이상 지속 시 만료
WEAKENING_MAX_SCANS = 3


class SignalTracker:
    """시그널 라이프사이클 상태 머신"""

    def __init__(self, track_repo: SignalTrackRepo):
        self.repo = track_repo

    async def process_scan_result(
        self,
        symbol: str,
        timeframe: str,
        signal: str,
        confidence: float,
        price: float,
    ) -> list[dict]:
        """
        스캔 결과를 상태 머신에 통과시키고, 발생한 전환 목록 반환.
        """
        direction = self._normalize_direction(signal)
        transitions: list[dict] = []

        active_track = await self.repo.get_active_track(symbol, timeframe)

        # 활성 트랙 없음
        if active_track is None:
            if direction is not None:
                track_id = await self.repo.create_track(
                    symbol, timeframe, direction, signal, confidence, price
                )
                transitions.append({
                    "track_id": track_id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "from_state": None,
                    "to_state": "FORMING",
                    "direction": direction,
                    "confidence": confidence,
                    "current_price": price,
                })
            return transitions

        # 활성 트랙 존재 → 상태 머신 실행
        same_dir = direction == active_track["direction"]
        new_state = self._compute_transition(active_track, direction, confidence)

        if new_state != active_track["state"]:
            # 상태 전환 발생
            await self.repo.transition_track(
                active_track["id"], new_state, signal or active_track["current_signal"],
                confidence, price
            )
            transition = {
                "track_id": active_track["id"],
                "symbol": symbol,
                "timeframe": timeframe,
                "from_state": active_track["state"],
                "to_state": new_state,
                "direction": active_track["direction"],
                "confidence": confidence,
                "current_price": price,
            }
            transitions.append(transition)
            logger.info(
                "[%s] %s → %s (conf=%.2f, scans=%d)",
                symbol, active_track["state"], new_state,
                confidence, active_track["consecutive_scans"],
            )
        elif same_dir and new_state not in ("EXPIRED",):
            # 상태 동일, 통계만 업데이트
            await self.repo.update_track_stats(
                active_track["id"], signal, confidence, price
            )

        # EXPIRED 후 새 방향이 있으면 새 FORMING 시작
        if new_state == "EXPIRED" and direction is not None:
            track_id = await self.repo.create_track(
                symbol, timeframe, direction, signal, confidence, price
            )
            transitions.append({
                "track_id": track_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "from_state": None,
                "to_state": "FORMING",
                "direction": direction,
                "confidence": confidence,
                "current_price": price,
            })

        return transitions

    def _normalize_direction(self, signal: str) -> str | None:
        """시그널을 방향으로 정규화"""
        if signal in ("STRONG_LONG", "LONG"):
            return "LONG"
        if signal in ("STRONG_SHORT", "SHORT"):
            return "SHORT"
        return None

    def _compute_transition(
        self, track: dict, direction: str | None, confidence: float
    ) -> str:
        """순수 함수: 현재 상태 + 스캔 결과 → 다음 상태"""
        state = track["state"]
        same_dir = direction == track["direction"]
        scans = track["consecutive_scans"]
        peak = track["peak_confidence"]

        if state == "FORMING":
            if same_dir:
                return "CONFIRMING"
            return "EXPIRED"

        elif state == "CONFIRMING":
            if same_dir:
                if scans + 1 >= CONFIRM_MIN_SCANS and confidence >= CONFIRM_MIN_CONFIDENCE:
                    return "CONFIRMED"
                return "CONFIRMING"
            return "EXPIRED"

        elif state == "CONFIRMED":
            if same_dir and confidence >= peak * WEAKENING_THRESHOLD:
                return "CONFIRMED"
            # 약화: 같은 방향이지만 신뢰도 하락 or 방향 전환/중립
            return "WEAKENING"

        elif state == "WEAKENING":
            if same_dir and confidence >= peak * WEAKENING_THRESHOLD:
                return "CONFIRMED"  # 재확정
            weak_count = track.get("weak_scans", 0) + 1
            if weak_count >= WEAKENING_MAX_SCANS:
                return "EXPIRED"
            return "WEAKENING"

        return state

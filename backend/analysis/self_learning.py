"""
자기학습 엔진 v2 - 과거 시그널/예측 결과를 분석하여 지표별 정확도 계산 및 가중치 자동 조정

v2 개선:
- 시간 감쇠 가중치: 최근 예측일수록 더 높은 가중치 (반감기 30일)
- 레짐별 정확도 추적: TRENDING_UP/DOWN, RANGING, VOLATILE별 분리 통계
- 결과 등급별 점수: HIT_TP3=1.0, HIT_TP2=0.8, HIT_TP1=0.6, PARTIAL=0.4

흐름:
1. VERIFIED 예측과 가장 가까운 시그널을 매칭
2. 각 지표가 올바른 방향을 가리켰는지 채점 (시간 감쇠 + 레짐별)
3. 지표별/카테고리별 정확도 계산
4. 정확도 기반 적응형 가중치 생성
"""
import logging
import math
from datetime import datetime, timezone
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# 기본 가중치 (signal_engine.py와 동일)
DEFAULT_WEIGHTS = {
    "indicators": 0.30,
    "candle_patterns": 0.12,
    "chart_patterns": 0.25,
    "volume": 0.15,
    "futures_data": 0.18,
}

# 최소 샘플 수: 이 이상 모여야 학습 시작
MIN_SAMPLES = 10

# 대용량 데이터 활용: 제한 확대
MAX_PREDICTIONS = 5000
MAX_SIGNALS = 20000

# 시간 감쇠 반감기 (일)
TIME_DECAY_HALF_LIFE_DAYS = 30

# 성공 결과 분류 및 점수
SUCCESS_RESULTS = {"HIT_TP1", "HIT_TP2", "HIT_TP3", "PARTIAL"}
FAILURE_RESULTS = {"HIT_SL", "WRONG"}
RESULT_SCORES = {
    "HIT_TP3": 1.0,
    "HIT_TP2": 0.8,
    "HIT_TP1": 0.6,
    "PARTIAL": 0.4,
    "HIT_SL": 0.0,
    "WRONG": 0.0,
}


class SelfLearningEngine:
    """시그널 정확도 분석 및 가중치 자동 조정"""

    def __init__(self, client: AsyncClient, schema: str = "coin"):
        self._client = client
        self._schema = schema
        self._cached_weights: dict | None = None

    def _table(self, name: str):
        return self._client.schema(self._schema).table(name)

    async def run_learning_cycle(self):
        """
        전체 학습 사이클 실행:
        1. 검증된 예측 수집
        2. 시그널과 매칭
        3. 지표별 정확도 계산
        4. 적응형 가중치 생성 및 저장
        """
        logger.info("[자기학습] 학습 사이클 시작")

        # 1. 검증된 예측 조회
        predictions = await self._get_verified_predictions()
        if len(predictions) < MIN_SAMPLES:
            logger.info("[자기학습] 샘플 부족 (%d/%d), 스킵", len(predictions), MIN_SAMPLES)
            return

        # 2. 시그널 히스토리 조회
        signals = await self._get_recent_signals()
        if not signals:
            logger.info("[자기학습] 시그널 데이터 없음, 스킵")
            return

        # 3. 예측-시그널 매칭 및 채점
        accuracy_data = self._score_indicators(predictions, signals)

        if not accuracy_data:
            logger.info("[자기학습] 채점 결과 없음, 스킵")
            return

        # 4. DB 저장
        await self._save_accuracy(accuracy_data)

        # 5. 적응형 가중치 계산 및 저장
        weights = self._calculate_adaptive_weights(accuracy_data)
        await self._save_weights(weights, len(predictions))

        # 캐시 갱신
        self._cached_weights = weights

        logger.info(
            "[자기학습] 완료 - 샘플: %d, 지표: %d개, 가중치: %s",
            len(predictions),
            len(accuracy_data),
            {k: round(v, 3) for k, v in weights.items()},
        )

    async def get_adaptive_weights(self) -> dict:
        """현재 적응형 가중치 반환. 없으면 기본값."""
        if self._cached_weights:
            return self._cached_weights

        try:
            resp = (
                await self._table("adaptive_weights")
                .select("weights")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if resp.data:
                self._cached_weights = resp.data[0]["weights"]
                return self._cached_weights
        except Exception as e:
            logger.debug("[자기학습] 가중치 로드 실패: %s", e)

        return DEFAULT_WEIGHTS.copy()

    async def get_indicator_stats(self) -> list[dict]:
        """지표별 정확도 통계 반환 (API용)."""
        try:
            resp = (
                await self._table("indicator_accuracy")
                .select("*")
                .order("accuracy", desc=True)
                .execute()
            )
            return resp.data
        except Exception:
            return []

    # ─── 내부 메서드 ──────────────────────────────────────

    async def _get_verified_predictions(self) -> list[dict]:
        """검증 완료된 예측 조회 (대용량 활용)."""
        resp = (
            await self._table("predictions")
            .select("symbol,timeframe,signal_direction,result,regime,created_at")
            .eq("status", "VERIFIED")
            .order("created_at", desc=True)
            .limit(MAX_PREDICTIONS)
            .execute()
        )
        return resp.data

    async def _get_recent_signals(self) -> list[dict]:
        """최근 시그널 조회 (대용량 활용)."""
        resp = (
            await self._table("signals")
            .select("symbol,timeframe,signal,indicators,candle_patterns,chart_patterns,volume_signals,futures_signals,created_at")
            .order("created_at", desc=True)
            .limit(MAX_SIGNALS)
            .execute()
        )
        return resp.data

    def _score_indicators(
        self, predictions: list[dict], signals: list[dict]
    ) -> dict[str, dict]:
        """
        예측과 시그널을 매칭하고 각 지표를 채점.
        시간 감쇠 + 레짐별 분리 추적.

        Returns:
            {indicator_name: {"category": str, "weighted_total": float, "weighted_correct": float,
                              "total": int, "correct": int, "by_regime": dict}}
        """
        sig_index: dict[str, list[dict]] = {}
        for sig in signals:
            key = f"{sig['symbol']}_{sig['timeframe']}"
            sig_index.setdefault(key, []).append(sig)

        accuracy: dict[str, dict] = {}
        matched = 0
        now = datetime.now(timezone.utc)

        for pred in predictions:
            result = pred.get("result")
            if result not in SUCCESS_RESULTS and result not in FAILURE_RESULTS:
                continue

            is_success = result in SUCCESS_RESULTS
            direction = pred["signal_direction"]
            is_long = direction in ("STRONG_LONG", "LONG")
            regime = pred.get("regime", "UNKNOWN") or "UNKNOWN"

            # 시간 감쇠 가중치 계산
            time_weight = self._time_decay_weight(pred.get("created_at"), now)

            # 가장 가까운 시그널 찾기
            key = f"{pred['symbol']}_{pred['timeframe']}"
            candidates = sig_index.get(key, [])
            if not candidates:
                continue

            closest = self._find_closest_signal(pred["created_at"], candidates)
            if not closest:
                continue

            matched += 1

            # 각 카테고리의 지표 채점
            self._score_category(
                accuracy, closest.get("indicators") or [],
                "indicators", is_long, is_success, time_weight, regime
            )
            self._score_category(
                accuracy, closest.get("candle_patterns") or [],
                "candle_patterns", is_long, is_success, time_weight, regime
            )
            self._score_category(
                accuracy, closest.get("chart_patterns") or [],
                "chart_patterns", is_long, is_success, time_weight, regime
            )
            self._score_category(
                accuracy, closest.get("volume_signals") or [],
                "volume", is_long, is_success, time_weight, regime
            )
            self._score_category(
                accuracy, closest.get("futures_signals") or [],
                "futures_data", is_long, is_success, time_weight, regime
            )

        logger.info("[자기학습] %d개 예측 중 %d개 매칭됨", len(predictions), matched)
        return accuracy

    def _time_decay_weight(self, created_at: str | None, now: datetime) -> float:
        """시간 감쇠 가중치 계산 (반감기 30일)."""
        if not created_at:
            return 0.5
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            days_ago = (now - dt).total_seconds() / 86400
            return math.exp(-0.693 * days_ago / TIME_DECAY_HALF_LIFE_DAYS)
        except Exception:
            return 0.5

    def _score_category(
        self,
        accuracy: dict,
        items: list[dict],
        category: str,
        is_long: bool,
        is_success: bool,
        time_weight: float = 1.0,
        regime: str = "UNKNOWN",
    ):
        """개별 카테고리(지표/패턴/거래량) 채점 (시간 감쇠 + 레짐별)."""
        for item in items:
            name = item.get("name", "unknown")
            sig_dir = item.get("signal", "neutral")

            if sig_dir == "neutral":
                continue

            indicator_agrees = (
                (sig_dir == "long" and is_long)
                or (sig_dir == "short" and not is_long)
            )

            key = f"{category}:{name}"
            if key not in accuracy:
                accuracy[key] = {
                    "category": category,
                    "total": 0, "correct": 0,
                    "weighted_total": 0.0, "weighted_correct": 0.0,
                    "by_regime": {},
                }

            accuracy[key]["total"] += 1
            accuracy[key]["weighted_total"] += time_weight

            is_correct = (indicator_agrees and is_success) or (not indicator_agrees and not is_success)
            if is_correct:
                accuracy[key]["correct"] += 1
                accuracy[key]["weighted_correct"] += time_weight

            # 레짐별 추적
            if regime not in accuracy[key]["by_regime"]:
                accuracy[key]["by_regime"][regime] = {"total": 0, "correct": 0}
            accuracy[key]["by_regime"][regime]["total"] += 1
            if is_correct:
                accuracy[key]["by_regime"][regime]["correct"] += 1

    def _find_closest_signal(self, pred_time: str, signals: list[dict]) -> dict | None:
        """예측 생성 시각에 가장 가까운 시그널 반환."""
        try:
            pred_dt = datetime.fromisoformat(pred_time.replace("Z", "+00:00"))
        except Exception:
            return None

        best = None
        best_diff = float("inf")

        for sig in signals:
            try:
                sig_dt = datetime.fromisoformat(sig["created_at"].replace("Z", "+00:00"))
                diff = abs((pred_dt - sig_dt).total_seconds())
                if diff < best_diff:
                    best_diff = diff
                    best = sig
            except Exception:
                continue

        # 10분 이내의 시그널만 매칭
        if best_diff > 600:
            return None

        return best

    def _calculate_adaptive_weights(self, accuracy_data: dict) -> dict:
        """지표 정확도 기반 적응형 가중치 계산 (시간 감쇠 가중 평균)."""
        # 카테고리별 시간 감쇠 가중 정확도 계산
        category_scores: dict[str, list[float]] = {}
        for _, data in accuracy_data.items():
            cat = data["category"]
            if data["total"] >= 3:  # 최소 3회 이상 관측된 지표만
                w_total = data.get("weighted_total", 0)
                w_correct = data.get("weighted_correct", 0)
                acc = w_correct / w_total if w_total > 0 else data["correct"] / data["total"]
                category_scores.setdefault(cat, []).append(acc)

        category_accuracy: dict[str, float] = {}
        for cat in DEFAULT_WEIGHTS:
            scores = category_scores.get(cat, [])
            if scores:
                category_accuracy[cat] = sum(scores) / len(scores)
            else:
                category_accuracy[cat] = 0.5  # 데이터 없으면 중립

        # 가중치 조정: base * (0.5 + accuracy)
        raw_weights = {}
        for cat, base_w in DEFAULT_WEIGHTS.items():
            acc = category_accuracy.get(cat, 0.5)
            raw_weights[cat] = base_w * (0.5 + acc)

        # 정규화 (합 = 1.0)
        total = sum(raw_weights.values())
        if total == 0:
            return DEFAULT_WEIGHTS.copy()

        adaptive = {k: v / total for k, v in raw_weights.items()}

        logger.info(
            "[자기학습] 카테고리 정확도: %s → 가중치: %s",
            {k: round(v, 3) for k, v in category_accuracy.items()},
            {k: round(v, 3) for k, v in adaptive.items()},
        )

        return adaptive

    async def _save_accuracy(self, accuracy_data: dict):
        """지표별 정확도를 DB에 저장 (upsert)."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for key, data in accuracy_data.items():
            parts = key.split(":", 1)
            rows.append({
                "indicator_name": parts[1] if len(parts) > 1 else key,
                "category": data["category"],
                "total_count": data["total"],
                "correct_count": data["correct"],
                "accuracy": round(data["correct"] / data["total"], 4) if data["total"] > 0 else 0.5,
                "last_updated": now,
            })

        if not rows:
            return

        try:
            # 기존 데이터 삭제 후 재삽입 (간단한 전략)
            await self._table("indicator_accuracy").delete().neq("id", 0).execute()
            await self._table("indicator_accuracy").insert(rows).execute()
        except Exception as e:
            logger.error("[자기학습] 정확도 저장 실패: %s", e)

    async def _save_weights(self, weights: dict, sample_count: int):
        """적응형 가중치를 DB에 저장."""
        now = datetime.now(timezone.utc).isoformat()

        try:
            # 최신 1개만 유지
            await self._table("adaptive_weights").delete().neq("id", 0).execute()
            await self._table("adaptive_weights").insert({
                "weights": weights,
                "sample_count": sample_count,
                "created_at": now,
            }).execute()
        except Exception as e:
            logger.error("[자기학습] 가중치 저장 실패: %s", e)

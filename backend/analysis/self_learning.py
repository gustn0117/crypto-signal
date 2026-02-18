"""
자기학습 엔진 - 과거 시그널/예측 결과를 분석하여 지표별 정확도 계산 및 가중치 자동 조정

흐름:
1. VERIFIED 예측과 가장 가까운 시그널을 매칭
2. 각 지표가 올바른 방향을 가리켰는지 채점
3. 지표별/카테고리별 정확도 계산
4. 정확도 기반 적응형 가중치 생성
"""
import logging
from datetime import datetime, timezone
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# 기본 가중치
DEFAULT_WEIGHTS = {
    "indicators": 0.35,
    "candle_patterns": 0.15,
    "chart_patterns": 0.30,
    "volume": 0.20,
}

# 최소 샘플 수: 이 이상 모여야 학습 시작
MIN_SAMPLES = 10

# 성공 결과 분류
SUCCESS_RESULTS = {"HIT_TP1", "HIT_TP2", "HIT_TP3", "PARTIAL"}
FAILURE_RESULTS = {"HIT_SL", "WRONG"}


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
        """검증 완료된 예측 조회."""
        resp = (
            await self._table("predictions")
            .select("symbol,timeframe,signal_direction,result,created_at")
            .eq("status", "VERIFIED")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        return resp.data

    async def _get_recent_signals(self) -> list[dict]:
        """최근 시그널 조회."""
        resp = (
            await self._table("signals")
            .select("symbol,timeframe,signal,indicators,candle_patterns,chart_patterns,volume_signals,created_at")
            .order("created_at", desc=True)
            .limit(5000)
            .execute()
        )
        return resp.data

    def _score_indicators(
        self, predictions: list[dict], signals: list[dict]
    ) -> dict[str, dict]:
        """
        예측과 시그널을 매칭하고 각 지표를 채점.

        Returns:
            {indicator_name: {"category": str, "total": int, "correct": int}}
        """
        # 시그널을 symbol+timeframe+created_at 기준 인덱스
        sig_index: dict[str, list[dict]] = {}
        for sig in signals:
            key = f"{sig['symbol']}_{sig['timeframe']}"
            sig_index.setdefault(key, []).append(sig)

        accuracy: dict[str, dict] = {}
        matched = 0

        for pred in predictions:
            result = pred.get("result")
            if result not in SUCCESS_RESULTS and result not in FAILURE_RESULTS:
                continue

            is_success = result in SUCCESS_RESULTS
            direction = pred["signal_direction"]
            is_long = direction in ("STRONG_LONG", "LONG")

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
                "indicators", is_long, is_success
            )
            self._score_category(
                accuracy, closest.get("candle_patterns") or [],
                "candle_patterns", is_long, is_success
            )
            self._score_category(
                accuracy, closest.get("chart_patterns") or [],
                "chart_patterns", is_long, is_success
            )
            self._score_category(
                accuracy, closest.get("volume_signals") or [],
                "volume", is_long, is_success
            )

        logger.info("[자기학습] %d개 예측 중 %d개 매칭됨", len(predictions), matched)
        return accuracy

    def _score_category(
        self,
        accuracy: dict,
        items: list[dict],
        category: str,
        is_long: bool,
        is_success: bool,
    ):
        """개별 카테고리(지표/패턴/거래량) 채점."""
        for item in items:
            name = item.get("name", "unknown")
            sig_dir = item.get("signal", "neutral")

            if sig_dir == "neutral":
                continue  # 중립은 채점 제외

            # 지표가 예측 방향과 같은지 판단
            indicator_agrees = (
                (sig_dir == "long" and is_long)
                or (sig_dir == "short" and not is_long)
            )

            key = f"{category}:{name}"
            if key not in accuracy:
                accuracy[key] = {"category": category, "total": 0, "correct": 0}

            accuracy[key]["total"] += 1

            # 지표가 방향과 일치 + 성공 → 정답
            # 지표가 방향과 불일치 + 실패 → 정답 (경고가 맞았음)
            if (indicator_agrees and is_success) or (not indicator_agrees and not is_success):
                accuracy[key]["correct"] += 1

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
        """지표 정확도 기반 적응형 가중치 계산."""
        # 카테고리별 평균 정확도 계산
        category_scores: dict[str, list[float]] = {}
        for key, data in accuracy_data.items():
            cat = data["category"]
            if data["total"] >= 3:  # 최소 3회 이상 관측된 지표만
                acc = data["correct"] / data["total"]
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

"""
백테스트 엔진
과거 시그널과 캔들 데이터를 활용하여 시그널 유형별 역대 성과를 자동 검증.
- 시그널 유형/신뢰도/레짐별 승률 통계
- 고급 통계: Sharpe/Sortino Ratio, Max Drawdown, Profit Factor
- 프론트엔드에서 "과거 유사 시그널 승률 73%" 같은 정보 표시 가능
"""
import logging
import math
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 백테스트 결과 캐시 (6시간마다 갱신)
_backtest_cache: dict = {"stats": None, "updated_at": None}
BACKTEST_CACHE_TTL = 21600  # 6시간


class BacktestEngine:
    """과거 시그널 성과 자동 검증"""

    def __init__(self, client, schema: str = "coin"):
        self._client = client
        self._schema = schema

    def _table(self, name: str):
        return self._client.schema(self._schema).table(name)

    async def run_backtest(self) -> dict:
        """
        전체 백테스트 실행:
        1. 검증된 예측 전체 조회
        2. 시그널 유형/신뢰도 구간/타임프레임/레짐별 통계 계산
        3. 캐시 저장
        """
        now = datetime.now(timezone.utc)
        if (
            _backtest_cache["stats"]
            and _backtest_cache["updated_at"]
            and (now - _backtest_cache["updated_at"]).total_seconds() < BACKTEST_CACHE_TTL
        ):
            return _backtest_cache["stats"]

        logger.info("[백테스트] 분석 시작")

        try:
            # 전체 검증된 예측 조회 (제한 없음 - 대용량 활용)
            # C5: actual_pnl_pct 필드 추가 (실제 PnL 기반 통계)
            resp = (
                await self._table("predictions")
                .select("symbol,timeframe,signal_direction,confidence,result,regime,created_at,progress_pnl_pct,entry_price,atr")
                .eq("status", "VERIFIED")
                .order("created_at", desc=True)
                .limit(10000)
                .execute()
            )
            predictions = resp.data or []

            if len(predictions) < 10:
                logger.info("[백테스트] 검증 데이터 부족 (%d개), 스킵", len(predictions))
                return {}

            stats = self._compute_stats(predictions)
            _backtest_cache["stats"] = stats
            _backtest_cache["updated_at"] = now

            logger.info(
                "[백테스트] 완료 - %d개 예측 분석, %d개 카테고리",
                len(predictions), len(stats.get("by_signal", {})),
            )
            return stats

        except Exception as e:
            logger.error("[백테스트] 실행 실패: %s", e)
            return _backtest_cache.get("stats") or {}

    def _compute_stats(self, predictions: list[dict]) -> dict:
        """통계 계산"""
        success_results = {"HIT_TP1", "HIT_TP2", "HIT_TP3", "PARTIAL"}

        # 전체 통계
        total = len(predictions)
        wins = sum(1 for p in predictions if p.get("result") in success_results)
        overall_win_rate = round(wins / total, 4) if total > 0 else 0

        # 시그널 유형별 통계
        by_signal = {}
        for p in predictions:
            sig = p.get("signal_direction", "UNKNOWN")
            if sig not in by_signal:
                by_signal[sig] = {"total": 0, "wins": 0, "results": {}}
            by_signal[sig]["total"] += 1
            result = p.get("result", "UNKNOWN")
            by_signal[sig]["results"][result] = by_signal[sig]["results"].get(result, 0) + 1
            if result in success_results:
                by_signal[sig]["wins"] += 1

        for sig, data in by_signal.items():
            data["win_rate"] = round(data["wins"] / data["total"], 4) if data["total"] > 0 else 0

        # 신뢰도 구간별 통계
        confidence_buckets = {
            "0.0-0.3": {"min": 0.0, "max": 0.3, "total": 0, "wins": 0},
            "0.3-0.5": {"min": 0.3, "max": 0.5, "total": 0, "wins": 0},
            "0.5-0.7": {"min": 0.5, "max": 0.7, "total": 0, "wins": 0},
            "0.7-1.0": {"min": 0.7, "max": 1.0, "total": 0, "wins": 0},
        }
        for p in predictions:
            conf = p.get("confidence", 0)
            result = p.get("result", "")
            for bucket_name, bucket in confidence_buckets.items():
                if bucket["min"] <= conf < bucket["max"] or (bucket["max"] == 1.0 and conf == 1.0):
                    bucket["total"] += 1
                    if result in success_results:
                        bucket["wins"] += 1
                    break

        by_confidence = {}
        for name, bucket in confidence_buckets.items():
            by_confidence[name] = {
                "total": bucket["total"],
                "wins": bucket["wins"],
                "win_rate": round(bucket["wins"] / bucket["total"], 4) if bucket["total"] > 0 else 0,
            }

        # 타임프레임별 통계
        by_timeframe = {}
        for p in predictions:
            tf = p.get("timeframe", "unknown")
            if tf not in by_timeframe:
                by_timeframe[tf] = {"total": 0, "wins": 0}
            by_timeframe[tf]["total"] += 1
            if p.get("result") in success_results:
                by_timeframe[tf]["wins"] += 1

        for tf, data in by_timeframe.items():
            data["win_rate"] = round(data["wins"] / data["total"], 4) if data["total"] > 0 else 0

        # 레짐별 통계
        by_regime = {}
        for p in predictions:
            regime = p.get("regime", "UNKNOWN") or "UNKNOWN"
            if regime not in by_regime:
                by_regime[regime] = {"total": 0, "wins": 0}
            by_regime[regime]["total"] += 1
            if p.get("result") in success_results:
                by_regime[regime]["wins"] += 1

        for regime, data in by_regime.items():
            data["win_rate"] = round(data["wins"] / data["total"], 4) if data["total"] > 0 else 0

        # 심볼별 승률 (Top 10)
        by_symbol = {}
        for p in predictions:
            sym = p.get("symbol", "")
            if sym not in by_symbol:
                by_symbol[sym] = {"total": 0, "wins": 0}
            by_symbol[sym]["total"] += 1
            if p.get("result") in success_results:
                by_symbol[sym]["wins"] += 1

        for sym, data in by_symbol.items():
            data["win_rate"] = round(data["wins"] / data["total"], 4) if data["total"] > 0 else 0

        symbol_leaderboard = sorted(
            [{"symbol": k, **v} for k, v in by_symbol.items() if v["total"] >= 3],
            key=lambda x: x["win_rate"],
            reverse=True,
        )[:15]

        # 고급 통계 계산
        advanced = self._compute_advanced_stats(predictions)

        return {
            "total_predictions": total,
            "overall_win_rate": overall_win_rate,
            "by_signal": by_signal,
            "by_confidence": by_confidence,
            "by_timeframe": by_timeframe,
            "by_regime": by_regime,
            "symbol_leaderboard": symbol_leaderboard,
            "advanced_stats": advanced,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _compute_advanced_stats(self, predictions: list[dict]) -> dict:
        """고급 통계: Sharpe, Sortino, Max Drawdown, Profit Factor, 평균 보유 시간, 수익 곡선"""
        if not predictions:
            return {}

        # C5: 실제 PnL 우선 사용, 없으면 result 기반 추정치 폴백
        result_pnl_map = {
            "HIT_TP3": 0.06, "HIT_TP2": 0.04, "HIT_TP1": 0.02,
            "PARTIAL": 0.005, "WRONG": -0.015, "HIT_SL": -0.02,
        }
        pnl_list = []
        actual_count = 0
        for p in predictions:
            actual_pnl = p.get("progress_pnl_pct")
            if actual_pnl is not None and actual_pnl != 0:
                pnl_list.append(actual_pnl / 100.0)  # % → 소수
                actual_count += 1
            else:
                result = p.get("result", "WRONG")
                pnl_list.append(result_pnl_map.get(result, 0.0))

        if not pnl_list:
            return {}

        # Sharpe Ratio (일간 수익률 가정, risk-free = 0)
        mean_return = sum(pnl_list) / len(pnl_list)
        variance = sum((r - mean_return) ** 2 for r in pnl_list) / len(pnl_list)
        std_return = math.sqrt(variance) if variance > 0 else 0.001
        sharpe_ratio = round(mean_return / std_return, 4) if std_return > 0 else 0.0

        # Sortino Ratio (하방 편차만 사용)
        downside = [r for r in pnl_list if r < 0]
        if downside:
            downside_var = sum(r ** 2 for r in downside) / len(pnl_list)
            downside_std = math.sqrt(downside_var)
            sortino_ratio = round(mean_return / downside_std, 4) if downside_std > 0 else 0.0
        else:
            sortino_ratio = round(sharpe_ratio * 1.5, 4)

        # Profit Factor (총이익 / 총손실)
        total_profit = sum(r for r in pnl_list if r > 0)
        total_loss = abs(sum(r for r in pnl_list if r < 0))
        profit_factor = round(total_profit / total_loss, 4) if total_loss > 0 else 99.0

        # Max Drawdown (누적 수익 곡선 기반)
        cumulative = []
        running = 0.0
        for r in pnl_list:
            running += r
            cumulative.append(running)

        peak = cumulative[0]
        max_drawdown = 0.0
        for val in cumulative:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_drawdown:
                max_drawdown = dd
        max_drawdown_pct = round(max_drawdown * 100, 2)

        # 평균 보유 시간 (created_at이 있는 경우)
        hold_times = []
        for p in predictions:
            created = p.get("created_at")
            if not created:
                continue
            # verified_at 대신 result 기반 시간 추정 (실제 데이터 한계)
            tf = p.get("timeframe", "1h")
            tf_hours = {"1m": 1, "5m": 3, "15m": 6, "1h": 24, "4h": 48, "1d": 168}
            hold_times.append(tf_hours.get(tf, 24))
        avg_hold_hours = round(sum(hold_times) / len(hold_times), 1) if hold_times else 0

        # 수익 곡선 (최근 100개 포인트)
        equity_curve = []
        step = max(1, len(cumulative) // 100)
        for i in range(0, len(cumulative), step):
            equity_curve.append(round(cumulative[i] * 100, 2))

        # 연속 승/패
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_streak = 0
        for r in pnl_list:
            if r > 0:
                current_streak = current_streak + 1 if current_streak > 0 else 1
                max_consecutive_wins = max(max_consecutive_wins, current_streak)
            elif r < 0:
                current_streak = current_streak - 1 if current_streak < 0 else -1
                max_consecutive_losses = max(max_consecutive_losses, abs(current_streak))
            else:
                current_streak = 0

        return {
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_drawdown_pct,
            "avg_hold_hours": avg_hold_hours,
            "total_return_pct": round(sum(pnl_list) * 100, 2),
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "equity_curve": equity_curve[-100:],
            # C5: 실제 PnL 커버리지 정보
            "actual_pnl_count": actual_count,
            "actual_pnl_coverage": round(actual_count / len(pnl_list), 4) if pnl_list else 0,
        }

    def get_signal_win_rate(self, signal_direction: str, confidence: float = 0.0) -> Optional[dict]:
        """
        특정 시그널 유형의 역대 승률 반환.
        프론트엔드에서 "과거 유사 시그널 승률" 표시용.
        """
        stats = _backtest_cache.get("stats")
        if not stats:
            return None

        signal_stats = stats.get("by_signal", {}).get(signal_direction)
        if not signal_stats or signal_stats["total"] < 3:
            return None

        # 신뢰도 구간 매칭
        conf_label = "0.7-1.0"
        if confidence < 0.3:
            conf_label = "0.0-0.3"
        elif confidence < 0.5:
            conf_label = "0.3-0.5"
        elif confidence < 0.7:
            conf_label = "0.5-0.7"

        conf_stats = stats.get("by_confidence", {}).get(conf_label)

        return {
            "signal_win_rate": signal_stats["win_rate"],
            "signal_total": signal_stats["total"],
            "confidence_win_rate": conf_stats["win_rate"] if conf_stats and conf_stats["total"] >= 3 else None,
            "confidence_total": conf_stats["total"] if conf_stats else 0,
        }

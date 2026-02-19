"""
시그널 엔진 - 모든 분석 결과를 종합하여 최종 롱/숏 시그널 생성
(12개 기술 지표 + 캔들 패턴 + 차트 패턴 + 거래량 + 선물 데이터 + 시장 맥락)
"""
import logging
import math
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone

from .indicators import (
    analyze_rsi,
    analyze_macd,
    analyze_bollinger_bands,
    analyze_ema_cross,
    analyze_stochastic,
    analyze_adx,
    analyze_vwap,
    analyze_ichimoku,
    analyze_williams_r,
    analyze_cci,
    analyze_mfi,
    analyze_cmf,
    analyze_ma_cross_50_200,
    analyze_eom,
    analyze_kvo,
    analyze_vortex,
    IndicatorResult,
    TF_CATEGORY,
)
from .candle_patterns import analyze_candle_patterns, CandlePatternResult
from .chart_patterns import analyze_chart_patterns, ChartPatternResult
from .volume import analyze_volume, VolumeResult
from .levels import calculate_levels, PriceLevels
from .trade_params import calculate_trade_params, TradeParams
from .mtf import check_higher_tf, check_multi_tf, MTFConfirmation, SECOND_HIGHER_TF_MAP
from .regime import detect_regime
import pandas_ta as ta

logger = logging.getLogger(__name__)


def _sanitize(obj):
    """NaN/Infinity/numpy 타입을 JSON 안전 값으로 변환 (재귀)"""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    # numpy ndarray → Python list
    if hasattr(obj, "tolist") and hasattr(obj, "ndim"):
        return _sanitize(obj.tolist())
    # numpy scalar → Python native
    if hasattr(obj, "item"):
        obj = obj.item()
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    if isinstance(obj, (int, bool, str)) or obj is None:
        return obj
    # 알 수 없는 타입 → str 변환
    try:
        return float(obj)
    except (TypeError, ValueError):
        return str(obj)


@dataclass
class FuturesResult:
    """선물 데이터 분석 결과"""
    name: str
    signal: str
    strength: float
    value: float
    description: str


@dataclass
class TradeSignal:
    """최종 트레이드 시그널"""
    symbol: str
    timeframe: str
    signal: str  # "STRONG_LONG", "LONG", "NEUTRAL", "SHORT", "STRONG_SHORT"
    confidence: float  # 0.0 ~ 1.0 (신뢰도)
    current_price: float
    indicators: List[dict] = field(default_factory=list)
    candle_patterns: List[dict] = field(default_factory=list)
    chart_patterns: List[dict] = field(default_factory=list)
    volume_signals: List[dict] = field(default_factory=list)
    futures_signals: List[dict] = field(default_factory=list)
    summary: str = ""
    timestamp: str = ""
    trade_params: Optional[dict] = None
    mtf_confirmation: Optional[dict] = None
    price_levels: Optional[dict] = None
    indicator_snapshot: Optional[dict] = None

    def to_dict(self) -> dict:
        return _sanitize(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "signal": self.signal,
                "confidence": round(self.confidence, 3),
                "current_price": self.current_price,
                "indicators": self.indicators,
                "candle_patterns": self.candle_patterns,
                "chart_patterns": self.chart_patterns,
                "volume_signals": self.volume_signals,
                "futures_signals": self.futures_signals,
                "summary": self.summary,
                "timestamp": self.timestamp,
                "trade_params": self.trade_params,
                "mtf_confirmation": self.mtf_confirmation,
                "price_levels": self.price_levels,
                "indicator_snapshot": self.indicator_snapshot,
            }
        )


class SignalEngine:
    """
    복합 전략 시그널 엔진
    12개 기술 지표 + 캔들 패턴 + 차트 패턴 + 거래량 + 선물 데이터를 종합
    """

    DEFAULT_WEIGHTS = {
        "indicators": 0.30,
        "candle_patterns": 0.12,
        "chart_patterns": 0.25,
        "volume": 0.15,
        "futures_data": 0.18,
    }

    # 레짐별 카테고리 가중치 배율
    REGIME_WEIGHT_MODIFIERS = {
        "TRENDING_UP":   {"indicators": 1.3, "candle_patterns": 0.7, "chart_patterns": 1.1, "volume": 0.9, "futures_data": 1.0},
        "TRENDING_DOWN": {"indicators": 1.3, "candle_patterns": 0.7, "chart_patterns": 1.1, "volume": 0.9, "futures_data": 1.0},
        "RANGING":       {"indicators": 0.8, "candle_patterns": 1.3, "chart_patterns": 1.0, "volume": 1.3, "futures_data": 1.1},
        "VOLATILE":      {"indicators": 0.9, "candle_patterns": 0.8, "chart_patterns": 0.8, "volume": 1.2, "futures_data": 1.4},
    }

    def __init__(self):
        self._adaptive_weights: dict | None = None
        self._market_context: dict | None = None

    def set_adaptive_weights(self, weights: dict | None):
        """자기학습 엔진에서 계산된 적응형 가중치를 설정."""
        self._adaptive_weights = weights
        if weights:
            logger.info("적응형 가중치 적용: %s", {k: round(v, 3) for k, v in weights.items()})

    def set_market_context(self, context: dict | None):
        """시장 맥락 데이터 설정 (BTC 도미넌스, 공포탐욕지수 등)."""
        self._market_context = context

    @property
    def weights(self) -> dict:
        return self._adaptive_weights or self.DEFAULT_WEIGHTS

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        higher_tf_df: Optional[pd.DataFrame] = None,
        futures_data: Optional[List] = None,
        higher_tf_dfs: Optional[dict] = None,
    ) -> TradeSignal:
        """종합 분석 수행 후 TradeSignal 반환"""
        current_price = df["close"].iloc[-1]

        # 1) 기술적 지표 분석 (16개 — 타임프레임별 파라미터 적용)
        indicator_results: List[IndicatorResult] = [
            analyze_rsi(df, timeframe=timeframe),
            analyze_macd(df, timeframe=timeframe),
            analyze_bollinger_bands(df, timeframe=timeframe),
            analyze_ema_cross(df, timeframe=timeframe),
            analyze_stochastic(df, timeframe=timeframe),
            analyze_adx(df, timeframe=timeframe),
            analyze_vwap(df),
            analyze_ichimoku(df),
            analyze_williams_r(df, timeframe=timeframe),
            analyze_cci(df, timeframe=timeframe),
            analyze_mfi(df, timeframe=timeframe),
            analyze_cmf(df, timeframe=timeframe),
            analyze_ma_cross_50_200(df),
            analyze_eom(df, timeframe=timeframe),
            analyze_kvo(df, timeframe=timeframe),
            analyze_vortex(df, timeframe=timeframe),
        ]

        # 2) 캔들 패턴 분석
        candle_results: List[CandlePatternResult] = analyze_candle_patterns(df)

        # 3) 차트 패턴 분석
        chart_results: List[ChartPatternResult] = analyze_chart_patterns(df)

        # 4) 거래량 분석
        volume_results: List[VolumeResult] = analyze_volume(df)

        # 5) 선물 데이터 (외부에서 전달)
        futures_results = futures_data or []

        # 6) 점수 계산
        indicator_score = self._calc_category_score(
            [(r.signal, r.strength) for r in indicator_results]
        )
        candle_score = self._calc_category_score(
            [(r.signal, r.strength) for r in candle_results]
        ) if candle_results else 0.0
        chart_score = self._calc_category_score(
            [(r.signal, r.strength) for r in chart_results]
        ) if chart_results else 0.0
        volume_score = self._calc_category_score(
            [(r.signal, r.strength) for r in volume_results]
        ) if volume_results else 0.0
        futures_score = self._calc_category_score(
            [(r.signal, r.strength) for r in futures_results]
        ) if futures_results else 0.0

        # 7) 레짐 감지 + 가중 합산
        regime = detect_regime(df)
        w = self._get_regime_adjusted_weights(regime.regime)
        total_score = (
            indicator_score * w.get("indicators", 0.30)
            + candle_score * w.get("candle_patterns", 0.12)
            + chart_score * w.get("chart_patterns", 0.25)
            + volume_score * w.get("volume", 0.15)
            + futures_score * w.get("futures_data", 0.18)
        )
        logger.debug("레짐=%s 가중치=%s", regime.regime, {k: round(v, 3) for k, v in w.items()})

        # 8) 시그널 결정 (레짐별 동적 임계값 적용)
        signal, confidence = self._determine_signal(total_score, regime=regime.regime)

        # 8.5) 지표 합류(Confluence) 보너스
        confluence_bonus = self._detect_confluence(indicator_results)
        if confluence_bonus != 0.0:
            confidence = max(0.0, min(1.0, confidence + confluence_bonus))

        # 8.6) 스캘프 TF 거래량 필터 (저거래량 시 신뢰도 감소)
        confidence = self._scalp_volume_filter(df, timeframe, confidence)

        # 9) 시장 맥락 보정 (BTC 도미넌스, Fear & Greed 등)
        if self._market_context and symbol != "BTC/USDT":
            confidence = self._apply_market_context(signal, confidence)

        # 10) 가격 레벨 계산
        levels = calculate_levels(df)

        # 11) 멀티 타임프레임 확인 (2단계 상위 TF)
        mtf_result: Optional[MTFConfirmation] = None
        from config import HIGHER_TF_MAP
        htf1_name = HIGHER_TF_MAP.get(timeframe, timeframe)
        htf2_name = SECOND_HIGHER_TF_MAP.get(timeframe, timeframe)

        # higher_tf_dfs 딕셔너리 우선, 없으면 기존 higher_tf_df 사용
        htf1_df = (higher_tf_dfs or {}).get(htf1_name, higher_tf_df)
        htf2_df = (higher_tf_dfs or {}).get(htf2_name)

        if htf1_df is not None and len(htf1_df) >= 50:
            if htf2_df is not None and len(htf2_df) >= 50 and htf1_name != htf2_name:
                mtf_result = check_multi_tf(htf1_df, htf2_df, signal, htf1_name, htf2_name)
            else:
                mtf_result = check_higher_tf(htf1_df, signal, htf1_name)
            if mtf_result:
                confidence = max(0.0, min(1.0, confidence + mtf_result.confidence_modifier))

        # 12) 트레이드 파라미터 계산
        trade_params_result: Optional[TradeParams] = None
        if signal != "NEUTRAL":
            trade_params_result = calculate_trade_params(df, signal, levels, timeframe=timeframe, confidence=confidence)

        # 13) 지표 스냅샷 생성
        indicator_snapshot = self._build_indicator_snapshot(df, timeframe)

        # 14) 요약 생성
        summary = self._generate_summary(
            signal, confidence, indicator_results, candle_results,
            chart_results, volume_results, futures_results, mtf_result, trade_params_result
        )

        return TradeSignal(
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            current_price=current_price,
            indicators=[
                {"name": r.name, "signal": r.signal, "strength": round(r.strength, 2),
                 "value": round(r.value, 4), "description": r.description}
                for r in indicator_results
            ],
            candle_patterns=[
                {"name": r.name, "signal": r.signal, "strength": round(r.strength, 2),
                 "description": r.description}
                for r in candle_results
            ],
            chart_patterns=[
                {"name": r.name, "signal": r.signal, "strength": round(r.strength, 2),
                 "description": r.description}
                for r in chart_results
            ],
            volume_signals=[
                {"name": r.name, "signal": r.signal, "strength": round(r.strength, 2),
                 "value": round(r.value, 4), "description": r.description}
                for r in volume_results
            ],
            futures_signals=[
                {"name": r.name, "signal": r.signal, "strength": round(r.strength, 2),
                 "value": round(r.value, 4), "description": r.description}
                for r in futures_results
            ],
            summary=summary,
            timestamp=datetime.now(timezone.utc).isoformat(),
            trade_params=trade_params_result.to_dict() if trade_params_result else None,
            mtf_confirmation=mtf_result.to_dict() if mtf_result else None,
            price_levels=levels.to_dict(),
            indicator_snapshot=indicator_snapshot,
        )

    def _apply_market_context(self, signal: str, confidence: float) -> float:
        """시장 맥락 보정 (알트코인에만 적용)"""
        ctx = self._market_context
        if not ctx:
            return confidence

        modifier = 0.0

        # Fear & Greed 보정
        fg = ctx.get("fear_greed")
        if fg is not None:
            if fg <= 20:  # Extreme Fear → 롱 편향
                if "LONG" in signal:
                    modifier += 0.05
                elif "SHORT" in signal:
                    modifier -= 0.03
            elif fg >= 80:  # Extreme Greed → 숏 편향
                if "SHORT" in signal:
                    modifier += 0.05
                elif "LONG" in signal:
                    modifier -= 0.03

        # 시장 모멘텀 보정
        momentum = ctx.get("market_momentum")
        if momentum is not None:
            if momentum >= 0.8:  # 과열 → 숏 편향
                if "SHORT" in signal:
                    modifier += 0.03
            elif momentum <= 0.2:  # 과매도 → 롱 편향
                if "LONG" in signal:
                    modifier += 0.03

        return max(0.0, min(1.0, confidence + modifier))

    def _build_indicator_snapshot(self, df: pd.DataFrame, timeframe: str = "1h") -> dict:
        """예측 엔진에 전달할 지표 스냅샷 생성."""
        from .indicators import get_params
        p = get_params(timeframe)

        snapshot: dict = {}
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        try:
            rsi = ta.rsi(close, length=p["rsi_period"])
            if rsi is not None and not rsi.empty:
                snapshot["rsi"] = round(float(rsi.dropna().iloc[-1]), 2)

            macd_df = ta.macd(close, fast=p["macd_fast"], slow=p["macd_slow"], signal=p["macd_signal"])
            if macd_df is not None and not macd_df.empty:
                hist_col = [c for c in macd_df.columns if "MACDh" in c or "Histogram" in c.replace("_", "")]
                if not hist_col:
                    hist_col = [c for c in macd_df.columns if "h_" in c]
                if hist_col:
                    hist = macd_df[hist_col[0]].dropna()
                    if len(hist) >= 4:
                        slope = (float(hist.iloc[-1]) - float(hist.iloc[-3])) / 2
                        snapshot["macd_hist_slope"] = round(slope, 6)

            bbands = ta.bbands(close, length=p["bb_period"], std=p["bb_std"])
            if bbands is not None and not bbands.empty:
                upper_col = [c for c in bbands.columns if "BBU" in c]
                lower_col = [c for c in bbands.columns if "BBL" in c]
                if upper_col and lower_col:
                    bbu = float(bbands[upper_col[0]].dropna().iloc[-1])
                    bbl = float(bbands[lower_col[0]].dropna().iloc[-1])
                    if bbu != bbl:
                        bb_pos = (float(close.iloc[-1]) - bbl) / (bbu - bbl)
                        snapshot["bb_position"] = round(max(0.0, min(1.0, bb_pos)), 3)

            vol_ma = volume.rolling(20, min_periods=10).mean()
            if vol_ma is not None and not vol_ma.empty:
                avg_vol = float(vol_ma.dropna().iloc[-1])
                if avg_vol > 0:
                    snapshot["volume_ratio"] = round(float(volume.iloc[-1]) / avg_vol, 3)

            atr = ta.atr(high, low, close, length=14)
            if atr is not None and not atr.empty:
                snapshot["atr"] = round(float(atr.dropna().iloc[-1]), 6)

        except Exception as e:
            logger.warning("indicator_snapshot 생성 실패: %s", e)

        return snapshot

    def _get_regime_adjusted_weights(self, regime: str) -> dict:
        """레짐에 따라 카테고리 가중치를 조정 (정규화 포함)."""
        base = self.weights
        modifiers = self.REGIME_WEIGHT_MODIFIERS.get(regime)
        if not modifiers:
            return base  # UNKNOWN 등 → 기본 가중치

        adjusted = {k: base.get(k, 0) * modifiers.get(k, 1.0) for k in base}
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}
        return adjusted

    def _detect_confluence(self, indicator_results: List[IndicatorResult]) -> float:
        """
        지표 합류(Confluence) 감지 — 확장 버전.
        여러 지표 조합이 같은 방향을 가리킬 때 신뢰도 보너스.
        최대 +0.15.
        """
        bonus = 0.0
        by_name = {r.name: r for r in indicator_results}

        # 1) 핵심 3지표 합류: RSI + MACD + EMA 동일 방향 + strength > 0.5 → +0.05
        core_names = ("RSI", "MACD", "EMA")
        core = [by_name[n] for n in core_names if n in by_name]
        if len(core) == 3:
            dirs = [r.signal for r in core]
            if (len(set(dirs)) == 1
                    and dirs[0] != "neutral"
                    and all(r.strength > 0.5 for r in core)):
                bonus += 0.05

        # 2) MA50/200 골든/데드크로스 보너스 → +0.03
        ma_cross = by_name.get("MA50/200")
        if ma_cross and ma_cross.strength >= 0.7:
            bonus += 0.03

        # 3) 스토캐스틱 + RSI 동시 과매수/과매도 → +0.03
        rsi = by_name.get("RSI")
        stoch = by_name.get("Stochastic")
        if rsi and stoch:
            if (rsi.signal == stoch.signal
                    and rsi.signal != "neutral"
                    and rsi.strength >= 0.6
                    and stoch.strength >= 0.6):
                bonus += 0.03

        # 4) 볼린저밴드 + ADX 합류: BB 극단 + ADX 추세 → +0.02
        bb = by_name.get("Bollinger Bands")
        adx = by_name.get("ADX")
        if bb and adx:
            if (bb.signal != "neutral" and bb.strength >= 0.6
                    and adx.signal != "neutral" and adx.strength >= 0.5):
                bonus += 0.02

        # 5) 거래량 지표 합류: MFI + CMF 동일 방향 → +0.02
        mfi = by_name.get("MFI")
        cmf = by_name.get("CMF")
        if mfi and cmf:
            if (mfi.signal == cmf.signal
                    and mfi.signal != "neutral"
                    and mfi.strength >= 0.5
                    and cmf.strength >= 0.5):
                bonus += 0.02

        return min(bonus, 0.15)

    def _scalp_volume_filter(self, df: pd.DataFrame, timeframe: str, confidence: float) -> float:
        """
        스캘프 TF(1m, 5m)에서 거래량이 낮으면 신뢰도를 감소시킴.
        거래량이 20봉 평균의 0.5배 미만이면 최대 -0.15 페널티.
        """
        if TF_CATEGORY.get(timeframe) != "scalp":
            return confidence

        if "volume" not in df.columns or len(df) < 21:
            return confidence

        vol = df["volume"]
        avg_vol = float(vol.iloc[-21:-1].mean())
        current_vol = float(vol.iloc[-1])

        if avg_vol <= 0:
            return confidence

        ratio = current_vol / avg_vol
        if ratio < 0.5:
            # 거래량 매우 낮음: 최대 -0.15 페널티
            penalty = 0.15 * (1.0 - ratio / 0.5)
            confidence = max(0.0, confidence - penalty)
            logger.debug("스캘프 거래량 필터: ratio=%.2f, penalty=%.3f", ratio, penalty)
        elif ratio < 0.8:
            # 거래량 다소 낮음: 최대 -0.05 페널티
            penalty = 0.05 * (1.0 - (ratio - 0.5) / 0.3)
            confidence = max(0.0, confidence - penalty)

        return confidence

    def _calc_category_score(self, signals: list[tuple[str, float]]) -> float:
        """카테고리 점수 계산 (-1.0 ~ 1.0)"""
        if not signals:
            return 0.0

        score = 0.0
        for signal, strength in signals:
            if signal == "long":
                score += strength
            elif signal == "short":
                score -= strength

        return max(min(score / len(signals), 1.0), -1.0)

    # 레짐별 동적 시그널 임계값
    REGIME_SIGNAL_THRESHOLDS: dict[str, dict[str, float]] = {
        "TRENDING_UP":   {"strong": 0.50, "normal": 0.15},   # 추세 방향 진입 쉽게
        "TRENDING_DOWN": {"strong": 0.50, "normal": 0.15},
        "RANGING":       {"strong": 0.70, "normal": 0.30},   # 더 확실할 때만 진입
        "VOLATILE":      {"strong": 0.65, "normal": 0.25},   # 약간 엄격
    }
    _DEFAULT_THRESHOLDS = {"strong": 0.60, "normal": 0.20}

    def _determine_signal(self, total_score: float, regime: str = "UNKNOWN") -> tuple[str, float]:
        """총점에서 최종 시그널 및 신뢰도 결정 (레짐별 동적 임계값)"""
        confidence = abs(total_score)
        th = self.REGIME_SIGNAL_THRESHOLDS.get(regime, self._DEFAULT_THRESHOLDS)
        strong_th = th["strong"]
        normal_th = th["normal"]

        if total_score >= strong_th:
            return "STRONG_LONG", min(confidence, 1.0)
        elif total_score >= normal_th:
            return "LONG", min(confidence, 1.0)
        elif total_score <= -strong_th:
            return "STRONG_SHORT", min(confidence, 1.0)
        elif total_score <= -normal_th:
            return "SHORT", min(confidence, 1.0)
        else:
            return "NEUTRAL", confidence

    def _generate_summary(
        self,
        signal: str,
        confidence: float,
        indicators: list,
        candles: list,
        charts: list,
        volumes: list,
        futures: list,
        mtf: Optional[MTFConfirmation] = None,
        trade_params: Optional[TradeParams] = None,
    ) -> str:
        """사람이 읽을 수 있는 요약 생성"""
        signal_kr = {
            "STRONG_LONG": "강한 롱 (매수)",
            "LONG": "롱 (매수)",
            "NEUTRAL": "관망",
            "SHORT": "숏 (매도)",
            "STRONG_SHORT": "강한 숏 (매도)",
        }

        parts = [f"종합 판단: {signal_kr.get(signal, signal)} (신뢰도 {confidence:.0%})"]

        if mtf:
            parts.append(f"상위TF({mtf.higher_tf}): {mtf.description}")

        long_reasons = []
        short_reasons = []

        for ind in indicators:
            if ind.signal == "long" and ind.strength >= 0.5:
                long_reasons.append(ind.description)
            elif ind.signal == "short" and ind.strength >= 0.5:
                short_reasons.append(ind.description)

        for cp in candles:
            if cp.signal == "long":
                long_reasons.append(cp.description)
            elif cp.signal == "short":
                short_reasons.append(cp.description)

        for cp in charts:
            if cp.signal == "long":
                long_reasons.append(cp.description)
            elif cp.signal == "short":
                short_reasons.append(cp.description)

        for vol in volumes:
            if vol.signal == "long":
                long_reasons.append(vol.description)
            elif vol.signal == "short":
                short_reasons.append(vol.description)

        for f in futures:
            if f.signal == "long" and f.strength >= 0.4:
                long_reasons.append(f.description)
            elif f.signal == "short" and f.strength >= 0.4:
                short_reasons.append(f.description)

        if long_reasons:
            parts.append("롱 근거: " + " / ".join(long_reasons[:4]))
        if short_reasons:
            parts.append("숏 근거: " + " / ".join(short_reasons[:4]))

        if trade_params:
            direction = "롱" if trade_params.position_direction == "long" else "숏"
            parts.append(
                f"추천 {direction}: 진입 ${trade_params.entry_price:,.2f} / "
                f"손절 ${trade_params.stop_loss:,.2f} ({trade_params.risk_percent:.1f}%) / "
                f"익절 ${trade_params.take_profit_2:,.2f} (R:R 1:{trade_params.risk_reward_ratio:.0f})"
            )

        return "\n".join(parts)

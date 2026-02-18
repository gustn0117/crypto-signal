"""
시그널 엔진 - 모든 분석 결과를 종합하여 최종 롱/숏 시그널 생성
"""
import logging
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
    IndicatorResult,
)
from .candle_patterns import analyze_candle_patterns, CandlePatternResult
from .chart_patterns import analyze_chart_patterns, ChartPatternResult
from .volume import analyze_volume, VolumeResult
from .levels import calculate_levels, PriceLevels
from .trade_params import calculate_trade_params, TradeParams
from .mtf import check_higher_tf, MTFConfirmation
import pandas_ta as ta

logger = logging.getLogger(__name__)


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
    summary: str = ""
    timestamp: str = ""
    trade_params: Optional[dict] = None
    mtf_confirmation: Optional[dict] = None
    price_levels: Optional[dict] = None
    indicator_snapshot: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "signal": self.signal,
            "confidence": round(self.confidence, 3),
            "current_price": self.current_price,
            "indicators": self.indicators,
            "candle_patterns": self.candle_patterns,
            "chart_patterns": self.chart_patterns,
            "volume_signals": self.volume_signals,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "trade_params": self.trade_params,
            "mtf_confirmation": self.mtf_confirmation,
            "price_levels": self.price_levels,
            "indicator_snapshot": self.indicator_snapshot,
        }


class SignalEngine:
    """
    복합 전략 시그널 엔진
    기술적 지표 + 캔들 패턴 + 거래량 분석을 종합하여 최종 시그널 생성
    """

    WEIGHTS = {
        "indicators": 0.35,
        "candle_patterns": 0.15,
        "chart_patterns": 0.30,
        "volume": 0.20,
    }

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        higher_tf_df: Optional[pd.DataFrame] = None,
    ) -> TradeSignal:
        """종합 분석 수행 후 TradeSignal 반환"""
        current_price = df["close"].iloc[-1]

        # 1) 기술적 지표 분석
        indicator_results: List[IndicatorResult] = [
            analyze_rsi(df),
            analyze_macd(df),
            analyze_bollinger_bands(df),
            analyze_ema_cross(df),
            analyze_stochastic(df),
        ]

        # 2) 캔들 패턴 분석
        candle_results: List[CandlePatternResult] = analyze_candle_patterns(df)

        # 3) 차트 패턴 분석 (구조적 패턴)
        chart_results: List[ChartPatternResult] = analyze_chart_patterns(df)

        # 4) 거래량 분석
        volume_results: List[VolumeResult] = analyze_volume(df)

        # 5) 점수 계산
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

        # 6) 가중 합산
        total_score = (
            indicator_score * self.WEIGHTS["indicators"]
            + candle_score * self.WEIGHTS["candle_patterns"]
            + chart_score * self.WEIGHTS["chart_patterns"]
            + volume_score * self.WEIGHTS["volume"]
        )

        # 6) 시그널 결정
        signal, confidence = self._determine_signal(total_score)

        # 7) 가격 레벨 계산
        levels = calculate_levels(df)

        # 8) 멀티 타임프레임 확인
        mtf_result: Optional[MTFConfirmation] = None
        if higher_tf_df is not None and len(higher_tf_df) >= 50:
            from config import HIGHER_TF_MAP
            higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
            mtf_result = check_higher_tf(higher_tf_df, signal, higher_tf)
            if mtf_result:
                # MTF 보정 적용
                confidence = max(0.0, min(1.0, confidence + mtf_result.confidence_modifier))
                logger.debug(
                    "%s MTF %s: %s (modifier=%.2f)",
                    symbol, mtf_result.higher_tf, mtf_result.alignment, mtf_result.confidence_modifier
                )

        # 9) 트레이드 파라미터 계산
        trade_params_result: Optional[TradeParams] = None
        if signal != "NEUTRAL":
            trade_params_result = calculate_trade_params(df, signal, levels)

        # 10) 지표 스냅샷 생성 (예측 엔진용)
        indicator_snapshot = self._build_indicator_snapshot(df)

        # 11) 요약 생성
        summary = self._generate_summary(signal, confidence, indicator_results, candle_results, chart_results, volume_results, mtf_result, trade_params_result)

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
            summary=summary,
            timestamp=datetime.now(timezone.utc).isoformat(),
            trade_params=trade_params_result.to_dict() if trade_params_result else None,
            mtf_confirmation=mtf_result.to_dict() if mtf_result else None,
            price_levels=levels.to_dict(),
            indicator_snapshot=indicator_snapshot,
        )

    def _build_indicator_snapshot(self, df: pd.DataFrame) -> dict:
        """예측 엔진에 전달할 지표 스냅샷 생성."""
        snapshot: dict = {}
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        try:
            # RSI(14)
            rsi = ta.rsi(close, length=14)
            if rsi is not None and not rsi.empty:
                snapshot["rsi"] = round(float(rsi.dropna().iloc[-1]), 2)

            # MACD 히스토그램 3봉 기울기
            macd_df = ta.macd(close, fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.empty:
                hist_col = [c for c in macd_df.columns if "MACDh" in c or "Histogram" in c.replace("_", "")]
                if not hist_col:
                    hist_col = [c for c in macd_df.columns if "h_" in c]
                if hist_col:
                    hist = macd_df[hist_col[0]].dropna()
                    if len(hist) >= 4:
                        slope = (float(hist.iloc[-1]) - float(hist.iloc[-3])) / 2
                        snapshot["macd_hist_slope"] = round(slope, 6)

            # 볼린저 밴드 내 위치 (0=하단, 1=상단)
            bbands = ta.bbands(close, length=20, std=2.0)
            if bbands is not None and not bbands.empty:
                upper_col = [c for c in bbands.columns if "BBU" in c]
                lower_col = [c for c in bbands.columns if "BBL" in c]
                if upper_col and lower_col:
                    bbu = float(bbands[upper_col[0]].dropna().iloc[-1])
                    bbl = float(bbands[lower_col[0]].dropna().iloc[-1])
                    if bbu != bbl:
                        bb_pos = (float(close.iloc[-1]) - bbl) / (bbu - bbl)
                        snapshot["bb_position"] = round(max(0.0, min(1.0, bb_pos)), 3)

            # 거래량 비율: 현재 / 20봉 평균
            vol_ma = volume.rolling(20, min_periods=10).mean()
            if vol_ma is not None and not vol_ma.empty:
                avg_vol = float(vol_ma.dropna().iloc[-1])
                if avg_vol > 0:
                    snapshot["volume_ratio"] = round(float(volume.iloc[-1]) / avg_vol, 3)

            # ATR(14) - 예측에서 직접 사용
            atr = ta.atr(high, low, close, length=14)
            if atr is not None and not atr.empty:
                snapshot["atr"] = round(float(atr.dropna().iloc[-1]), 6)

        except Exception as e:
            logger.warning("indicator_snapshot 생성 실패: %s", e)

        return snapshot

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

    def _determine_signal(self, total_score: float) -> tuple[str, float]:
        """총점에서 최종 시그널 및 신뢰도 결정"""
        confidence = abs(total_score)

        if total_score >= 0.6:
            return "STRONG_LONG", min(confidence, 1.0)
        elif total_score >= 0.2:
            return "LONG", min(confidence, 1.0)
        elif total_score <= -0.6:
            return "STRONG_SHORT", min(confidence, 1.0)
        elif total_score <= -0.2:
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

        # MTF 정보
        if mtf:
            parts.append(f"상위TF({mtf.higher_tf}): {mtf.description}")

        # 주요 근거
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

        if long_reasons:
            parts.append("롱 근거: " + " / ".join(long_reasons[:3]))
        if short_reasons:
            parts.append("숏 근거: " + " / ".join(short_reasons[:3]))

        # SL/TP 정보
        if trade_params:
            direction = "롱" if trade_params.position_direction == "long" else "숏"
            parts.append(
                f"추천 {direction}: 진입 ${trade_params.entry_price:,.2f} / "
                f"손절 ${trade_params.stop_loss:,.2f} ({trade_params.risk_percent:.1f}%) / "
                f"익절 ${trade_params.take_profit_2:,.2f} (R:R 1:{trade_params.risk_reward_ratio:.0f})"
            )

        return "\n".join(parts)

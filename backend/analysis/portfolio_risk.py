"""
포트폴리오 리스크 관리 모듈
VaR, 포지션 제한, 상관관계 리스크, 드로다운 관리
"""
import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 리스크 한도
MAX_POSITION_PCT = 20.0       # 단일 포지션 최대 비율 (%)
MAX_TOTAL_EXPOSURE_PCT = 80.0  # 총 노출 최대 비율 (%)
MAX_CORRELATED_POSITIONS = 3   # 고상관(>0.85) 포지션 최대 수
MAX_DAILY_LOSS_PCT = 10.0      # 일일 최대 손실 제한 (%)
VAR_CONFIDENCE = 0.95          # VaR 신뢰수준


@dataclass
class RiskWarning:
    """리스크 경고"""
    level: str          # "info", "warning", "critical"
    category: str       # "position_limit", "correlation", "var", "drawdown"
    message: str
    value: float = 0.0


@dataclass
class PortfolioRiskReport:
    """포트폴리오 리스크 리포트"""
    total_exposure_pct: float       # 총 노출 비율
    portfolio_beta: float           # 가중 평균 BTC 베타
    var_95: float                   # 95% VaR (금액)
    var_95_pct: float               # 95% VaR (%)
    max_position_pct: float         # 최대 단일 포지션 비율
    position_count: int             # 오픈 포지션 수
    warnings: List[RiskWarning] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_exposure_pct": round(self.total_exposure_pct, 2),
            "portfolio_beta": round(self.portfolio_beta, 3),
            "var_95": round(self.var_95, 2),
            "var_95_pct": round(self.var_95_pct, 2),
            "max_position_pct": round(self.max_position_pct, 2),
            "position_count": self.position_count,
            "warnings": [
                {"level": w.level, "category": w.category,
                 "message": w.message, "value": round(w.value, 4)}
                for w in self.warnings
            ],
        }


class PortfolioRiskManager:
    """포트폴리오 리스크 관리"""

    def __init__(self, correlation_analyzer=None):
        self.correlation = correlation_analyzer

    def assess_risk(
        self,
        positions: list[dict],
        equity: float,
        daily_pnl: float = 0.0,
    ) -> PortfolioRiskReport:
        """현재 포트폴리오 리스크 종합 평가."""
        warnings: List[RiskWarning] = []

        if not positions or equity <= 0:
            return PortfolioRiskReport(0, 0, 0, 0, 0, 0, [])

        # 1) 총 노출
        total_exposure = sum(abs(float(p.get("position_usdt", 0))) for p in positions)
        total_exposure_pct = (total_exposure / equity) * 100

        if total_exposure_pct > MAX_TOTAL_EXPOSURE_PCT:
            warnings.append(RiskWarning(
                "critical", "exposure",
                f"총 노출 {total_exposure_pct:.1f}% > 한도 {MAX_TOTAL_EXPOSURE_PCT}%",
                total_exposure_pct,
            ))

        # 2) 최대 단일 포지션
        max_pos_pct = 0.0
        for p in positions:
            pos_pct = abs(float(p.get("position_usdt", 0))) / equity * 100
            max_pos_pct = max(max_pos_pct, pos_pct)
            if pos_pct > MAX_POSITION_PCT:
                warnings.append(RiskWarning(
                    "warning", "position_limit",
                    f"{p.get('symbol', '?')} 포지션 {pos_pct:.1f}% > 한도 {MAX_POSITION_PCT}%",
                    pos_pct,
                ))

        # 3) BTC 베타 가중 평균
        portfolio_beta = self._calc_portfolio_beta(positions, equity)

        # 4) 상관관계 리스크
        corr_warnings = self._check_correlation_risk(positions)
        warnings.extend(corr_warnings)

        # 5) VaR (간이 파라메트릭)
        var_pct = self._calc_parametric_var(positions, equity)
        var_amount = equity * var_pct / 100

        # 6) 일일 드로다운 체크
        if daily_pnl < 0:
            daily_loss_pct = abs(daily_pnl) / equity * 100
            if daily_loss_pct > MAX_DAILY_LOSS_PCT:
                warnings.append(RiskWarning(
                    "critical", "drawdown",
                    f"일일 손실 {daily_loss_pct:.1f}% > 한도 {MAX_DAILY_LOSS_PCT}%",
                    daily_loss_pct,
                ))

        return PortfolioRiskReport(
            total_exposure_pct=total_exposure_pct,
            portfolio_beta=portfolio_beta,
            var_95=var_amount,
            var_95_pct=var_pct,
            max_position_pct=max_pos_pct,
            position_count=len(positions),
            warnings=warnings,
        )

    def check_new_position(
        self,
        symbol: str,
        size_usdt: float,
        positions: list[dict],
        equity: float,
    ) -> list[RiskWarning]:
        """새 포지션 오픈 전 리스크 체크."""
        warnings = []

        if equity <= 0:
            return [RiskWarning("critical", "equity", "자본금 0 이하", 0)]

        # 단일 포지션 한도
        pos_pct = size_usdt / equity * 100
        if pos_pct > MAX_POSITION_PCT:
            warnings.append(RiskWarning(
                "warning", "position_limit",
                f"요청 포지션 {pos_pct:.1f}% > 한도 {MAX_POSITION_PCT}%",
                pos_pct,
            ))

        # 총 노출 한도
        current_exposure = sum(abs(float(p.get("position_usdt", 0))) for p in positions)
        new_total_pct = (current_exposure + size_usdt) / equity * 100
        if new_total_pct > MAX_TOTAL_EXPOSURE_PCT:
            warnings.append(RiskWarning(
                "critical", "exposure",
                f"총 노출 {new_total_pct:.1f}% > 한도 {MAX_TOTAL_EXPOSURE_PCT}%",
                new_total_pct,
            ))

        # 상관관계 체크
        if self.correlation:
            high_corr_count = 0
            for p in positions:
                corr = self.correlation.get_correlation(symbol, p.get("symbol", ""))
                if corr is not None and corr > 0.85:
                    high_corr_count += 1
            if high_corr_count >= MAX_CORRELATED_POSITIONS:
                warnings.append(RiskWarning(
                    "warning", "correlation",
                    f"{symbol} 고상관 포지션 {high_corr_count}개 (한도 {MAX_CORRELATED_POSITIONS})",
                    high_corr_count,
                ))

        return warnings

    def _calc_portfolio_beta(self, positions: list[dict], equity: float) -> float:
        """가중 평균 BTC 베타."""
        if not self.correlation or equity <= 0:
            return 1.0

        weighted_beta = 0.0
        total_weight = 0.0
        for p in positions:
            sym = p.get("symbol", "")
            weight = abs(float(p.get("position_usdt", 0))) / equity
            beta = self.correlation.get_beta(sym)
            if beta is not None:
                weighted_beta += beta * weight
                total_weight += weight

        return weighted_beta / total_weight if total_weight > 0 else 1.0

    def _check_correlation_risk(self, positions: list[dict]) -> list[RiskWarning]:
        """고상관 포지션 동시 보유 경고."""
        warnings = []
        if not self.correlation or len(positions) < 2:
            return warnings

        symbols = [p.get("symbol", "") for p in positions]
        checked = set()
        for i, sym_a in enumerate(symbols):
            for j, sym_b in enumerate(symbols):
                if i >= j:
                    continue
                pair = tuple(sorted([sym_a, sym_b]))
                if pair in checked:
                    continue
                checked.add(pair)
                corr = self.correlation.get_correlation(sym_a, sym_b)
                if corr is not None and corr > 0.85:
                    warnings.append(RiskWarning(
                        "info", "correlation",
                        f"{sym_a} ↔ {sym_b} 상관계수 {corr:.2f} (높음)",
                        corr,
                    ))
        return warnings

    def _calc_parametric_var(self, positions: list[dict], equity: float) -> float:
        """간이 파라메트릭 VaR (정규분포 가정, 일간 95%)."""
        if not positions or equity <= 0:
            return 0.0

        # 각 포지션의 ATR% 기반 일간 변동성 추정
        total_var_sq = 0.0
        for p in positions:
            pos_usdt = abs(float(p.get("position_usdt", 0)))
            weight = pos_usdt / equity
            # ATR%가 없으면 크립토 평균 3% 사용
            daily_vol = 0.03
            total_var_sq += (weight * daily_vol) ** 2

        portfolio_vol = math.sqrt(total_var_sq)
        # 95% VaR = 1.645 * portfolio_vol
        var_pct = 1.645 * portfolio_vol * 100
        return var_pct

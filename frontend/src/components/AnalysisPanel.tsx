"use client";

import { Signal } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import SignalBadge from "./SignalBadge";
import MTFBadge from "./MTFBadge";
import { AnalysisSkeleton } from "./Skeleton";
import { BarChart3 } from "lucide-react";

interface AnalysisPanelProps {
  signal: Signal | null;
  loading?: boolean;
}

function StrengthBar({ strength, signal }: { strength: number; signal: string }) {
  const color = signal === "long" ? "var(--long)" : signal === "short" ? "var(--short)" : "var(--text-muted)";
  return (
    <div className="w-full h-1.5 bg-card-active rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{ width: `${strength * 100}%`, backgroundColor: color }}
      />
    </div>
  );
}

export default function AnalysisPanel({ signal, loading }: AnalysisPanelProps) {
  if (loading) {
    return <AnalysisSkeleton />;
  }

  if (!signal) {
    return (
      <div className="p-6 flex items-center justify-center h-64 text-muted">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-card-active flex items-center justify-center">
            <BarChart3 size={22} className="text-icon-muted" />
          </div>
          <p className="text-sm">코인을 선택하면 상세 분석을 볼 수 있습니다</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4 overflow-auto max-h-[600px]">
      {/* 종합 판단 */}
      <div className="p-4 rounded-card bg-card-active">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-base text-heading">{signal.symbol}</h3>
          <SignalBadge signal={signal.signal} confidence={signal.confidence} size="lg" />
        </div>
        <p className="text-sm text-muted whitespace-pre-line leading-relaxed">{signal.summary}</p>
        {signal.mtf_confirmation && (
          <div className="mt-3">
            <MTFBadge mtf={signal.mtf_confirmation} size="sm" />
          </div>
        )}
      </div>

      {/* SL/TP 간략 표시 */}
      {signal.trade_params && (
        <div className="p-3 rounded-card bg-card-active">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-muted uppercase tracking-wider">
              트레이드 파라미터
            </h4>
            <span
              className="text-xs font-bold"
              style={{ color: signal.trade_params.position_direction === "long" ? "var(--long)" : "var(--short)" }}
            >
              {signal.trade_params.position_direction.toUpperCase()}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <span className="text-muted">SL</span>
              <div className="font-mono text-danger">${formatPrice(signal.trade_params.stop_loss)}</div>
            </div>
            <div>
              <span className="text-muted">Entry</span>
              <div className="font-mono text-primary">${formatPrice(signal.trade_params.entry_price)}</div>
            </div>
            <div>
              <span className="text-muted">TP1</span>
              <div className="font-mono text-success-text">${formatPrice(signal.trade_params.take_profit_1)}</div>
            </div>
          </div>
          <div className="flex items-center justify-between mt-2 text-xs text-muted">
            <span>R:R 1:{signal.trade_params.risk_reward_ratio.toFixed(1)}</span>
            <span className="text-danger">리스크 {signal.trade_params.risk_percent.toFixed(2)}%</span>
          </div>
        </div>
      )}

      {/* 기술적 지표 */}
      <div>
        <h4 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
          기술적 지표
        </h4>
        <div className="space-y-2">
          {signal.indicators.map((ind, i) => (
            <div key={i} className="p-3 rounded-card bg-card-active">
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-medium text-sm text-heading">{ind.name}</span>
                <span
                  className="text-xs font-medium"
                  style={{
                    color: ind.signal === "long" ? "var(--long)" : ind.signal === "short" ? "var(--short)" : "var(--text-muted)",
                  }}
                >
                  {ind.signal.toUpperCase()}
                </span>
              </div>
              <StrengthBar strength={ind.strength} signal={ind.signal} />
              <p className="text-xs text-muted mt-1.5">{ind.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 캔들 패턴 */}
      {signal.candle_patterns.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
            캔들 패턴
          </h4>
          <div className="space-y-2">
            {signal.candle_patterns.map((cp, i) => (
              <div key={i} className="p-3 rounded-card bg-card-active">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm text-heading">{cp.name}</span>
                  <span
                    className="text-xs font-medium"
                    style={{ color: cp.signal === "long" ? "var(--long)" : "var(--short)" }}
                  >
                    {cp.signal.toUpperCase()}
                  </span>
                </div>
                <StrengthBar strength={cp.strength} signal={cp.signal} />
                <p className="text-xs text-muted mt-1.5">{cp.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 거래량 분석 */}
      {signal.volume_signals.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
            거래량 분석
          </h4>
          <div className="space-y-2">
            {signal.volume_signals.map((vol, i) => (
              <div key={i} className="p-3 rounded-card bg-card-active">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm text-heading">{vol.name}</span>
                  <span
                    className="text-xs font-medium"
                    style={{ color: vol.signal === "long" ? "var(--long)" : "var(--short)" }}
                  >
                    {vol.signal.toUpperCase()}
                  </span>
                </div>
                <StrengthBar strength={vol.strength} signal={vol.signal} />
                <p className="text-xs text-muted mt-1.5">{vol.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 선물 데이터 */}
      {signal.futures_signals && signal.futures_signals.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
            선물 데이터
          </h4>
          <div className="space-y-2">
            {signal.futures_signals.map((fut, i) => (
              <div key={i} className="p-3 rounded-card bg-card-active">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm text-heading">{fut.name}</span>
                  <span
                    className="text-xs font-medium"
                    style={{ color: fut.signal === "long" ? "var(--long)" : fut.signal === "short" ? "var(--short)" : "var(--text-muted)" }}
                  >
                    {fut.signal.toUpperCase()}
                  </span>
                </div>
                <StrengthBar strength={fut.strength} signal={fut.signal} />
                <p className="text-xs text-muted mt-1.5">{fut.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

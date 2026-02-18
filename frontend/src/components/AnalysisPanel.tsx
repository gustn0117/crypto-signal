"use client";

import { Signal } from "@/lib/api";
import SignalBadge from "./SignalBadge";
import MTFBadge from "./MTFBadge";

interface AnalysisPanelProps {
  signal: Signal | null;
  loading?: boolean;
}

function formatCompact(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

function StrengthBar({ strength, signal }: { strength: number; signal: string }) {
  const color = signal === "long" ? "#4caf50" : signal === "short" ? "#ff5722" : "#abafb3";
  return (
    <div className="w-full h-1.5 bg-card-active rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${strength * 100}%`, backgroundColor: color }}
      />
    </div>
  );
}

export default function AnalysisPanel({ signal, loading }: AnalysisPanelProps) {
  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <div className="animate-pulse text-muted">분석 중...</div>
      </div>
    );
  }

  if (!signal) {
    return (
      <div className="p-6 flex items-center justify-center h-full text-muted">
        <div className="text-center">
          <div className="text-4xl mb-3">📈</div>
          <p>코인을 선택하면 상세 분석을 볼 수 있습니다</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-5 overflow-auto max-h-[600px]">
      {/* 종합 판단 */}
      <div className="p-4 rounded-lg bg-card border border-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-lg">{signal.symbol}</h3>
          <SignalBadge signal={signal.signal} confidence={signal.confidence} size="lg" />
        </div>
        <p className="text-sm text-muted whitespace-pre-line">{signal.summary}</p>
        {/* MTF 배지 */}
        {signal.mtf_confirmation && (
          <div className="mt-3">
            <MTFBadge mtf={signal.mtf_confirmation} size="sm" />
          </div>
        )}
      </div>

      {/* SL/TP 간략 표시 */}
      {signal.trade_params && (
        <div className="p-3 rounded-lg bg-card border border-border">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-muted uppercase tracking-wider">
              트레이드 파라미터
            </h4>
            <span
              className="text-xs font-bold"
              style={{ color: signal.trade_params.position_direction === "long" ? "#4caf50" : "#ff5722" }}
            >
              {signal.trade_params.position_direction.toUpperCase()}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <span className="text-muted">SL</span>
              <div className="font-mono" style={{ color: "#ef5350" }}>${formatCompact(signal.trade_params.stop_loss)}</div>
            </div>
            <div>
              <span className="text-muted">Entry</span>
              <div className="font-mono" style={{ color: "#4680ff" }}>${formatCompact(signal.trade_params.entry_price)}</div>
            </div>
            <div>
              <span className="text-muted">TP1</span>
              <div className="font-mono" style={{ color: "#4caf50" }}>${formatCompact(signal.trade_params.take_profit_1)}</div>
            </div>
          </div>
          <div className="flex items-center justify-between mt-2 text-xs text-muted">
            <span>R:R 1:{signal.trade_params.risk_reward_ratio.toFixed(1)}</span>
            <span style={{ color: "#ff5722" }}>리스크 {signal.trade_params.risk_percent.toFixed(2)}%</span>
          </div>
        </div>
      )}

      {/* 기술적 지표 */}
      <div>
        <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-3">
          기술적 지표
        </h4>
        <div className="space-y-2">
          {signal.indicators.map((ind, i) => (
            <div key={i} className="p-3 rounded bg-card border border-card-active">
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-medium text-sm">{ind.name}</span>
                <span
                  className="text-xs font-medium"
                  style={{
                    color: ind.signal === "long" ? "#4caf50" : ind.signal === "short" ? "#ff5722" : "#abafb3",
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
          <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-3">
            캔들 패턴
          </h4>
          <div className="space-y-2">
            {signal.candle_patterns.map((cp, i) => (
              <div key={i} className="p-3 rounded bg-card border border-card-active">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm">{cp.name}</span>
                  <span
                    className="text-xs font-medium"
                    style={{
                      color: cp.signal === "long" ? "#4caf50" : "#ff5722",
                    }}
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
          <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-3">
            거래량 분석
          </h4>
          <div className="space-y-2">
            {signal.volume_signals.map((vol, i) => (
              <div key={i} className="p-3 rounded bg-card border border-card-active">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm">{vol.name}</span>
                  <span
                    className="text-xs font-medium"
                    style={{
                      color: vol.signal === "long" ? "#4caf50" : "#ff5722",
                    }}
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
    </div>
  );
}

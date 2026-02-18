"use client";

import { useState } from "react";
import { Prediction, PredictionStats } from "@/lib/api";
import { CheckCircle, XCircle, Clock, BarChart3, RefreshCw } from "lucide-react";

interface PredictionHistoryPanelProps {
  predictions: Prediction[];
  stats: PredictionStats | null;
  onVerify: (id: number) => Promise<unknown>;
  onReload: () => void;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const RESULT_CONFIG: Record<string, { label: string; color: string; icon: typeof CheckCircle }> = {
  HIT_TP3: { label: "TP3 도달", color: "#26dad2", icon: CheckCircle },
  HIT_TP2: { label: "TP2 도달", color: "#26dad2", icon: CheckCircle },
  HIT_TP1: { label: "TP1 도달", color: "#26dad2", icon: CheckCircle },
  PARTIAL: { label: "부분 수익", color: "#ffb22b", icon: Clock },
  NEUTRAL: { label: "보합", color: "#abafb3", icon: Clock },
  HIT_SL: { label: "손절 도달", color: "#ef5350", icon: XCircle },
  WRONG: { label: "예측 실패", color: "#ef5350", icon: XCircle },
};

export default function PredictionHistoryPanel({
  predictions,
  stats,
  onVerify,
  onReload,
}: PredictionHistoryPanelProps) {
  const [verifying, setVerifying] = useState<number | null>(null);

  if (predictions.length === 0 && (!stats || stats.total_predictions === 0)) return null;

  const handleVerify = async (id: number) => {
    setVerifying(id);
    try {
      await onVerify(id);
    } finally {
      setVerifying(null);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-body overflow-hidden">
      <div className="px-4 py-3 bg-card border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 size={16} className="text-primary" />
          <h3 className="font-semibold text-heading">예측 히스토리</h3>
        </div>
        <button onClick={onReload} className="p-1 rounded hover:bg-card-active transition-colors">
          <RefreshCw size={14} className="text-muted" />
        </button>
      </div>

      {stats && stats.total_predictions > 0 && (
        <div className="px-4 py-3 border-b border-card-active grid grid-cols-4 gap-3">
          <StatBox label="총 예측" value={String(stats.total_predictions)} />
          <StatBox
            label="TP 적중률"
            value={`${(stats.tp_hit_rate * 100).toFixed(1)}%`}
            color="#4caf50"
          />
          <StatBox
            label="SL 적중률"
            value={`${(stats.sl_hit_rate * 100).toFixed(1)}%`}
            color="#ef5350"
          />
          <StatBox
            label="평균 정확도"
            value={`${(stats.avg_accuracy_score * 100).toFixed(1)}%`}
            color="#4680ff"
          />
        </div>
      )}

      <div className="divide-y divide-card-active max-h-[400px] overflow-auto">
        {predictions.map((pred) => {
          const rc = pred.result ? RESULT_CONFIG[pred.result] : null;
          const Icon = rc?.icon || Clock;
          return (
            <div key={pred.id} className="px-4 py-3 hover:bg-card transition-colors">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs font-bold px-2 py-0.5 rounded ${
                      pred.signal_direction.includes("LONG")
                        ? "text-success bg-[#26dad215]"
                        : pred.signal_direction.includes("SHORT")
                        ? "text-danger bg-[#ef535015]"
                        : "text-muted bg-[#abafb315]"
                    }`}
                  >
                    {pred.signal_direction}
                  </span>
                  <span className="text-xs text-muted">{formatTime(pred.created_at)}</span>
                </div>
                <div className="flex items-center gap-2">
                  {pred.status === "ACTIVE" ? (
                    <>
                      <span className="text-xs text-primary">활성</span>
                      <button
                        onClick={() => handleVerify(pred.id)}
                        disabled={verifying === pred.id}
                        className="text-xs px-2 py-1 rounded bg-card-active text-muted hover:text-white transition-colors disabled:opacity-50"
                      >
                        {verifying === pred.id ? "검증 중..." : "검증"}
                      </button>
                    </>
                  ) : pred.status === "EXPIRED" ? (
                    <span className="text-xs text-muted">만료</span>
                  ) : (
                    <div className="flex items-center gap-1" style={{ color: rc?.color }}>
                      <Icon size={14} />
                      <span className="text-xs font-medium">{rc?.label}</span>
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs text-muted">
                <span>진입: ${formatPrice(pred.entry_price)}</span>
                <span>신뢰도: {(pred.confidence * 100).toFixed(0)}%</span>
                {pred.accuracy_score !== null && (
                  <span style={{ color: "#4680ff" }}>
                    정확도: {(pred.accuracy_score * 100).toFixed(1)}%
                  </span>
                )}
                {pred.max_favorable !== null && (
                  <span className="text-success">MFE: +{pred.max_favorable.toFixed(2)}%</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="p-2 rounded bg-card text-center">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-sm font-bold" style={{ color: color || "#ffffff" }}>
        {value}
      </div>
    </div>
  );
}

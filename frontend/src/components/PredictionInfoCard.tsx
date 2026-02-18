"use client";

import { Prediction } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { TrendingUp, TrendingDown, Clock, Target, ShieldAlert } from "lucide-react";

interface PredictionInfoCardProps {
  prediction: Prediction;
}

const REGIME_LABELS: Record<string, { label: string; color: string }> = {
  TRENDING_UP: { label: "상승 추세", color: "var(--long)" },
  TRENDING_DOWN: { label: "하락 추세", color: "var(--short)" },
  RANGING: { label: "횡보", color: "var(--warning)" },
  VOLATILE: { label: "변동성 확대", color: "var(--secondary)" },
};

export default function PredictionInfoCard({ prediction }: PredictionInfoCardProps) {
  const isLong = prediction.signal_direction.includes("LONG");
  const pnl = prediction.progress_pnl_pct;
  const rr = prediction.progress_rr_current;
  const timePct = prediction.progress_time_pct;
  const pathAcc = prediction.progress_path_accuracy;

  const regimeInfo = prediction.regime ? REGIME_LABELS[prediction.regime] : null;

  const tpChecks = {
    tp1: pnl !== null && pnl >= ((Math.abs(prediction.take_profit_1 - prediction.entry_price) / prediction.entry_price) * 100),
    tp2: pnl !== null && pnl >= ((Math.abs(prediction.take_profit_2 - prediction.entry_price) / prediction.entry_price) * 100),
    tp3: pnl !== null && pnl >= ((Math.abs(prediction.take_profit_3 - prediction.entry_price) / prediction.entry_price) * 100),
    sl: pnl !== null && pnl <= -((Math.abs(prediction.stop_loss - prediction.entry_price) / prediction.entry_price) * 100),
  };

  const createdAt = new Date(prediction.created_at);
  const tfSeconds: Record<string, number> = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
  };
  const totalSec = prediction.horizon_candles * (tfSeconds[prediction.timeframe] || 3600);
  const elapsedSec = (Date.now() - createdAt.getTime()) / 1000;
  const remainHours = Math.max(0, (totalSec - elapsedSec) / 3600);

  return (
    <div className="rounded-lg border border-border bg-body overflow-hidden">
      <div className="px-4 py-3 bg-card border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isLong ? (
            <TrendingUp size={16} className="text-success" />
          ) : (
            <TrendingDown size={16} className="text-danger" />
          )}
          <span className={`text-sm font-bold ${isLong ? "text-success" : "text-danger"}`}>
            {prediction.signal_direction}
          </span>
          <span className="text-xs text-muted">
            ({(prediction.confidence * 100).toFixed(0)}%)
          </span>
          {regimeInfo && (
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{ color: regimeInfo.color, backgroundColor: `color-mix(in srgb, ${regimeInfo.color} 10%, transparent)` }}
            >
              {regimeInfo.label}
            </span>
          )}
        </div>
        {prediction.auto_generated && (
          <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">Auto</span>
        )}
      </div>

      <div className="px-4 py-3 border-b border-card-active">
        <div className="flex items-center justify-between text-xs">
          <div>
            <span className="text-muted">진입: </span>
            <span className="text-heading font-mono">${formatPrice(prediction.entry_price)}</span>
          </div>
          <div>
            <span className="text-danger">SL: </span>
            <span className="font-mono">${formatPrice(prediction.stop_loss)}</span>
          </div>
          <div className="text-success">
            TP: {formatPrice(prediction.take_profit_1)} / {formatPrice(prediction.take_profit_2)} / {formatPrice(prediction.take_profit_3)}
          </div>
        </div>
      </div>

      <div className="px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricBox
          label="P&L"
          value={pnl !== null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}%` : "-"}
          color={pnl !== null ? (pnl >= 0 ? "var(--success-text)" : "var(--short)") : "var(--text-body)"}
        />
        <MetricBox
          label="R:R"
          value={rr !== null ? `${rr.toFixed(1)}x` : "-"}
          color="var(--primary)"
        />
        <MetricBox
          label="경로 정확도"
          value={pathAcc !== null ? `${(pathAcc * 100).toFixed(0)}%` : "-"}
          color="var(--warning)"
        />
        <MetricBox
          label="남은 시간"
          value={`${remainHours.toFixed(1)}h`}
          color="var(--text-body)"
        />
      </div>

      {timePct !== null && (
        <div className="px-4 pb-3">
          <div className="flex items-center justify-between text-xs text-muted mb-1">
            <span>시간 진행</span>
            <span>{(timePct * 100).toFixed(0)}%</span>
          </div>
          <div className="w-full h-1.5 bg-card-active rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${timePct * 100}%`,
                backgroundColor: timePct > 0.8 ? "var(--warning)" : "var(--primary)",
              }}
            />
          </div>
        </div>
      )}

      <div className="px-4 py-2 border-t border-card-active flex items-center gap-3 text-xs">
        <CheckItem label="TP1" hit={tpChecks.tp1} color="var(--long)" />
        <CheckItem label="TP2" hit={tpChecks.tp2} color="var(--long)" />
        <CheckItem label="TP3" hit={tpChecks.tp3} color="var(--long)" />
        <CheckItem label="SL" hit={tpChecks.sl} color="var(--short)" />
      </div>
    </div>
  );
}

function MetricBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="text-center">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-sm font-bold" style={{ color }}>{value}</div>
    </div>
  );
}

function CheckItem({ label, hit, color }: { label: string; hit: boolean; color: string }) {
  return (
    <div className="flex items-center gap-1">
      <span
        className="w-3 h-3 rounded-sm flex items-center justify-center text-[8px]"
        style={{
          backgroundColor: hit ? color : "transparent",
          border: `1px solid ${hit ? color : "var(--border)"}`,
          color: hit ? "#fff" : "var(--text-body)",
        }}
      >
        {hit ? "\u2713" : ""}
      </span>
      <span className={hit ? "font-medium" : "text-muted"} style={hit ? { color } : undefined}>
        {label}
      </span>
    </div>
  );
}

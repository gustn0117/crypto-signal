"use client";

import { Prediction } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import {
  TrendingUp,
  TrendingDown,
  Clock,
  Target,
  RotateCcw,
  Activity,
  Crosshair,
} from "lucide-react";

interface PredictionInfoCardProps {
  prediction: Prediction;
  onExpire?: (id: number) => void;
}

const REGIME_LABELS: Record<string, { label: string; color: string }> = {
  TRENDING_UP: { label: "상승 추세", color: "var(--long)" },
  TRENDING_DOWN: { label: "하락 추세", color: "var(--short)" },
  RANGING: { label: "횡보", color: "var(--warning)" },
  VOLATILE: { label: "변동성 확대", color: "var(--secondary)" },
};

function formatDateTime(isoStr: string): string {
  const d = new Date(isoStr);
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const hours = d.getHours().toString().padStart(2, "0");
  const mins = d.getMinutes().toString().padStart(2, "0");
  return `${month}/${day} ${hours}:${mins}`;
}

function formatElapsed(ms: number): string {
  const totalMin = Math.floor(ms / 60000);
  if (totalMin < 60) return `${totalMin}분`;
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours < 24) return mins > 0 ? `${hours}시간 ${mins}분` : `${hours}시간`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours > 0 ? `${days}일 ${remHours}시간` : `${days}일`;
}

function getAccuracyColor(acc: number): string {
  if (acc >= 0.7) return "var(--success-text)";
  if (acc >= 0.4) return "var(--warning)";
  return "var(--danger)";
}

function getAccuracyLabel(acc: number): string {
  if (acc >= 0.8) return "매우 정확";
  if (acc >= 0.6) return "양호";
  if (acc >= 0.4) return "보통";
  if (acc >= 0.2) return "부정확";
  return "이탈";
}

export default function PredictionInfoCard({ prediction, onExpire }: PredictionInfoCardProps) {
  const isLong = prediction.signal_direction.includes("LONG");
  const pnl = prediction.progress_pnl_pct;
  const rr = prediction.progress_rr_current;
  const timePct = prediction.progress_time_pct;
  const pathAcc = prediction.progress_path_accuracy;

  const regimeInfo = prediction.regime ? REGIME_LABELS[prediction.regime] : null;

  const tpPct = (tp: number) => {
    const diff = isLong ? tp - prediction.entry_price : prediction.entry_price - tp;
    return (diff / prediction.entry_price) * 100;
  };
  const slPct = (() => {
    const diff = isLong
      ? prediction.entry_price - prediction.stop_loss
      : prediction.stop_loss - prediction.entry_price;
    return (diff / prediction.entry_price) * 100;
  })();

  const tpChecks = {
    tp1: pnl !== null && pnl >= tpPct(prediction.take_profit_1),
    tp2: pnl !== null && pnl >= tpPct(prediction.take_profit_2),
    tp3: pnl !== null && pnl >= tpPct(prediction.take_profit_3),
    sl: pnl !== null && pnl <= -slPct,
  };

  const createdAt = new Date(prediction.created_at);
  const tfSeconds: Record<string, number> = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
  };
  const totalSec = prediction.horizon_candles * (tfSeconds[prediction.timeframe] || 3600);
  const elapsedMs = Date.now() - createdAt.getTime();
  const elapsedSec = elapsedMs / 1000;
  const remainHours = Math.max(0, (totalSec - elapsedSec) / 3600);

  return (
    <div className="rounded-lg border border-border bg-body overflow-hidden">
      {/* 헤더: 방향 + 신뢰도 + 초기화 버튼 */}
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
        <div className="flex items-center gap-2">
          {prediction.auto_generated && (
            <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">Auto</span>
          )}
          {onExpire && (
            <button
              onClick={() => onExpire(prediction.id)}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium text-muted hover:text-danger hover:bg-danger/10 transition-colors"
              title="예측 초기화"
            >
              <RotateCcw size={12} />
              초기화
            </button>
          )}
        </div>
      </div>

      {/* 예측 시작 시간 + 경과 시간 */}
      <div className="px-4 py-2.5 border-b border-card-active bg-card/50 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-muted">
          <Clock size={12} />
          <span>시작: <span className="text-heading font-medium">{formatDateTime(prediction.created_at)}</span></span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-muted">
            경과: <span className="text-heading font-medium">{formatElapsed(elapsedMs)}</span>
          </span>
          <span className="text-muted">
            남은: <span className="text-heading font-medium">{remainHours < 1 ? `${(remainHours * 60).toFixed(0)}분` : `${remainHours.toFixed(1)}h`}</span>
          </span>
        </div>
      </div>

      {/* 예측 적중률 (경로 정확도) — 강조 표시 */}
      {pathAcc !== null && (
        <div className="px-4 py-3 border-b border-card-active">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <Crosshair size={14} style={{ color: getAccuracyColor(pathAcc) }} />
              <span className="text-xs font-medium text-heading">예측 적중률</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{
                  color: getAccuracyColor(pathAcc),
                  backgroundColor: `color-mix(in srgb, ${getAccuracyColor(pathAcc)} 12%, transparent)`,
                }}
              >
                {getAccuracyLabel(pathAcc)}
              </span>
              <span className="text-lg font-bold" style={{ color: getAccuracyColor(pathAcc) }}>
                {(pathAcc * 100).toFixed(1)}%
              </span>
            </div>
          </div>
          <div className="w-full h-2 bg-card-active rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${pathAcc * 100}%`,
                backgroundColor: getAccuracyColor(pathAcc),
              }}
            />
          </div>
          <p className="text-[10px] text-muted mt-1">
            예측한 가격 경로와 실제 가격이 얼마나 일치하는지 나타냅니다
          </p>
        </div>
      )}

      {/* 가격 정보 */}
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

      {/* 지표 4개 */}
      <div className="px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricBox
          label="P&L"
          value={pnl !== null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}%` : "-"}
          color={pnl !== null ? (pnl >= 0 ? "var(--success-text)" : "var(--short)") : "var(--text-body)"}
          icon={<Activity size={12} />}
        />
        <MetricBox
          label="R:R"
          value={rr !== null ? `${rr.toFixed(1)}x` : "-"}
          color="var(--primary)"
          icon={<Target size={12} />}
        />
        <MetricBox
          label="적중률"
          value={pathAcc !== null ? `${(pathAcc * 100).toFixed(0)}%` : "-"}
          color={pathAcc !== null ? getAccuracyColor(pathAcc) : "var(--text-body)"}
          icon={<Crosshair size={12} />}
        />
        <MetricBox
          label="남은 시간"
          value={remainHours < 1 ? `${(remainHours * 60).toFixed(0)}m` : `${remainHours.toFixed(1)}h`}
          color="var(--text-body)"
          icon={<Clock size={12} />}
        />
      </div>

      {/* 시간 진행 바 */}
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
                width: `${Math.min(timePct * 100, 100)}%`,
                backgroundColor: timePct > 0.8 ? "var(--warning)" : "var(--primary)",
              }}
            />
          </div>
        </div>
      )}

      {/* TP/SL 체크 */}
      <div className="px-4 py-2 border-t border-card-active flex items-center gap-3 text-xs">
        <CheckItem label="TP1" hit={tpChecks.tp1} color="var(--long)" />
        <CheckItem label="TP2" hit={tpChecks.tp2} color="var(--long)" />
        <CheckItem label="TP3" hit={tpChecks.tp3} color="var(--long)" />
        <CheckItem label="SL" hit={tpChecks.sl} color="var(--short)" />
      </div>
    </div>
  );
}

function MetricBox({ label, value, color, icon }: { label: string; value: string; color: string; icon?: React.ReactNode }) {
  return (
    <div className="text-center">
      <div className="flex items-center justify-center gap-1 text-xs text-muted mb-0.5">
        {icon}
        {label}
      </div>
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

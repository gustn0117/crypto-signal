"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useWebSocket } from "@/hooks/useWebSocket";
import { usePredictionsPage, PredictionFilters } from "@/hooks/usePredictionsPage";
import { Prediction, PredictionDashboardStats } from "@/lib/api";
import { formatPrice, timeAgo } from "@/lib/utils";
import SignalBadge from "@/components/SignalBadge";
import {
  Target,
  TrendingUp,
  TrendingDown,
  Clock,
  Trophy,
  Filter,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  BarChart3,
  Activity,
} from "lucide-react";

// ─── 결과 컬러/아이콘 (PredictionDashboardWidget 패턴) ────
const RESULT_COLORS: Record<string, string> = {
  HIT_TP3: "var(--long)",
  HIT_TP2: "var(--long)",
  HIT_TP1: "var(--long)",
  PARTIAL: "var(--warning)",
  NEUTRAL: "var(--text-muted)",
  HIT_SL: "var(--short)",
  WRONG: "var(--short)",
};
const RESULT_LABELS: Record<string, string> = {
  HIT_TP3: "TP3 도달",
  HIT_TP2: "TP2 도달",
  HIT_TP1: "TP1 도달",
  PARTIAL: "일부 달성",
  NEUTRAL: "중립",
  HIT_SL: "SL 도달",
  WRONG: "실패",
};

const TF_OPTIONS = ["", "1m", "5m", "15m", "30m", "1h", "4h", "1d"];
const DIR_OPTIONS = ["", "STRONG_LONG", "LONG", "SHORT", "STRONG_SHORT"];
const RESULT_OPTIONS = ["", "HIT_TP3", "HIT_TP2", "HIT_TP1", "PARTIAL", "NEUTRAL", "HIT_SL", "WRONG"];

export default function PredictionsPage() {
  const ws = useWebSocket();
  const {
    activePredictions,
    historyPredictions,
    historyTotal,
    dashboardStats,
    loading,
    activeLoading,
    historyLoading,
    filters,
    setFilters,
    page,
    setPage,
    pageSize,
    applyProgress,
    applyCreated,
    applyVerified,
    reload,
  } = usePredictionsPage();

  const [tab, setTab] = useState<"active" | "history" | "analysis">("active");

  // ─── WebSocket 이벤트 연동 ───────────────────────────
  useEffect(() => {
    if (ws.predictionProgress.length > 0) {
      applyProgress(ws.predictionProgress);
    }
  }, [ws.predictionProgress, applyProgress]);

  useEffect(() => {
    if (ws.predictionCreated) {
      applyCreated(ws.predictionCreated);
      ws.clearPredictionCreated();
    }
  }, [ws.predictionCreated, applyCreated, ws.clearPredictionCreated]);

  useEffect(() => {
    if (ws.predictionVerified) {
      applyVerified(ws.predictionVerified);
      ws.clearPredictionVerified();
    }
  }, [ws.predictionVerified, applyVerified, ws.clearPredictionVerified]);

  if (loading) {
    return (
      <div className="p-4 lg:p-6 space-y-4">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-card-active rounded w-48" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-20 bg-card-active rounded-lg" />
            ))}
          </div>
          <div className="h-64 bg-card-active rounded-lg" />
        </div>
      </div>
    );
  }

  const totalPages = Math.ceil(historyTotal / pageSize);

  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* ─── 헤더 ────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Target size={22} className="text-primary" />
          <h1 className="text-lg font-bold text-heading">예측 관리</h1>
          {activePredictions.length > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
              {activePredictions.length} 활성
            </span>
          )}
        </div>
        <button
          onClick={reload}
          className="p-2 rounded-card text-icon-muted hover:text-heading hover:bg-card-active transition-colors"
          title="새로고침"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* ─── 요약 통계 ──────────────────────────────────── */}
      {dashboardStats && dashboardStats.total_predictions > 0 && (
        <StatsBar stats={dashboardStats} />
      )}

      {/* ─── 탭 ────────────────────────────────────────── */}
      <div className="flex gap-1 border-b border-border">
        {[
          { key: "active" as const, label: "활성 예측", icon: Activity, count: activePredictions.length },
          { key: "history" as const, label: "히스토리", icon: Clock },
          { key: "analysis" as const, label: "분석", icon: BarChart3 },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t.key
                ? "text-primary border-primary"
                : "text-muted border-transparent hover:text-heading"
            }`}
          >
            <t.icon size={14} />
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-primary/10 text-primary ml-1">
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ─── 활성 예측 탭 ────────────────────────────────── */}
      {tab === "active" && (
        <ActiveTab predictions={activePredictions} loading={activeLoading} />
      )}

      {/* ─── 히스토리 탭 ─────────────────────────────────── */}
      {tab === "history" && (
        <HistoryTab
          predictions={historyPredictions}
          total={historyTotal}
          loading={historyLoading}
          filters={filters}
          setFilters={setFilters}
          page={page}
          setPage={setPage}
          totalPages={totalPages}
        />
      )}

      {/* ─── 분석 탭 ─────────────────────────────────────── */}
      {tab === "analysis" && (
        <AnalysisTab stats={dashboardStats} />
      )}
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 요약 통계 바
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function StatsBar({ stats }: { stats: PredictionDashboardStats }) {
  const items = [
    { label: "총 예측", value: String(stats.total_predictions) },
    { label: "활성", value: String(stats.active_predictions), color: "var(--primary)" },
    {
      label: "승률",
      value: `${(stats.win_rate * 100).toFixed(0)}%`,
      color: stats.win_rate >= 0.5 ? "var(--success-text)" : "var(--danger)",
    },
    {
      label: "평균 정확도",
      value: `${(stats.avg_accuracy * 100).toFixed(0)}%`,
      color: "var(--warning)",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {items.map((item) => (
        <div key={item.label} className="cd-card p-3 text-center">
          <div className="text-xs text-muted mb-1">{item.label}</div>
          <div className="text-xl font-bold" style={{ color: item.color || "var(--heading)" }}>
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 활성 예측 탭
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function ActiveTab({ predictions, loading }: { predictions: Prediction[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-48 animate-pulse bg-card-active rounded-lg" />
        ))}
      </div>
    );
  }

  if (predictions.length === 0) {
    return (
      <div className="cd-card p-8 text-center">
        <Target size={40} className="mx-auto text-muted mb-3 opacity-50" />
        <p className="text-muted text-sm">현재 활성 예측이 없습니다.</p>
        <p className="text-xs text-muted mt-1">코인 상세 페이지에서 예측을 생성할 수 있습니다.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {predictions.map((p) => (
        <ActivePredictionCard key={p.id} prediction={p} />
      ))}
    </div>
  );
}

function ActivePredictionCard({ prediction }: { prediction: Prediction }) {
  const isLong = prediction.signal_direction.includes("LONG");
  const pnl = prediction.progress_pnl_pct;
  const rr = prediction.progress_rr_current;
  const timePct = prediction.progress_time_pct;
  const pathAcc = prediction.progress_path_accuracy;
  const symbolShort = prediction.symbol.replace("/USDT", "");

  const tfSeconds: Record<string, number> = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
  };
  const totalSec = prediction.horizon_candles * (tfSeconds[prediction.timeframe] || 3600);
  const elapsedSec = (Date.now() - new Date(prediction.created_at).getTime()) / 1000;
  const remainHours = Math.max(0, (totalSec - elapsedSec) / 3600);

  return (
    <Link
      href={`/coin/${prediction.symbol.replace("/", "")}`}
      className="cd-card p-0 overflow-hidden hover:border-primary/30 transition-colors block"
    >
      {/* 헤더: 심볼 + 방향 + 신뢰도 */}
      <div className="px-4 py-3 bg-card border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-heading">{symbolShort}</span>
          <span className="text-xs text-muted">{prediction.timeframe}</span>
        </div>
        <div className="flex items-center gap-2">
          {isLong ? (
            <TrendingUp size={14} className="text-success" />
          ) : (
            <TrendingDown size={14} className="text-danger" />
          )}
          <span className={`text-xs font-bold ${isLong ? "text-success" : "text-danger"}`}>
            {prediction.signal_direction.replace("STRONG_", "S.")}
          </span>
          <span className="text-xs text-muted">
            {(prediction.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* 가격 정보 */}
      <div className="px-4 py-2 border-b border-card-active text-xs flex items-center justify-between">
        <span>
          <span className="text-muted">진입 </span>
          <span className="text-heading font-mono">${formatPrice(prediction.entry_price)}</span>
        </span>
        <span>
          <span className="text-danger">SL </span>
          <span className="font-mono">${formatPrice(prediction.stop_loss)}</span>
        </span>
        <span className="text-success font-mono">
          TP1 ${formatPrice(prediction.take_profit_1)}
        </span>
      </div>

      {/* 매트릭스 */}
      <div className="px-4 py-3 grid grid-cols-4 gap-2 text-center">
        <div>
          <div className="text-[10px] text-muted">P&L</div>
          <div
            className="text-sm font-bold"
            style={{ color: pnl !== null ? (pnl >= 0 ? "var(--success-text)" : "var(--short)") : "var(--text-body)" }}
          >
            {pnl !== null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}%` : "-"}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-muted">R:R</div>
          <div className="text-sm font-bold" style={{ color: "var(--primary)" }}>
            {rr !== null ? `${rr.toFixed(1)}x` : "-"}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-muted">경로</div>
          <div className="text-sm font-bold" style={{ color: "var(--warning)" }}>
            {pathAcc !== null ? `${(pathAcc * 100).toFixed(0)}%` : "-"}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-muted">남은시간</div>
          <div className="text-sm font-bold text-body-text">
            {remainHours.toFixed(1)}h
          </div>
        </div>
      </div>

      {/* 시간 진행 바 */}
      {timePct !== null && (
        <div className="px-4 pb-3">
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
    </Link>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 히스토리 탭
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function HistoryTab({
  predictions,
  total,
  loading,
  filters,
  setFilters,
  page,
  setPage,
  totalPages,
}: {
  predictions: Prediction[];
  total: number;
  loading: boolean;
  filters: PredictionFilters;
  setFilters: (f: PredictionFilters) => void;
  page: number;
  setPage: (p: number) => void;
  totalPages: number;
}) {
  return (
    <div className="space-y-4">
      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter size={14} className="text-muted" />
        <FilterSelect
          value={filters.direction || ""}
          onChange={(v) => setFilters({ ...filters, direction: v || undefined })}
          options={DIR_OPTIONS}
          labels={{ "": "방향 전체", STRONG_LONG: "강한 롱", LONG: "롱", SHORT: "숏", STRONG_SHORT: "강한 숏" }}
        />
        <FilterSelect
          value={filters.timeframe || ""}
          onChange={(v) => setFilters({ ...filters, timeframe: v || undefined })}
          options={TF_OPTIONS}
          labels={{ "": "타임프레임 전체" }}
        />
        <FilterSelect
          value={filters.result || ""}
          onChange={(v) => setFilters({ ...filters, result: v || undefined })}
          options={RESULT_OPTIONS}
          labels={{
            "": "결과 전체",
            HIT_TP3: "TP3", HIT_TP2: "TP2", HIT_TP1: "TP1",
            PARTIAL: "일부 달성", NEUTRAL: "중립", HIT_SL: "SL", WRONG: "실패",
          }}
        />
        <span className="text-xs text-muted ml-auto">총 {total}건</span>
      </div>

      {/* 테이블 */}
      <div className="cd-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-card text-xs text-muted border-b border-border">
                <th className="text-left px-4 py-2.5 font-medium">시간</th>
                <th className="text-left px-4 py-2.5 font-medium">코인</th>
                <th className="text-center px-4 py-2.5 font-medium">TF</th>
                <th className="text-center px-4 py-2.5 font-medium">방향</th>
                <th className="text-center px-4 py-2.5 font-medium">신뢰도</th>
                <th className="text-right px-4 py-2.5 font-medium">진입가</th>
                <th className="text-center px-4 py-2.5 font-medium">결과</th>
                <th className="text-center px-4 py-2.5 font-medium">정확도</th>
                <th className="text-center px-4 py-2.5 font-medium">MFE</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="border-t border-card-active">
                    {Array.from({ length: 9 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 bg-card-active rounded animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : predictions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-muted text-sm">
                    조건에 맞는 예측이 없습니다.
                  </td>
                </tr>
              ) : (
                predictions.map((p) => (
                  <HistoryRow key={p.id} prediction={p} />
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* 페이지네이션 */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-card bg-card-active text-body-text hover:text-heading disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={14} /> 이전
            </button>
            <span className="text-xs text-muted">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-card bg-card-active text-body-text hover:text-heading disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              다음 <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function HistoryRow({ prediction }: { prediction: Prediction }) {
  const isLong = prediction.signal_direction.includes("LONG");
  const symbolShort = prediction.symbol.replace("/USDT", "");
  const resultColor = RESULT_COLORS[prediction.result || ""] || "var(--text-muted)";
  const resultLabel = RESULT_LABELS[prediction.result || ""] || prediction.result || "-";

  return (
    <tr className="border-t border-card-active hover:bg-card-active/50 transition-colors">
      <td className="px-4 py-2.5 text-xs text-muted whitespace-nowrap">
        {timeAgo(prediction.created_at)}
      </td>
      <td className="px-4 py-2.5">
        <Link
          href={`/coin/${prediction.symbol.replace("/", "")}`}
          className="text-heading font-medium hover:text-primary transition-colors"
        >
          {symbolShort}
        </Link>
      </td>
      <td className="px-4 py-2.5 text-center text-xs text-muted">{prediction.timeframe}</td>
      <td className="px-4 py-2.5 text-center">
        <SignalBadge signal={prediction.signal_direction} size="sm" />
      </td>
      <td className="px-4 py-2.5 text-center text-xs">
        {(prediction.confidence * 100).toFixed(0)}%
      </td>
      <td className="px-4 py-2.5 text-right text-xs font-mono text-heading">
        ${formatPrice(prediction.entry_price)}
      </td>
      <td className="px-4 py-2.5 text-center">
        {prediction.result ? (
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{
              color: resultColor,
              backgroundColor: `color-mix(in srgb, ${resultColor} 12%, transparent)`,
            }}
          >
            {resultLabel}
          </span>
        ) : (
          <span className="text-xs text-muted">-</span>
        )}
      </td>
      <td className="px-4 py-2.5 text-center text-xs">
        {prediction.accuracy_score !== null
          ? `${(prediction.accuracy_score * 100).toFixed(0)}%`
          : "-"}
      </td>
      <td className="px-4 py-2.5 text-center text-xs">
        {prediction.max_favorable !== null
          ? `${prediction.max_favorable >= 0 ? "+" : ""}${prediction.max_favorable.toFixed(2)}%`
          : "-"}
      </td>
    </tr>
  );
}

function FilterSelect({
  value,
  onChange,
  options,
  labels,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  labels: Record<string, string>;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="text-xs px-2.5 py-1.5 rounded-card bg-card border border-border text-body-text focus:outline-none focus:border-primary"
    >
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {labels[opt] || opt}
        </option>
      ))}
    </select>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 분석 탭
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function AnalysisTab({ stats }: { stats: PredictionDashboardStats | null }) {
  if (!stats || stats.total_predictions === 0) {
    return (
      <div className="cd-card p-8 text-center">
        <BarChart3 size={40} className="mx-auto text-muted mb-3 opacity-50" />
        <p className="text-muted text-sm">분석할 예측 데이터가 아직 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* 코인별 정확도 리더보드 */}
      {stats.leaderboard.length > 0 && (
        <div className="cd-card p-0 overflow-hidden">
          <div className="cd-card-header flex items-center gap-2">
            <Trophy size={16} className="text-warning" />
            <h3 className="font-semibold text-sm text-heading">코인별 정확도 순위</h3>
          </div>
          <div className="p-4">
            <div className="space-y-2">
              {stats.leaderboard.map((item, i) => {
                const pct = item.avg_acc * 100;
                return (
                  <div key={item.symbol} className="flex items-center gap-3">
                    <span
                      className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                      style={{
                        backgroundColor:
                          i === 0
                            ? "var(--warning)"
                            : i === 1
                            ? "var(--text-muted)"
                            : i === 2
                            ? "#cd7f32"
                            : "var(--card-active)",
                        color: i < 3 ? "#fff" : "var(--text-body)",
                      }}
                    >
                      {i + 1}
                    </span>
                    <Link
                      href={`/coin/${item.symbol.replace("/", "")}`}
                      className="text-sm font-medium text-heading hover:text-primary transition-colors w-20"
                    >
                      {item.symbol.replace("/USDT", "")}
                    </Link>
                    <div className="flex-1 h-2 bg-card-active rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${pct}%`,
                          backgroundColor:
                            pct >= 70
                              ? "var(--success-text)"
                              : pct >= 50
                              ? "var(--warning)"
                              : "var(--danger)",
                        }}
                      />
                    </div>
                    <span className="text-xs font-mono text-heading w-12 text-right">
                      {pct.toFixed(0)}%
                    </span>
                    <span className="text-xs text-muted w-12 text-right">
                      {item.wins}승
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 최근 결과 스트릭 */}
      {stats.recent_results.length > 0 && (
        <div className="cd-card p-0 overflow-hidden">
          <div className="cd-card-header flex items-center gap-2">
            <Clock size={16} className="text-muted" />
            <h3 className="font-semibold text-sm text-heading">최근 결과</h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {stats.recent_results.map((item, i) => {
                const color = RESULT_COLORS[item.result] || "var(--text-muted)";
                const label = RESULT_LABELS[item.result] || item.result;
                return (
                  <div
                    key={i}
                    className="rounded-card p-3 border border-border"
                    style={{
                      borderLeftWidth: 3,
                      borderLeftColor: color,
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <Link
                        href={`/coin/${item.symbol.replace("/", "")}`}
                        className="text-sm font-medium text-heading hover:text-primary transition-colors"
                      >
                        {item.symbol.replace("/USDT", "")}
                      </Link>
                      <span
                        className="text-xs font-bold"
                        style={{ color }}
                      >
                        {label}
                      </span>
                    </div>
                    <div className="text-xs text-muted">
                      정확도: {(item.accuracy_score * 100).toFixed(0)}%
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 전체 통계 요약 */}
      <div className="cd-card p-0 overflow-hidden lg:col-span-2">
        <div className="cd-card-header flex items-center gap-2">
          <BarChart3 size={16} className="text-primary" />
          <h3 className="font-semibold text-sm text-heading">전체 통계</h3>
        </div>
        <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatBlock label="총 예측" value={String(stats.total_predictions)} />
          <StatBlock
            label="활성 예측"
            value={String(stats.active_predictions)}
            color="var(--primary)"
          />
          <StatBlock
            label="승률"
            value={`${(stats.win_rate * 100).toFixed(1)}%`}
            color={stats.win_rate >= 0.5 ? "var(--success-text)" : "var(--danger)"}
          />
          <StatBlock
            label="평균 정확도"
            value={`${(stats.avg_accuracy * 100).toFixed(1)}%`}
            color="var(--warning)"
          />
        </div>
      </div>
    </div>
  );
}

function StatBlock({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="p-4 rounded-lg bg-card-active text-center">
      <div className="text-xs text-muted mb-2">{label}</div>
      <div className="text-2xl font-bold" style={{ color: color || "var(--heading)" }}>
        {value}
      </div>
    </div>
  );
}

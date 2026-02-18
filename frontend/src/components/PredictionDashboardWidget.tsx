"use client";

import { useState, useEffect } from "react";
import { PredictionDashboardStats, fetchPredictionDashboard } from "@/lib/api";
import { BarChart3, Trophy, Clock } from "lucide-react";

const RESULT_COLORS: Record<string, string> = {
  HIT_TP3: "#26dad2",
  HIT_TP2: "#26dad2",
  HIT_TP1: "#26dad2",
  PARTIAL: "#ffb22b",
  NEUTRAL: "#abafb3",
  HIT_SL: "#ef5350",
  WRONG: "#ef5350",
};

const RESULT_ICONS: Record<string, string> = {
  HIT_TP3: "TP3",
  HIT_TP2: "TP2",
  HIT_TP1: "TP1",
  PARTIAL: "P",
  NEUTRAL: "-",
  HIT_SL: "SL",
  WRONG: "X",
};

export default function PredictionDashboardWidget() {
  const [stats, setStats] = useState<PredictionDashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchPredictionDashboard();
        setStats(data);
      } catch (error) {
        console.error("대시보드 통계 로드 실패:", error);
      } finally {
        setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-body p-4 animate-pulse">
        <div className="h-4 bg-card-active rounded w-1/3 mb-3" />
        <div className="h-8 bg-card-active rounded mb-2" />
        <div className="h-8 bg-card-active rounded" />
      </div>
    );
  }

  if (!stats || stats.total_predictions === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-body overflow-hidden">
      {/* 헤더 */}
      <div className="px-4 py-3 bg-card border-b border-border flex items-center gap-2">
        <BarChart3 size={16} className="text-primary" />
        <h3 className="font-semibold text-sm text-heading">예측 시스템</h3>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-4 gap-px bg-card-active">
        <StatCell label="총 예측" value={String(stats.total_predictions)} />
        <StatCell label="활성" value={String(stats.active_predictions)} color="#4680ff" />
        <StatCell
          label="승률"
          value={`${(stats.win_rate * 100).toFixed(0)}%`}
          color={stats.win_rate >= 0.5 ? "#4caf50" : "#ef5350"}
        />
        <StatCell
          label="평균 정확도"
          value={`${(stats.avg_accuracy * 100).toFixed(0)}%`}
          color="#ffb22b"
        />
      </div>

      {/* 리더보드 */}
      {stats.leaderboard.length > 0 && (
        <div className="px-4 py-3 border-t border-card-active">
          <div className="flex items-center gap-1 mb-2">
            <Trophy size={12} className="text-warning" />
            <span className="text-xs text-muted">정확도 순위</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {stats.leaderboard.slice(0, 5).map((item, i) => (
              <span
                key={item.symbol}
                className="text-xs px-2 py-1 rounded bg-card border border-card-active"
              >
                <span className="text-warning">{i + 1}.</span>{" "}
                <span className="text-heading font-medium">{item.symbol.replace("/USDT", "")}</span>{" "}
                <span className="text-success">{(item.avg_acc * 100).toFixed(0)}%</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 최근 결과 */}
      {stats.recent_results.length > 0 && (
        <div className="px-4 py-3 border-t border-card-active">
          <div className="flex items-center gap-1 mb-2">
            <Clock size={12} className="text-muted" />
            <span className="text-xs text-muted">최근 결과</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {stats.recent_results.slice(0, 6).map((item, i) => {
              const color = RESULT_COLORS[item.result] || "#abafb3";
              const icon = RESULT_ICONS[item.result] || "?";
              return (
                <span
                  key={i}
                  className="text-xs px-2 py-1 rounded flex items-center gap-1"
                  style={{ backgroundColor: `${color}15`, color }}
                >
                  <span className="font-medium">{item.symbol.replace("/USDT", "")}</span>
                  <span className="font-bold">{icon}</span>
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCell({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-body p-3 text-center">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-lg font-bold" style={{ color: color || "#ffffff" }}>{value}</div>
    </div>
  );
}

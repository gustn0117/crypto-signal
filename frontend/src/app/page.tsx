"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Signal, Candle, analyzeSymbol, fetchOHLCV, scanMarket } from "@/lib/api";
import { useWS } from "@/components/ClientLayout";
import CandleChart from "@/components/CandleChart";
import SignalTable from "@/components/SignalTable";
import AnalysisPanel from "@/components/AnalysisPanel";
import TimeframeSelector from "@/components/TimeframeSelector";
import PredictionDashboardWidget from "@/components/PredictionDashboardWidget";
import { ChartSkeleton, AnalysisSkeleton } from "@/components/Skeleton";
import {
  ExternalLink,
  CheckCircle,
  Eye,
  ArrowUpDown,
  Activity,
  BarChart3,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export default function Dashboard() {
  const { signals: wsSignals } = useWS();

  const [signals, setSignals] = useState<Signal[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>("");
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [timeframe, setTimeframe] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    if (wsSignals.length > 0) {
      setSignals(wsSignals);
    }
  }, [wsSignals]);

  const handleSelectSymbol = useCallback(
    async (symbol: string) => {
      setSelectedSymbol(symbol);
      setLoading(true);
      try {
        const [analysis, ohlcv] = await Promise.all([
          analyzeSymbol(symbol, timeframe),
          fetchOHLCV(symbol, timeframe),
        ]);
        setSelectedSignal(analysis);
        setCandles(ohlcv);
      } catch (error) {
        console.error("분석 실패:", error);
      } finally {
        setLoading(false);
      }
    },
    [timeframe]
  );

  const handleTimeframeChange = useCallback(
    async (tf: string) => {
      setTimeframe(tf);
      if (selectedSymbol) {
        setLoading(true);
        try {
          const [analysis, ohlcv] = await Promise.all([
            analyzeSymbol(selectedSymbol, tf),
            fetchOHLCV(selectedSymbol, tf),
          ]);
          setSelectedSignal(analysis);
          setCandles(ohlcv);
        } catch (error) {
          console.error("타임프레임 변경 실패:", error);
        } finally {
          setLoading(false);
        }
      }
    },
    [selectedSymbol]
  );

  const handleScan = useCallback(async () => {
    setScanning(true);
    try {
      const result = await scanMarket(timeframe);
      setSignals(result);
    } catch (error) {
      console.error("스캔 실패:", error);
    } finally {
      setScanning(false);
    }
  }, [timeframe]);

  return (
    <div className="space-y-6">
      {/* 상단 바 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold text-heading">대시보드</h2>
        <div className="flex items-center gap-3">
          <TimeframeSelector selected={timeframe} onChange={handleTimeframeChange} />
          <button
            onClick={handleScan}
            disabled={scanning}
            className="px-4 py-2 bg-primary hover:bg-primary/80 text-white text-sm font-medium rounded-card transition-colors disabled:opacity-50"
          >
            {scanning ? "스캔 중..." : "마켓 스캔"}
          </button>
        </div>
      </div>

      {/* 요약 카드 */}
      {signals.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <SummaryCard
            label="확정 시그널"
            count={signals.filter((s) => s.track?.state === "CONFIRMED").length}
            color="#26dad2"
            icon={CheckCircle}
          />
          <SummaryCard
            label="포착 중"
            count={signals.filter((s) => s.track?.state === "FORMING" || s.track?.state === "CONFIRMING").length}
            color="#ffb22b"
            icon={Eye}
          />
          <SummaryCard
            label="롱 / 숏"
            count={signals.filter((s) => s.signal.includes("LONG")).length}
            suffix={` / ${signals.filter((s) => s.signal.includes("SHORT")).length}`}
            color="#4680ff"
            icon={ArrowUpDown}
          />
          <SummaryCard
            label="활성 / 관망"
            count={signals.filter((s) => s.signal !== "NEUTRAL").length}
            suffix={` / ${signals.filter((s) => s.signal === "NEUTRAL").length}`}
            color="#abafb3"
            icon={Activity}
          />
        </div>
      )}

      {/* 메인 그리드 */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* 좌측: 시그널 테이블 */}
        <div className="xl:col-span-4 cd-card p-0 overflow-hidden">
          <div className="cd-card-header flex items-center justify-between">
            <span className="font-semibold text-heading">시그널 목록</span>
            <span className="text-xs text-muted">
              {signals.filter((s) => s.signal !== "NEUTRAL").length}개 활성
            </span>
          </div>
          <SignalTable
            signals={signals}
            onSelect={handleSelectSymbol}
            selectedSymbol={selectedSymbol}
          />
        </div>

        {/* 중앙: 차트 */}
        <div className="xl:col-span-4 space-y-5">
          {selectedSymbol ? (
            <div className="animate-fade-in">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-heading">{selectedSymbol}</span>
                <Link
                  href={`/coin/${selectedSymbol.replace("/", "")}`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-card text-xs font-medium text-primary bg-primary/10 hover:bg-primary/20 border border-primary/20 transition-colors"
                >
                  상세 분석
                  <ExternalLink size={12} />
                </Link>
              </div>
              {loading ? (
                <ChartSkeleton />
              ) : (
                <CandleChart candles={candles} symbol={selectedSymbol} />
              )}
            </div>
          ) : (
            <div className="h-[540px] cd-card flex items-center justify-center">
              <div className="text-center text-body-text">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-card-active flex items-center justify-center">
                  <BarChart3 size={28} className="text-icon-muted" />
                </div>
                <p className="text-base font-medium text-heading mb-1">코인을 선택하세요</p>
                <p className="text-sm text-muted">
                  왼쪽 목록에서 코인을 클릭하면 차트가 표시됩니다
                </p>
              </div>
            </div>
          )}

          {/* 예측 위젯 */}
          <PredictionDashboardWidget />
        </div>

        {/* 우측: 분석 패널 */}
        <div className="xl:col-span-4 cd-card p-0 overflow-hidden">
          <div className="cd-card-header">
            <span className="font-semibold text-heading">상세 분석</span>
          </div>
          {selectedSignal ? (
            <AnalysisPanel signal={selectedSignal} loading={loading} />
          ) : (
            <AnalysisSkeleton />
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  count,
  color,
  suffix,
  icon: Icon,
}: {
  label: string;
  count: number;
  color: string;
  suffix?: string;
  icon: LucideIcon;
}) {
  return (
    <div className="cd-card flex items-center gap-3">
      <div
        className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
        style={{ backgroundColor: `${color}15` }}
      >
        <Icon size={20} style={{ color }} />
      </div>
      <div className="min-w-0">
        <div className="text-xs text-muted mb-0.5 uppercase tracking-wider truncate">{label}</div>
        <div className="text-xl font-bold" style={{ color }}>
          {count}{suffix}
        </div>
      </div>
    </div>
  );
}

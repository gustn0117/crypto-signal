"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useCoinDetail } from "@/hooks/useCoinDetail";
import { useWS } from "@/components/ClientLayout";
import CandleChart from "@/components/CandleChart";
import CoinSearch from "@/components/CoinSearch";
import PriceHeader from "@/components/PriceHeader";
import IndicatorGauge from "@/components/IndicatorGauge";
import ConfidenceMeter from "@/components/ConfidenceMeter";
import SignalBadge from "@/components/SignalBadge";
import SignalStateBadge from "@/components/SignalStateBadge";
import TimeframeSelector from "@/components/TimeframeSelector";
import TradeParamsCard from "@/components/TradeParamsCard";
import MTFBadge from "@/components/MTFBadge";
import PredictionHistoryPanel from "@/components/PredictionHistoryPanel";
import PredictionInfoCard from "@/components/PredictionInfoCard";
import { ChartSkeleton } from "@/components/Skeleton";
import { usePrediction } from "@/hooks/usePrediction";
import { ArrowLeft, RefreshCw, TrendingUp, Clock, CheckCircle } from "lucide-react";

export default function CoinDetailPage() {
  const params = useParams();
  const symbol = params.symbol as string;

  const {
    signal,
    candles,
    ticker,
    timeframe,
    loading,
    lastRefresh,
    changeTimeframe,
    refresh,
  } = useCoinDetail(symbol);

  const {
    predictionCreated,
    predictionProgress,
    predictionVerified,
  } = useWS();

  const {
    activePrediction,
    predictions,
    stats: predictionStats,
    generating,
    generate,
    verify,
    reload: reloadPredictions,
  } = usePrediction(symbol, timeframe, {
    predictionCreated,
    predictionProgress,
    predictionVerified,
  });

  const displaySymbol = symbol.includes("/") ? symbol : symbol.replace("USDT", "/USDT");

  return (
    <div className="space-y-6">
      {/* 페이지 타이틀 바 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="p-2 rounded-card text-icon-muted hover:text-heading hover:bg-card-active transition-colors"
          >
            <ArrowLeft size={18} />
          </Link>
          <h2 className="text-lg font-semibold text-heading">{displaySymbol}</h2>
          <CoinSearch currentSymbol={symbol} />
        </div>
        <div className="flex items-center gap-3">
          <TimeframeSelector selected={timeframe} onChange={changeTimeframe} />
          <button
            onClick={refresh}
            className="p-2 rounded-card hover:bg-card-active text-icon-muted hover:text-heading transition-colors"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* 가격 헤더 */}
      <PriceHeader
        symbol={symbol}
        ticker={ticker}
        signal={signal}
        lastRefresh={lastRefresh}
      />

      {/* 차트 + 종합 판단 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* 캔들 차트 */}
        <div className="lg:col-span-8">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <button
                onClick={() => generate(24)}
                disabled={generating}
                className={`flex items-center gap-2 px-4 py-2 rounded-card text-sm font-medium transition-colors ${
                  generating
                    ? "bg-card-active text-muted cursor-not-allowed"
                    : "bg-primary/15 text-primary hover:bg-primary/25 border border-primary/20"
                }`}
              >
                <TrendingUp size={16} className={generating ? "animate-pulse" : ""} />
                {generating ? "예측 생성 중..." : "가격 예측"}
              </button>
              {activePrediction && (
                <div className="flex items-center gap-1.5 text-xs">
                  {activePrediction.status === "ACTIVE" ? (
                    <>
                      <Clock size={14} className="text-primary" />
                      <span className="text-primary">
                        예측 활성 ({activePrediction.signal_direction}, {(activePrediction.confidence * 100).toFixed(0)}%)
                      </span>
                    </>
                  ) : activePrediction.status === "VERIFIED" ? (
                    <>
                      <CheckCircle size={14} className="text-success" />
                      <span className="text-success">
                        검증 완료: {activePrediction.result}
                      </span>
                    </>
                  ) : null}
                </div>
              )}
            </div>
          </div>
          {loading && candles.length === 0 ? (
            <ChartSkeleton />
          ) : (
            <CandleChart candles={candles} symbol={displaySymbol} prediction={activePrediction} />
          )}
          {/* 활성 예측 실시간 추적 카드 */}
          {activePrediction && activePrediction.status === "ACTIVE" && (
            <div className="mt-4 animate-fade-in">
              <PredictionInfoCard prediction={activePrediction} />
            </div>
          )}
        </div>

        {/* 종합 판단 패널 */}
        <div className="lg:col-span-4 space-y-4">
          <div className={`p-5 rounded-card cd-card ${
            signal?.track?.state === "CONFIRMED"
              ? "!border-success/40"
              : ""
          }`}>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-4">
              종합 판단
            </h3>
            {signal?.track && (
              <div className="flex justify-center mb-3">
                <SignalStateBadge track={signal.track} size="md" showDetail />
              </div>
            )}
            {signal?.track?.state === "CONFIRMED" && (
              <div className="mb-4 px-3 py-2 rounded-card bg-success/10 border border-success/20 text-center">
                <span className="text-sm text-success font-medium">
                  시그널 확정 ({signal.track.consecutive_scans}회 연속
                  {signal.track.confirmed_at && `, ${getAgeText(signal.track.confirmed_at)} 확정`})
                </span>
              </div>
            )}
            <div className="flex items-center justify-center mb-4">
              <ConfidenceMeter
                confidence={signal?.confidence || 0}
                signal={signal?.signal || "NEUTRAL"}
              />
            </div>
            <div className="text-center mb-4">
              <SignalBadge
                signal={signal?.signal || "NEUTRAL"}
                confidence={signal?.confidence}
                size="lg"
              />
            </div>
            {signal?.mtf_confirmation && (
              <div className="mb-4">
                <MTFBadge mtf={signal.mtf_confirmation} />
              </div>
            )}
            {signal?.track && (
              <p className="text-xs text-muted text-center mb-3">
                {getAgeText(signal.track.first_detected_at)} 포착 | {signal.track.consecutive_scans}회 연속 확인
              </p>
            )}
            {signal?.summary && (
              <p className="text-sm text-body-text whitespace-pre-line leading-relaxed">
                {signal.summary}
              </p>
            )}
          </div>

          {signal?.trade_params && (
            <TradeParamsCard
              tradeParams={signal.trade_params}
              priceLevels={signal.price_levels}
            />
          )}

          {/* 가격 정보 카드 */}
          <div className="cd-card">
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
              가격 정보
            </h3>
            <div className="grid grid-cols-2 gap-2.5">
              <PriceStatItem label="현재가" value={`$${formatPrice(ticker?.price || 0)}`} />
              <PriceStatItem
                label="24h 변동"
                value={`${(ticker?.change_24h || 0) >= 0 ? "+" : ""}${(ticker?.change_24h || 0).toFixed(2)}%`}
                color={(ticker?.change_24h || 0) >= 0 ? "var(--success-text)" : "var(--danger)"}
              />
              <PriceStatItem label="매수호가" value={`$${formatPrice(ticker?.bid || 0)}`} />
              <PriceStatItem label="매도호가" value={`$${formatPrice(ticker?.ask || 0)}`} />
              <PriceStatItem label="24h 고가" value={`$${formatPrice(ticker?.high_24h || 0)}`} color="var(--success-text)" />
              <PriceStatItem label="24h 저가" value={`$${formatPrice(ticker?.low_24h || 0)}`} color="var(--danger)" />
            </div>
          </div>
        </div>
      </div>

      {/* 상세 분석 4열 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {[
          { title: "기술적 지표", weight: "35%", data: signal?.indicators, type: "indicator" },
          { title: "차트 패턴", weight: "30%", data: signal?.chart_patterns, type: "pattern" },
          { title: "캔들 패턴", weight: "15%", data: signal?.candle_patterns, type: "pattern" },
          { title: "거래량 분석", weight: "20%", data: signal?.volume_signals, type: "pattern" },
        ].map((section) => (
          <div key={section.title} className="cd-card p-0 overflow-hidden">
            <div className="cd-card-header flex items-center justify-between">
              <span className="font-semibold text-heading">{section.title}</span>
              <span className="text-xs text-muted">가중치 {section.weight}</span>
            </div>
            <div className="p-4 space-y-3">
              {section.data && section.data.length > 0 ? (
                section.type === "indicator" ? (
                  section.data.map((ind: any, i: number) => (
                    <IndicatorGauge key={i} indicator={ind} />
                  ))
                ) : (
                  section.data.map((p: any, i: number) => (
                    <PatternCard key={i} name={p.name} signal={p.signal} strength={p.strength} description={p.description} />
                  ))
                )
              ) : (
                <EmptyState text="데이터 없음" />
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 예측 히스토리 */}
      <PredictionHistoryPanel
        predictions={predictions}
        stats={predictionStats}
        onVerify={verify}
        onReload={reloadPredictions}
      />
    </div>
  );
}

function getAgeText(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "방금 전";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

function PriceStatItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="px-3 py-2 rounded-card bg-card-active">
      <div className="text-xs text-muted mb-0.5">{label}</div>
      <div className="text-sm font-mono font-semibold" style={{ color: color || "#ffffff" }}>
        {value}
      </div>
    </div>
  );
}

function PatternCard({ name, signal, strength, description }: { name: string; signal: string; strength: number; description: string }) {
  const color = signal === "long" ? "var(--long)" : signal === "short" ? "var(--short)" : "var(--text-muted)";
  const label = signal === "long" ? "LONG" : signal === "short" ? "SHORT" : "NEUTRAL";

  return (
    <div className="p-3 rounded-card bg-card-active border border-border">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-heading">{name}</span>
        <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{ color, backgroundColor: `${signal === "long" ? "rgba(38,218,210,0.12)" : signal === "short" ? "rgba(239,83,80,0.12)" : "rgba(171,175,179,0.1)"}` }}>
          {label}
        </span>
      </div>
      <div className="h-1.5 bg-body rounded-full overflow-hidden mb-2">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${strength * 100}%`, backgroundColor: color }} />
      </div>
      <p className="text-xs text-body-text leading-relaxed">{description}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center h-32 text-muted text-sm">
      {text}
    </div>
  );
}

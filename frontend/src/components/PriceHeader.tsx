"use client";

import { Signal, Ticker } from "@/lib/api";
import { formatPrice, formatVolume } from "@/lib/utils";
import SignalBadge from "./SignalBadge";

interface PriceHeaderProps {
  symbol: string;
  ticker: Ticker | null;
  signal: Signal | null;
  lastRefresh: string;
  loading?: boolean;
}

export default function PriceHeader({ symbol, ticker, signal, lastRefresh, loading }: PriceHeaderProps) {
  const displaySymbol = symbol.includes("/") ? symbol : symbol.replace("USDT", "/USDT");
  const price = ticker?.price || signal?.current_price || 0;
  const change = ticker?.change_24h || 0;
  const isPositive = change >= 0;

  if (loading) {
    return (
      <div className="cd-card animate-pulse">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-5">
            <div>
              <div className="h-6 w-32 bg-card-active rounded mb-2" />
              <div className="flex items-center gap-3">
                <div className="h-8 w-40 bg-card-active rounded" />
                <div className="h-6 w-16 bg-card-active rounded" />
              </div>
            </div>
            <div className="h-8 w-24 bg-card-active rounded-full" />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 lg:gap-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i}>
                <div className="h-3 w-16 bg-card-active rounded mb-1" />
                <div className="h-5 w-20 bg-card-active rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="cd-card">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div className="flex items-center gap-5">
          <div>
            <h2 className="text-xl font-bold text-heading mb-1">{displaySymbol}</h2>
            <div className="flex items-center gap-3">
              <span className="text-2xl font-bold text-heading font-mono">
                ${formatPrice(price)}
              </span>
              <span
                className={`text-base font-semibold ${
                  isPositive ? "text-success-text" : "text-danger"
                }`}
              >
                {isPositive ? "+" : ""}{change.toFixed(2)}%
              </span>
            </div>
          </div>

          {signal && (
            <SignalBadge signal={signal.signal} confidence={signal.confidence} size="lg" />
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 lg:gap-6">
          <StatItem label="24h 고가" value={`$${formatPrice(ticker?.high_24h || 0)}`} />
          <StatItem label="24h 저가" value={`$${formatPrice(ticker?.low_24h || 0)}`} />
          <StatItem label="24h 거래량" value={formatVolume(ticker?.volume_usdt || 0)} />
          {signal && (
            <StatItem
              label="신뢰도"
              value={`${(signal.confidence * 100).toFixed(0)}%`}
              color={signal.confidence >= 0.7 ? "var(--success-text)" : signal.confidence >= 0.4 ? "var(--warning)" : "var(--text-muted)"}
            />
          )}
        </div>
      </div>
      {lastRefresh && (
        <div className="text-xs text-muted mt-3 pt-3 border-t border-border">
          마지막 갱신: {new Date(lastRefresh).toLocaleTimeString("ko-KR")}
        </div>
      )}
    </div>
  );
}

function StatItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-xs text-muted mb-0.5">{label}</div>
      <div className="text-sm font-semibold font-mono" style={{ color: color || "var(--text-heading)" }}>
        {value}
      </div>
    </div>
  );
}

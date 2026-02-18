"use client";

import { Signal, Ticker } from "@/lib/api";
import SignalBadge from "./SignalBadge";

interface PriceHeaderProps {
  symbol: string;
  ticker: Ticker | null;
  signal: Signal | null;
  lastRefresh: string;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

function formatVolume(vol: number): string {
  if (vol >= 1_000_000_000) return `$${(vol / 1_000_000_000).toFixed(2)}B`;
  if (vol >= 1_000_000) return `$${(vol / 1_000_000).toFixed(2)}M`;
  if (vol >= 1_000) return `$${(vol / 1_000).toFixed(2)}K`;
  return `$${vol.toFixed(0)}`;
}

export default function PriceHeader({ symbol, ticker, signal, lastRefresh }: PriceHeaderProps) {
  const displaySymbol = symbol.includes("/") ? symbol : symbol.replace("USDT", "/USDT");
  const price = ticker?.price || signal?.current_price || 0;
  const change = ticker?.change_24h || 0;
  const isPositive = change >= 0;

  return (
    <div className="p-5 rounded-lg border border-border bg-body">
      <div className="flex items-center justify-between">
        {/* 왼쪽: 심볼 + 가격 */}
        <div className="flex items-center gap-6">
          <div>
            <h2 className="text-2xl font-bold text-heading">{displaySymbol}</h2>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-3xl font-bold text-heading">
                ${formatPrice(price)}
              </span>
              <span
                className={`text-lg font-semibold ${
                  isPositive ? "text-success" : "text-danger"
                }`}
              >
                {isPositive ? "+" : ""}{change.toFixed(2)}%
              </span>
            </div>
          </div>

          {/* 시그널 배지 */}
          {signal && (
            <div className="ml-4">
              <SignalBadge signal={signal.signal} confidence={signal.confidence} size="lg" />
            </div>
          )}
        </div>

        {/* 오른쪽: 24h 통계 */}
        <div className="flex items-center gap-6">
          <StatItem label="24h 고가" value={`$${formatPrice(ticker?.high_24h || 0)}`} />
          <StatItem label="24h 저가" value={`$${formatPrice(ticker?.low_24h || 0)}`} />
          <StatItem label="24h 거래량" value={formatVolume(ticker?.volume_usdt || 0)} />
          {signal && (
            <StatItem
              label="신뢰도"
              value={`${(signal.confidence * 100).toFixed(0)}%`}
              color={signal.confidence >= 0.7 ? "#4caf50" : signal.confidence >= 0.4 ? "#ffb22b" : "#abafb3"}
            />
          )}
          {lastRefresh && (
            <div className="text-xs text-muted">
              {new Date(lastRefresh).toLocaleTimeString("ko-KR")} 갱신
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-center">
      <div className="text-xs text-muted mb-0.5">{label}</div>
      <div className="text-sm font-semibold" style={{ color: color || "#ffffff" }}>
        {value}
      </div>
    </div>
  );
}

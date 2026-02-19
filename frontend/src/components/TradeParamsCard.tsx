"use client";

import Link from "next/link";
import { TradeParamsData, PriceLevelsData } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { Wallet } from "lucide-react";

interface TradeParamsCardProps {
  tradeParams: TradeParamsData;
  priceLevels?: PriceLevelsData;
  symbol?: string;
}

export default function TradeParamsCard({ tradeParams, priceLevels, symbol }: TradeParamsCardProps) {
  const isLong = tradeParams.position_direction === "long";
  const dirColor = isLong ? "var(--long)" : "var(--short)";
  const dirLabel = isLong ? "LONG" : "SHORT";

  const entry = tradeParams.entry_price;
  const sl = tradeParams.stop_loss;
  const riskDist = Math.abs(entry - sl);

  const calcRR = (tp: number) =>
    riskDist > 0 ? `${(Math.abs(tp - entry) / riskDist).toFixed(1)}:1` : "";

  const levels = isLong
    ? [
        { label: "TP3", price: tradeParams.take_profit_3, color: "var(--long)", rr: calcRR(tradeParams.take_profit_3) },
        { label: "TP2", price: tradeParams.take_profit_2, color: "var(--long)", rr: calcRR(tradeParams.take_profit_2) },
        { label: "TP1", price: tradeParams.take_profit_1, color: "var(--long)", rr: calcRR(tradeParams.take_profit_1) },
        { label: "Entry", price: entry, color: "var(--primary)", rr: "" },
        { label: "SL", price: sl, color: "var(--short)", rr: "" },
      ]
    : [
        { label: "SL", price: sl, color: "var(--short)", rr: "" },
        { label: "Entry", price: entry, color: "var(--primary)", rr: "" },
        { label: "TP1", price: tradeParams.take_profit_1, color: "var(--long)", rr: calcRR(tradeParams.take_profit_1) },
        { label: "TP2", price: tradeParams.take_profit_2, color: "var(--long)", rr: calcRR(tradeParams.take_profit_2) },
        { label: "TP3", price: tradeParams.take_profit_3, color: "var(--long)", rr: calcRR(tradeParams.take_profit_3) },
      ];

  return (
    <div className="p-4 rounded-lg border border-border bg-body">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">
          트레이드 파라미터
        </h3>
        <span
          className="text-xs font-bold px-2 py-0.5 rounded"
          style={{ color: dirColor, backgroundColor: `color-mix(in srgb, ${dirColor} 12%, transparent)` }}
        >
          {dirLabel}
        </span>
      </div>

      <div className="space-y-0">
        {levels.map((level, i) => (
          <div key={level.label} className="flex items-center gap-3 py-1.5">
            <span
              className="text-xs font-bold w-10 text-right shrink-0"
              style={{ color: level.color }}
            >
              {level.label}
            </span>
            <div className="flex flex-col items-center shrink-0">
              <div
                className="w-3 h-3 rounded-full border-2"
                style={{ borderColor: level.color, backgroundColor: level.label === "Entry" ? level.color : "transparent" }}
              />
              {i < levels.length - 1 && (
                <div className="w-px h-3 bg-border" />
              )}
            </div>
            <span className="text-sm font-mono text-heading flex-1">
              ${formatPrice(level.price)}
            </span>
            {level.rr && (
              <span className="text-xs text-muted">{level.rr}</span>
            )}
          </div>
        ))}
      </div>

      <div className="mt-4 pt-3 border-t border-card-active grid grid-cols-2 gap-3">
        <div className="p-2 rounded bg-card">
          <div className="text-xs text-muted">R:R 비율</div>
          <div className="text-sm font-semibold text-heading">
            1:{tradeParams.risk_reward_ratio.toFixed(1)}
          </div>
        </div>
        <div className="p-2 rounded bg-card">
          <div className="text-xs text-muted">리스크</div>
          <div className="text-sm font-semibold text-danger">
            {tradeParams.risk_percent.toFixed(2)}%
          </div>
        </div>
      </div>

      {priceLevels && (
        <div className="mt-3 pt-3 border-t border-card-active">
          <div className="flex items-center justify-between text-xs text-muted">
            <span>ATR(14)</span>
            <span className="font-mono">
              ${formatPrice(priceLevels.atr)} ({priceLevels.atr_percent.toFixed(2)}%)
            </span>
          </div>
          {priceLevels.support_levels.length > 0 && (
            <div className="flex items-center justify-between text-xs text-muted mt-1">
              <span>주요 지지</span>
              <span className="font-mono text-success">
                ${formatPrice(priceLevels.support_levels[0])}
              </span>
            </div>
          )}
          {priceLevels.resistance_levels.length > 0 && (
            <div className="flex items-center justify-between text-xs text-muted mt-1">
              <span>주요 저항</span>
              <span className="font-mono text-danger">
                ${formatPrice(priceLevels.resistance_levels[0])}
              </span>
            </div>
          )}
        </div>
      )}

      {symbol && (
        <Link
          href={`/paper-trading?symbol=${encodeURIComponent(symbol)}&direction=${dirLabel}&sl=${sl}&tp1=${tradeParams.take_profit_1}&tp2=${tradeParams.take_profit_2}&tp3=${tradeParams.take_profit_3}`}
          className="mt-3 w-full py-2 rounded-card text-sm font-medium bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20 transition-colors flex items-center justify-center gap-1.5"
        >
          <Wallet size={14} />
          모의투자 진입
        </Link>
      )}
    </div>
  );
}

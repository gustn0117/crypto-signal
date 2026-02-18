"use client";

import { TradeParamsData, PriceLevelsData } from "@/lib/api";

interface TradeParamsCardProps {
  tradeParams: TradeParamsData;
  priceLevels?: PriceLevelsData;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

export default function TradeParamsCard({ tradeParams, priceLevels }: TradeParamsCardProps) {
  const isLong = tradeParams.position_direction === "long";
  const dirColor = isLong ? "#26dad2" : "#ef5350";
  const dirLabel = isLong ? "LONG" : "SHORT";

  // 가격 사다리: SL -> Entry -> TP1 -> TP2 -> TP3 (롱 기준)
  const levels = isLong
    ? [
        { label: "TP3", price: tradeParams.take_profit_3, color: "#26dad2", rr: "3:1" },
        { label: "TP2", price: tradeParams.take_profit_2, color: "#26dad2", rr: "2:1" },
        { label: "TP1", price: tradeParams.take_profit_1, color: "#26dad2", rr: "1:1" },
        { label: "Entry", price: tradeParams.entry_price, color: "#4680ff", rr: "" },
        { label: "SL", price: tradeParams.stop_loss, color: "#ef5350", rr: "" },
      ]
    : [
        { label: "SL", price: tradeParams.stop_loss, color: "#ef5350", rr: "" },
        { label: "Entry", price: tradeParams.entry_price, color: "#4680ff", rr: "" },
        { label: "TP1", price: tradeParams.take_profit_1, color: "#26dad2", rr: "1:1" },
        { label: "TP2", price: tradeParams.take_profit_2, color: "#26dad2", rr: "2:1" },
        { label: "TP3", price: tradeParams.take_profit_3, color: "#26dad2", rr: "3:1" },
      ];

  return (
    <div className="p-4 rounded-lg border border-border bg-body">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">
          트레이드 파라미터
        </h3>
        <span
          className="text-xs font-bold px-2 py-0.5 rounded"
          style={{ color: dirColor, backgroundColor: `${dirColor}20` }}
        >
          {dirLabel}
        </span>
      </div>

      {/* 가격 사다리 */}
      <div className="space-y-0">
        {levels.map((level, i) => (
          <div key={level.label} className="relative">
            {/* 연결선 */}
            {i < levels.length - 1 && (
              <div className="absolute left-[52px] top-[28px] w-px h-[20px]" style={{ backgroundColor: "rgba(120, 130, 140, 0.13)" }} />
            )}
            <div className="flex items-center gap-3 py-1.5">
              <span
                className="text-xs font-bold w-10 text-right shrink-0"
                style={{ color: level.color }}
              >
                {level.label}
              </span>
              <div
                className="w-3 h-3 rounded-full border-2 shrink-0"
                style={{ borderColor: level.color, backgroundColor: level.label === "Entry" ? level.color : "transparent" }}
              />
              <span className="text-sm font-mono text-heading">
                ${formatPrice(level.price)}
              </span>
              {level.rr && (
                <span className="text-xs text-muted ml-auto">{level.rr}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 통계 */}
      <div className="mt-4 pt-3 border-t border-card-active grid grid-cols-2 gap-3">
        <div className="p-2 rounded bg-card">
          <div className="text-xs text-muted">R:R 비율</div>
          <div className="text-sm font-semibold text-heading">
            1:{tradeParams.risk_reward_ratio.toFixed(1)}
          </div>
        </div>
        <div className="p-2 rounded bg-card">
          <div className="text-xs text-muted">리스크</div>
          <div className="text-sm font-semibold" style={{ color: "#ef5350" }}>
            {tradeParams.risk_percent.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* ATR 정보 */}
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
    </div>
  );
}

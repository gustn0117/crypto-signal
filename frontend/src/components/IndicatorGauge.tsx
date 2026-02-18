"use client";

import { Indicator } from "@/lib/api";

interface IndicatorGaugeProps {
  indicator: Indicator;
}

export default function IndicatorGauge({ indicator }: IndicatorGaugeProps) {
  // position: 0(SHORT) ~ 50(NEUTRAL) ~ 100(LONG)
  const position =
    indicator.signal === "long"
      ? 50 + indicator.strength * 50
      : indicator.signal === "short"
      ? 50 - indicator.strength * 50
      : 50;

  const color =
    indicator.signal === "long"
      ? "#4caf50"
      : indicator.signal === "short"
      ? "#ef5350"
      : "#abafb3";

  const signalLabel =
    indicator.signal === "long"
      ? "LONG"
      : indicator.signal === "short"
      ? "SHORT"
      : "NEUTRAL";

  return (
    <div className="p-3 rounded-lg bg-card border border-card-active">
      {/* 상단: 이름 + 시그널 */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-heading">{indicator.name}</span>
        <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ color, backgroundColor: `${color}20` }}>
          {signalLabel}
        </span>
      </div>

      {/* 게이지 바 */}
      <div className="relative h-2 bg-card-active rounded-full overflow-hidden mb-2">
        {/* 배경 그라데이션 */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: "linear-gradient(to right, #ef535040, #10112d 40%, #10112d 60%, #26dad240)",
          }}
        />
        {/* 마커 */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full transition-all duration-500"
          style={{
            left: `${position}%`,
            transform: `translate(-50%, -50%)`,
            backgroundColor: color,
            borderWidth: 2,
            borderColor: "#070713",
            boxShadow: `0 0 6px ${color}80`,
          }}
        />
      </div>

      {/* 하단: 값 + 설명 */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted">
          {indicator.value !== undefined ? indicator.value.toFixed(2) : ""}
        </span>
        <span className="text-xs text-muted font-medium">
          강도 {(indicator.strength * 100).toFixed(0)}%
        </span>
      </div>
      <p className="text-xs text-muted mt-1 leading-relaxed">{indicator.description}</p>
    </div>
  );
}

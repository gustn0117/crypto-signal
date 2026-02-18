"use client";

import { Indicator } from "@/lib/api";

interface IndicatorGaugeProps {
  indicator: Indicator;
}

export default function IndicatorGauge({ indicator }: IndicatorGaugeProps) {
  const position =
    indicator.signal === "long"
      ? 50 + indicator.strength * 50
      : indicator.signal === "short"
      ? 50 - indicator.strength * 50
      : 50;

  const color =
    indicator.signal === "long"
      ? "var(--long)"
      : indicator.signal === "short"
      ? "var(--short)"
      : "var(--text-body)";

  const signalLabel =
    indicator.signal === "long"
      ? "LONG"
      : indicator.signal === "short"
      ? "SHORT"
      : "NEUTRAL";

  return (
    <div className="p-3 rounded-lg bg-card border border-card-active">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-heading">{indicator.name}</span>
        <span
          className="text-xs font-medium px-2 py-0.5 rounded"
          style={{ color, backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)` }}
        >
          {signalLabel}
        </span>
      </div>

      <div className="relative h-2 bg-card-active rounded-full overflow-hidden mb-2">
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: "linear-gradient(to right, rgba(239,83,80,0.25), var(--bg-active) 40%, var(--bg-active) 60%, rgba(38,218,210,0.25))",
          }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 transition-all duration-500"
          style={{
            left: `${position}%`,
            transform: `translate(-50%, -50%)`,
            backgroundColor: color,
            borderColor: "var(--bg-body)",
          }}
        />
      </div>

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

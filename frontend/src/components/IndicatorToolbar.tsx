"use client";

import { IndicatorConfig } from "@/hooks/useIndicatorToggles";

interface IndicatorToolbarProps {
  indicators: IndicatorConfig[];
  onToggle: (id: string) => void;
}

export default function IndicatorToolbar({ indicators, onToggle }: IndicatorToolbarProps) {
  const overlays = indicators.filter((i) => i.category === "overlay");
  const oscillators = indicators.filter((i) => i.category === "oscillator");

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 py-2 bg-card border border-border rounded-lg text-xs">
      <span className="text-muted font-medium mr-1 shrink-0">지표</span>
      {overlays.map((ind) => (
        <ToggleChip key={ind.id} indicator={ind} onToggle={onToggle} />
      ))}
      <span className="w-px h-4 bg-border mx-1" />
      {oscillators.map((ind) => (
        <ToggleChip key={ind.id} indicator={ind} onToggle={onToggle} />
      ))}
    </div>
  );
}

function ToggleChip({
  indicator,
  onToggle,
}: {
  indicator: IndicatorConfig;
  onToggle: (id: string) => void;
}) {
  return (
    <button
      onClick={() => onToggle(indicator.id)}
      className={`px-2 py-1 rounded-md font-medium transition-all ${
        indicator.enabled
          ? "text-white shadow-sm"
          : "text-muted hover:text-heading bg-transparent hover:bg-card-active"
      }`}
      style={
        indicator.enabled
          ? {
              backgroundColor: indicator.color,
              boxShadow: `0 0 8px ${indicator.color}33`,
            }
          : undefined
      }
    >
      {indicator.name}
    </button>
  );
}

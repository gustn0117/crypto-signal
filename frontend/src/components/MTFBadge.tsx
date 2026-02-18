"use client";

import { MTFData } from "@/lib/api";

interface MTFBadgeProps {
  mtf: MTFData;
  size?: "sm" | "md";
}

export default function MTFBadge({ mtf, size = "md" }: MTFBadgeProps) {
  const colorMap: Record<string, { bg: string; text: string; border: string }> = {
    aligned: { bg: "#26dad215", text: "#26dad2", border: "#26dad240" },
    opposed: { bg: "#ef535015", text: "#ef5350", border: "#ef535040" },
    neutral: { bg: "#abafb315", text: "#abafb3", border: "#abafb340" },
  };

  const style = colorMap[mtf.alignment] || colorMap.neutral;

  const trendIcon = mtf.higher_tf_trend === "bullish" ? "\u25B2" : mtf.higher_tf_trend === "bearish" ? "\u25BC" : "\u25C6";

  const alignLabel =
    mtf.alignment === "aligned" ? "정렬" : mtf.alignment === "opposed" ? "반대" : "중립";

  const modifierText =
    mtf.confidence_modifier > 0
      ? `+${(mtf.confidence_modifier * 100).toFixed(0)}%`
      : mtf.confidence_modifier < 0
        ? `${(mtf.confidence_modifier * 100).toFixed(0)}%`
        : "";

  if (size === "sm") {
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded border"
        style={{ color: style.text, backgroundColor: style.bg, borderColor: style.border }}
      >
        {trendIcon} {mtf.higher_tf} {alignLabel}
        {modifierText && <span className="opacity-75">{modifierText}</span>}
      </span>
    );
  }

  return (
    <div
      className="p-3 rounded-lg border"
      style={{ backgroundColor: style.bg, borderColor: style.border }}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-base" style={{ color: style.text }}>{trendIcon}</span>
          <span className="text-sm font-semibold" style={{ color: style.text }}>
            {mtf.higher_tf} {alignLabel}
          </span>
        </div>
        {modifierText && (
          <span className="text-xs font-bold" style={{ color: style.text }}>
            {modifierText}
          </span>
        )}
      </div>
      <p className="text-xs text-muted">{mtf.description}</p>
    </div>
  );
}

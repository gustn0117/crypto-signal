"use client";

import { MTFData } from "@/lib/api";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface MTFBadgeProps {
  mtf: MTFData;
  size?: "sm" | "md";
}

const ALIGNMENT_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  aligned: { color: "var(--long)", bg: "rgba(38,218,210,0.08)", border: "rgba(38,218,210,0.25)" },
  opposed: { color: "var(--short)", bg: "rgba(239,83,80,0.08)", border: "rgba(239,83,80,0.25)" },
  neutral: { color: "var(--text-body)", bg: "rgba(171,175,179,0.08)", border: "rgba(171,175,179,0.25)" },
};

export default function MTFBadge({ mtf, size = "md" }: MTFBadgeProps) {
  const style = ALIGNMENT_STYLES[mtf.alignment] || ALIGNMENT_STYLES.neutral;

  const TrendIcon =
    mtf.higher_tf_trend === "bullish" ? TrendingUp
    : mtf.higher_tf_trend === "bearish" ? TrendingDown
    : Minus;

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
        style={{ color: style.color, backgroundColor: style.bg, borderColor: style.border }}
      >
        <TrendIcon size={12} />
        {mtf.higher_tf} {alignLabel}
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
          <TrendIcon size={16} style={{ color: style.color }} />
          <span className="text-sm font-semibold" style={{ color: style.color }}>
            {mtf.higher_tf} {alignLabel}
          </span>
        </div>
        {modifierText && (
          <span className="text-xs font-bold" style={{ color: style.color }}>
            {modifierText}
          </span>
        )}
      </div>
      <p className="text-xs text-muted">{mtf.description}</p>
    </div>
  );
}

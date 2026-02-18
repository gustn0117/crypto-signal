"use client";

import { SignalTrack } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

const STATE_CONFIG: Record<string, {
  label: string;
  color: string;
  bgColor: string;
  pulse: boolean;
}> = {
  FORMING: {
    label: "포착",
    color: "var(--primary)",
    bgColor: "rgba(70,128,255,0.15)",
    pulse: true,
  },
  CONFIRMING: {
    label: "확인 중",
    color: "var(--warning)",
    bgColor: "rgba(255,178,43,0.15)",
    pulse: true,
  },
  CONFIRMED: {
    label: "확정",
    color: "var(--long)",
    bgColor: "rgba(38,218,210,0.15)",
    pulse: false,
  },
  WEAKENING: {
    label: "약화",
    color: "var(--weakening)",
    bgColor: "rgba(240,136,62,0.15)",
    pulse: false,
  },
};

export default function SignalStateBadge({
  track,
  size = "sm",
  showDetail = false,
}: {
  track?: SignalTrack;
  size?: "sm" | "md";
  showDetail?: boolean;
}) {
  if (!track) return null;

  const config = STATE_CONFIG[track.state] || STATE_CONFIG.FORMING;
  const isSmall = size === "sm";

  return (
    <div className="inline-flex items-center gap-1.5">
      <span
        className={`inline-flex items-center gap-1 font-medium rounded ${
          isSmall ? "text-[10px] px-1.5 py-0.5" : "text-xs px-2 py-1"
        }`}
        style={{ color: config.color, backgroundColor: config.bgColor }}
      >
        <span
          className={`inline-block rounded-full ${
            isSmall ? "w-1.5 h-1.5" : "w-2 h-2"
          } ${config.pulse ? "animate-pulse" : ""}`}
          style={{ backgroundColor: config.color }}
        />
        {config.label}
      </span>
      {showDetail && (
        <span className="text-[10px] text-muted">
          {track.consecutive_scans}회 · {timeAgo(track.first_detected_at)}
        </span>
      )}
    </div>
  );
}

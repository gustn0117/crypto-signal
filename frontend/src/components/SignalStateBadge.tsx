"use client";

import { SignalTrack } from "@/lib/api";

const STATE_CONFIG: Record<string, {
  label: string;
  color: string;
  bgColor: string;
  pulse: boolean;
}> = {
  FORMING: {
    label: "포착",
    color: "#4680ff",
    bgColor: "rgba(70,128,255,0.15)",
    pulse: true,
  },
  CONFIRMING: {
    label: "확인 중",
    color: "#ffb22b",
    bgColor: "rgba(255,178,43,0.15)",
    pulse: true,
  },
  CONFIRMED: {
    label: "확정",
    color: "#26dad2",
    bgColor: "rgba(38,218,210,0.15)",
    pulse: false,
  },
  WEAKENING: {
    label: "약화",
    color: "#f0883e",
    bgColor: "rgba(240,136,62,0.15)",
    pulse: false,
  },
};

function getAgeText(firstDetectedAt: string): string {
  const diff = Date.now() - new Date(firstDetectedAt).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "방금 전";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

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
          {track.consecutive_scans}회 · {getAgeText(track.first_detected_at)}
        </span>
      )}
    </div>
  );
}

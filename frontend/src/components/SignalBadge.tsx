"use client";

interface SignalBadgeProps {
  signal: string;
  confidence?: number;
  size?: "sm" | "md" | "lg";
}

const SIGNAL_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  STRONG_LONG: { label: "강한 롱", color: "#26dad2", bg: "rgba(38,218,210,0.15)" },
  LONG: { label: "롱", color: "#26dad2", bg: "rgba(38,218,210,0.1)" },
  NEUTRAL: { label: "관망", color: "#abafb3", bg: "rgba(171,175,179,0.1)" },
  SHORT: { label: "숏", color: "#ef5350", bg: "rgba(239,83,80,0.1)" },
  STRONG_SHORT: { label: "강한 숏", color: "#ef5350", bg: "rgba(239,83,80,0.15)" },
};

export default function SignalBadge({ signal, confidence, size = "md" }: SignalBadgeProps) {
  const config = SIGNAL_CONFIG[signal] || SIGNAL_CONFIG.NEUTRAL;

  const sizeClasses = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-3 py-1",
    lg: "text-base px-4 py-1.5 font-bold",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${sizeClasses[size]}`}
      style={{ color: config.color, backgroundColor: config.bg, border: `1px solid ${config.color}33` }}
    >
      <span
        className="w-2 h-2 rounded-full"
        style={{ backgroundColor: config.color }}
      />
      {config.label}
      {confidence !== undefined && (
        <span className="opacity-70 ml-1">{(confidence * 100).toFixed(0)}%</span>
      )}
    </span>
  );
}

"use client";

import { useState, useEffect } from "react";

interface ConfidenceMeterProps {
  confidence: number;
  signal: string;
  size?: number;
}

export default function ConfidenceMeter({ confidence, signal, size = 140 }: ConfidenceMeterProps) {
  const [animatedConfidence, setAnimatedConfidence] = useState(0);

  useEffect(() => {
    const timer = requestAnimationFrame(() => setAnimatedConfidence(confidence));
    return () => cancelAnimationFrame(timer);
  }, [confidence]);

  const percentage = Math.round(confidence * 100);
  const color = signal.includes("LONG")
    ? "var(--long)"
    : signal.includes("SHORT")
    ? "var(--short)"
    : "var(--text-body)";

  const radius = (size - 20) / 2;
  const circumference = Math.PI * radius;
  const filled = circumference * animatedConfidence;
  const cx = size / 2;
  const cy = size / 2 + 5;

  const signalText =
    signal === "STRONG_LONG"
      ? "강한 롱"
      : signal === "LONG"
      ? "롱"
      : signal === "STRONG_SHORT"
      ? "강한 숏"
      : signal === "SHORT"
      ? "숏"
      : "관망";

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size * 0.65} viewBox={`0 0 ${size} ${size * 0.65}`}>
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke="var(--bg-active)"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
          style={{ transition: "stroke-dasharray 0.8s ease-out" }}
        />
        <text
          x={cx}
          y={cy - 12}
          textAnchor="middle"
          className="text-2xl font-bold"
          fill={color}
          style={{ fontSize: size * 0.2 }}
        >
          {percentage}%
        </text>
        <text
          x={cx}
          y={cy + 2}
          textAnchor="middle"
          fill="var(--text-body)"
          style={{ fontSize: size * 0.09 }}
        >
          {signalText}
        </text>
      </svg>
    </div>
  );
}

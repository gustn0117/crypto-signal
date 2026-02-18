"use client";

interface ConfidenceMeterProps {
  confidence: number;
  signal: string;
  size?: number;
}

export default function ConfidenceMeter({ confidence, signal, size = 140 }: ConfidenceMeterProps) {
  const percentage = Math.round(confidence * 100);
  const color = signal.includes("LONG")
    ? "#26dad2"
    : signal.includes("SHORT")
    ? "#ef5350"
    : "#abafb3";

  const radius = (size - 20) / 2;
  const circumference = Math.PI * radius; // 반원
  const filled = circumference * confidence;
  const cx = size / 2;
  const cy = size / 2 + 5;

  const signalText =
    signal === "STRONG_LONG"
      ? "Strong Long"
      : signal === "LONG"
      ? "Long"
      : signal === "STRONG_SHORT"
      ? "Strong Short"
      : signal === "SHORT"
      ? "Short"
      : "Neutral";

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size * 0.65} viewBox={`0 0 ${size} ${size * 0.65}`}>
        {/* 배경 호 */}
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke="#10112d"
          strokeWidth="8"
          strokeLinecap="round"
        />
        {/* 채워진 호 */}
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
          style={{
            filter: `drop-shadow(0 0 4px ${color}60)`,
            transition: "stroke-dasharray 0.8s ease-out",
          }}
        />
        {/* 퍼센트 텍스트 */}
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
        {/* 시그널 라벨 */}
        <text
          x={cx}
          y={cy + 2}
          textAnchor="middle"
          fill="#abafb3"
          style={{ fontSize: size * 0.09 }}
        >
          {signalText}
        </text>
      </svg>
    </div>
  );
}

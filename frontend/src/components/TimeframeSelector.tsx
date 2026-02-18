"use client";

interface TimeframeSelectorProps {
  selected: string;
  onChange: (tf: string) => void;
}

const TIMEFRAMES = [
  { value: "1m", label: "1분" },
  { value: "5m", label: "5분" },
  { value: "15m", label: "15분" },
  { value: "30m", label: "30분" },
  { value: "1h", label: "1시간" },
  { value: "4h", label: "4시간" },
  { value: "1d", label: "1일" },
];

export default function TimeframeSelector({ selected, onChange }: TimeframeSelectorProps) {
  return (
    <div className="flex gap-1">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf.value}
          onClick={() => onChange(tf.value)}
          className={`px-3 py-1.5 text-sm rounded transition-colors ${
            selected === tf.value
              ? "bg-blue-600 text-white"
              : "bg-card-active text-muted hover:text-white hover:bg-[rgba(120,130,140,0.13)]"
          }`}
        >
          {tf.label}
        </button>
      ))}
    </div>
  );
}

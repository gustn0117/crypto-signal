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
    <div className="flex gap-1 flex-wrap">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf.value}
          onClick={() => onChange(tf.value)}
          className={`px-3 py-1.5 text-xs font-medium rounded-card transition-colors ${
            selected === tf.value
              ? "bg-primary text-white"
              : "bg-card-active text-muted hover:text-heading hover:bg-card-hover"
          }`}
        >
          {tf.label}
        </button>
      ))}
    </div>
  );
}

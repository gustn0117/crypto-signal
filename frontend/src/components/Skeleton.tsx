"use client";

function Pulse({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <div className={`animate-pulse bg-card-active rounded ${className}`} style={style} />
  );
}

export function ChartSkeleton() {
  return (
    <div className="h-[540px] border border-border rounded-lg bg-body p-4">
      <div className="flex items-center justify-between mb-4">
        <Pulse className="h-4 w-32" />
        <Pulse className="h-4 w-20" />
      </div>
      <div className="flex items-end gap-1 h-[460px] pt-8">
        {Array.from({ length: 40 }).map((_, i) => (
          <div key={i} className="flex-1 flex flex-col items-center justify-end gap-0.5">
            <Pulse className="w-px" style={{ height: `${20 + Math.random() * 30}%` }} />
            <Pulse
              className="w-full rounded-sm"
              style={{ height: `${10 + Math.random() * 40}%` }}
            />
            <Pulse className="w-px" style={{ height: `${10 + Math.random() * 20}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-0">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 px-4 py-3 border-t border-card-active"
        >
          <Pulse className="h-4 w-20" />
          <Pulse className="h-4 w-24" />
          <Pulse className="h-5 w-16 rounded-full" />
          <Pulse className="h-2 w-16 rounded-full" />
          <Pulse className="h-3 w-32" />
        </div>
      ))}
    </div>
  );
}

export function AnalysisSkeleton() {
  return (
    <div className="p-4 space-y-4">
      <div className="p-4 rounded-lg bg-card">
        <div className="flex items-center justify-between mb-3">
          <Pulse className="h-5 w-24" />
          <Pulse className="h-6 w-20 rounded-full" />
        </div>
        <Pulse className="h-3 w-full mb-2" />
        <Pulse className="h-3 w-3/4" />
      </div>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="p-3 rounded bg-card">
          <div className="flex items-center justify-between mb-2">
            <Pulse className="h-4 w-20" />
            <Pulse className="h-3 w-12" />
          </div>
          <Pulse className="h-1.5 w-full rounded-full mb-2" />
          <Pulse className="h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}

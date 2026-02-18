"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { Signal } from "@/lib/api";
import SignalBadge from "./SignalBadge";
import SignalStateBadge from "./SignalStateBadge";
import MTFBadge from "./MTFBadge";
import { ExternalLink, ChevronUp, ChevronDown, Radio } from "lucide-react";

interface SignalTableProps {
  signals: Signal[];
  onSelect: (symbol: string) => void;
  selectedSymbol?: string;
}

type SortKey = "symbol" | "confidence" | "signal" | "state";
type SortDir = "asc" | "desc";
type FilterType = "all" | "active" | "long" | "short" | "confirmed";

const FILTER_CONFIG: { key: FilterType; label: string; activeClass: string }[] = [
  { key: "all", label: "전체", activeClass: "bg-primary/15 text-primary" },
  { key: "active", label: "활성", activeClass: "bg-primary/15 text-primary" },
  { key: "long", label: "롱", activeClass: "bg-long-muted text-long" },
  { key: "short", label: "숏", activeClass: "bg-short-muted text-short" },
  { key: "confirmed", label: "확정", activeClass: "bg-long-muted text-long" },
];

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

const signalOrder: Record<string, number> = {
  STRONG_LONG: 5,
  LONG: 4,
  NEUTRAL: 3,
  SHORT: 2,
  STRONG_SHORT: 1,
};

const stateOrder: Record<string, number> = {
  CONFIRMED: 4,
  CONFIRMING: 3,
  FORMING: 2,
  WEAKENING: 1,
};

export default function SignalTable({ signals, onSelect, selectedSymbol }: SignalTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [filter, setFilter] = useState<FilterType>("all");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const filterCounts = useMemo(() => ({
    all: signals.length,
    active: signals.filter((s) => s.signal !== "NEUTRAL").length,
    long: signals.filter((s) => s.signal.includes("LONG")).length,
    short: signals.filter((s) => s.signal.includes("SHORT")).length,
    confirmed: signals.filter((s) => s.track?.state === "CONFIRMED").length,
  }), [signals]);

  const filtered = useMemo(() => {
    let result = [...signals];
    if (filter === "active") result = result.filter((s) => s.signal !== "NEUTRAL");
    if (filter === "long") result = result.filter((s) => s.signal.includes("LONG"));
    if (filter === "short") result = result.filter((s) => s.signal.includes("SHORT"));
    if (filter === "confirmed") result = result.filter((s) => s.track?.state === "CONFIRMED");

    result.sort((a, b) => {
      if (a.signal === "NEUTRAL" && b.signal !== "NEUTRAL") return 1;
      if (a.signal !== "NEUTRAL" && b.signal === "NEUTRAL") return -1;

      let cmp = 0;
      if (sortKey === "symbol") cmp = a.symbol.localeCompare(b.symbol);
      else if (sortKey === "confidence") cmp = a.confidence - b.confidence;
      else if (sortKey === "signal") cmp = (signalOrder[a.signal] || 0) - (signalOrder[b.signal] || 0);
      else if (sortKey === "state") cmp = (stateOrder[a.track?.state || ""] || 0) - (stateOrder[b.track?.state || ""] || 0);
      return sortDir === "asc" ? cmp : -cmp;
    });

    return result;
  }, [signals, sortKey, sortDir, filter]);

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null;
    return sortDir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
  };

  if (!signals.length) {
    return (
      <div className="flex items-center justify-center h-64 text-muted">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-card-active flex items-center justify-center">
            <Radio size={22} className="text-icon-muted" />
          </div>
          <p className="text-sm font-medium text-heading mb-1">스캔 결과 대기 중</p>
          <p className="text-xs text-muted">첫 스캔이 완료되면 시그널이 표시됩니다</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* 필터 버튼 */}
      <div className="flex items-center gap-1.5 px-3 py-2.5 border-b border-card-active flex-wrap">
        {FILTER_CONFIG.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
              filter === f.key ? f.activeClass : "text-muted hover:text-heading"
            }`}
          >
            {f.label} ({filterCounts[f.key]})
          </button>
        ))}
      </div>

      <div className="overflow-auto max-h-[560px]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="text-muted text-left">
              <th
                className="px-4 py-3 font-medium cursor-pointer hover:text-heading select-none"
                onClick={() => toggleSort("symbol")}
              >
                <span className="inline-flex items-center gap-1">코인 <SortIcon col="symbol" /></span>
              </th>
              <th className="px-4 py-3 font-medium hidden sm:table-cell">가격</th>
              <th
                className="px-4 py-3 font-medium cursor-pointer hover:text-heading select-none"
                onClick={() => toggleSort("signal")}
              >
                <span className="inline-flex items-center gap-1">시그널 <SortIcon col="signal" /></span>
              </th>
              <th
                className="px-4 py-3 font-medium cursor-pointer hover:text-heading select-none hidden md:table-cell"
                onClick={() => toggleSort("state")}
              >
                <span className="inline-flex items-center gap-1">상태 <SortIcon col="state" /></span>
              </th>
              <th
                className="px-4 py-3 font-medium cursor-pointer hover:text-heading select-none"
                onClick={() => toggleSort("confidence")}
              >
                <span className="inline-flex items-center gap-1">신뢰도 <SortIcon col="confidence" /></span>
              </th>
              <th className="px-2 py-3 font-medium hidden sm:table-cell"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((sig) => {
              const isConfirmed = sig.track?.state === "CONFIRMED";
              const isNeutral = sig.signal === "NEUTRAL";
              return (
                <tr
                  key={sig.symbol}
                  onClick={() => onSelect(sig.symbol)}
                  className={`border-t border-card-active cursor-pointer transition-colors ${
                    selectedSymbol === sig.symbol
                      ? "bg-primary/10"
                      : isNeutral
                        ? "hover:bg-card opacity-60"
                        : "hover:bg-card"
                  }`}
                  style={isConfirmed ? { borderLeft: "3px solid var(--long)" } : undefined}
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-heading">{sig.symbol}</div>
                    {sig.mtf_confirmation && (
                      <MTFBadge mtf={sig.mtf_confirmation} size="sm" />
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono hidden sm:table-cell">${formatPrice(sig.current_price)}</td>
                  <td className="px-4 py-3">
                    <SignalBadge signal={sig.signal} size="sm" />
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    {isNeutral ? (
                      <span className="text-xs text-muted">-</span>
                    ) : (
                      <SignalStateBadge track={sig.track} size="sm" />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isNeutral ? (
                      <span className="text-xs text-muted">-</span>
                    ) : (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-card-active rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${sig.confidence * 100}%`,
                              backgroundColor:
                                sig.confidence >= 0.7
                                  ? "var(--success-text)"
                                  : sig.confidence >= 0.4
                                    ? "var(--warning)"
                                    : "var(--text-muted)",
                            }}
                          />
                        </div>
                        <span className="text-muted text-xs">
                          {(sig.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-3 hidden sm:table-cell">
                    <Link
                      href={`/coin/${sig.symbol.replace("/", "")}`}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-card text-xs font-medium text-primary bg-primary/10 hover:bg-primary/20 transition-colors"
                      onClick={(e) => e.stopPropagation()}
                    >
                      상세
                      <ExternalLink size={12} />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

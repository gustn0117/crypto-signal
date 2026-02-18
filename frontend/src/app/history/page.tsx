"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Signal, fetchSignalHistory } from "@/lib/api";
import SignalBadge from "@/components/SignalBadge";
import { TableSkeleton } from "@/components/Skeleton";
import { ChevronLeft, ChevronRight, Clock } from "lucide-react";

const PAGE_SIZE = 30;
const SIGNAL_FILTERS = ["전체", "STRONG_LONG", "LONG", "SHORT", "STRONG_SHORT"];

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(4);
  return price.toFixed(6);
}

function formatTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function HistoryPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [signalFilter, setSignalFilter] = useState("전체");
  const [tfFilter, setTfFilter] = useState("");

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const params: { limit: number; offset: number; symbol?: string; timeframe?: string } = {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };
      if (symbolFilter) params.symbol = symbolFilter;
      if (tfFilter) params.timeframe = tfFilter;
      const data = await fetchSignalHistory(params);
      let filtered = data.signals;
      if (signalFilter !== "전체") {
        filtered = filtered.filter((s) => s.signal === signalFilter);
      }
      setSignals(filtered);
      setTotal(data.total);
    } catch (e) {
      console.error("히스토리 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }, [page, symbolFilter, tfFilter, signalFilter]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-heading">시그널 히스토리</h2>

      {/* 필터 */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="심볼 검색 (예: BTCUSDT)"
          value={symbolFilter}
          onChange={(e) => { setSymbolFilter(e.target.value.toUpperCase()); setPage(0); }}
          className="cd-input w-48"
        />
        <select
          value={tfFilter}
          onChange={(e) => { setTfFilter(e.target.value); setPage(0); }}
          className="cd-input"
        >
          <option value="">모든 타임프레임</option>
          <option value="5m">5m</option>
          <option value="15m">15m</option>
          <option value="1h">1h</option>
          <option value="4h">4h</option>
          <option value="1d">1d</option>
        </select>
        <div className="flex items-center gap-1">
          {SIGNAL_FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => { setSignalFilter(f); setPage(0); }}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                signalFilter === f
                  ? "bg-primary/15 text-primary"
                  : "text-muted hover:text-heading"
              }`}
            >
              {f === "전체" ? f : f.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {/* 테이블 */}
      <div className="cd-card p-0 overflow-hidden">
        {loading ? (
          <TableSkeleton rows={8} />
        ) : signals.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-card-active flex items-center justify-center">
              <Clock size={24} className="text-icon-muted" />
            </div>
            <p className="text-base font-medium text-heading mb-1">결과 없음</p>
            <p className="text-sm text-muted">검색 조건에 맞는 시그널이 없습니다</p>
          </div>
        ) : (
          <div className="overflow-auto">
            <table className="w-full text-sm cd-table">
              <thead className="bg-card">
                <tr>
                  <th>시간</th>
                  <th>코인</th>
                  <th className="hidden sm:table-cell">TF</th>
                  <th>시그널</th>
                  <th className="hidden sm:table-cell">신뢰도</th>
                  <th className="hidden md:table-cell">가격</th>
                  <th className="hidden md:table-cell">SL/TP</th>
                  <th className="hidden lg:table-cell">요약</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, i) => (
                  <tr key={`${sig.symbol}-${sig.timestamp}-${i}`}>
                    <td className="text-xs whitespace-nowrap">{formatTime(sig.timestamp)}</td>
                    <td>
                      <Link
                        href={`/coin/${sig.symbol.replace("/", "")}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {sig.symbol}
                      </Link>
                    </td>
                    <td className="hidden sm:table-cell">{sig.timeframe}</td>
                    <td><SignalBadge signal={sig.signal} size="sm" /></td>
                    <td className="text-xs hidden sm:table-cell">{(sig.confidence * 100).toFixed(0)}%</td>
                    <td className="font-mono text-xs hidden md:table-cell">${formatPrice(sig.current_price)}</td>
                    <td className="text-xs hidden md:table-cell">
                      {sig.trade_params ? (
                        <div className="space-y-0.5">
                          <div className="text-danger">SL: ${formatPrice(sig.trade_params.stop_loss)}</div>
                          <div className="text-success">TP1: ${formatPrice(sig.trade_params.take_profit_1)}</div>
                        </div>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td className="text-xs max-w-[250px] truncate hidden lg:table-cell">{sig.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted">
            총 {total}개 중 {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, total)}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="p-2 rounded-card border border-border hover:bg-card-active disabled:opacity-30 transition-colors"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-sm text-muted">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="p-2 rounded-card border border-border hover:bg-card-active disabled:opacity-30 transition-colors"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Market, fetchMarkets } from "@/lib/api";
import { Search, X } from "lucide-react";
import { useRouter } from "next/navigation";

interface CoinSearchProps {
  currentSymbol?: string;
}

function formatVolume(vol: number): string {
  if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(1)}B`;
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
  return vol.toFixed(0);
}

export default function CoinSearch({ currentSymbol }: CoinSearchProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [markets, setMarkets] = useState<Market[]>([]);
  const [filtered, setFiltered] = useState<Market[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchMarkets().then(setMarkets).catch(console.error);
  }, []);

  useEffect(() => {
    if (!query.trim()) {
      setFiltered(markets.slice(0, 20));
      return;
    }
    const q = query.toUpperCase();
    setFiltered(
      markets.filter((m) => m.symbol.toUpperCase().includes(q)).slice(0, 20)
    );
  }, [query, markets]);

  // 외부 클릭 시 닫기
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleSelect = useCallback(
    (symbol: string) => {
      const urlSymbol = symbol.replace("/", "");
      router.push(`/coin/${urlSymbol}`);
      setIsOpen(false);
      setQuery("");
    },
    [router]
  );

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center gap-2 bg-body border border-border rounded-lg px-3 py-1.5">
        <Search size={14} className="text-muted" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setIsOpen(true)}
          placeholder="코인 검색..."
          className="bg-transparent text-sm text-heading placeholder-muted outline-none w-40"
        />
        {query && (
          <button onClick={() => { setQuery(""); inputRef.current?.focus(); }}>
            <X size={14} className="text-muted hover:text-white" />
          </button>
        )}
      </div>

      {isOpen && filtered.length > 0 && (
        <div className="absolute top-full left-0 mt-1 w-80 max-h-80 overflow-auto bg-card border border-border rounded-lg shadow-xl z-50">
          {filtered.map((m) => (
            <button
              key={m.symbol}
              onClick={() => handleSelect(m.symbol)}
              className={`w-full px-4 py-2.5 flex items-center justify-between hover:bg-card-active transition-colors text-left ${
                currentSymbol === m.symbol.replace("/", "") ? "bg-[#4680ff22]" : ""
              }`}
            >
              <div>
                <span className="text-sm font-medium text-heading">
                  {m.symbol}
                </span>
                <span className="ml-2 text-xs text-muted">
                  Vol {formatVolume(m.volume_usdt)}
                </span>
              </div>
              <div className="text-right">
                <span className="text-sm text-heading">
                  ${m.price >= 1 ? m.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : m.price.toFixed(6)}
                </span>
                <span
                  className={`ml-2 text-xs ${
                    (m.change_24h || 0) >= 0 ? "text-success" : "text-danger"
                  }`}
                >
                  {(m.change_24h || 0) >= 0 ? "+" : ""}
                  {(m.change_24h || 0).toFixed(2)}%
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

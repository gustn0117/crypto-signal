"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Market, fetchMarkets } from "@/lib/api";
import { formatVolume } from "@/lib/utils";
import { Search, X, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";

interface CoinSearchProps {
  currentSymbol?: string;
  timeframe?: string;
}

export default function CoinSearch({ currentSymbol, timeframe }: CoinSearchProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [markets, setMarkets] = useState<Market[]>([]);
  const [filtered, setFiltered] = useState<Market[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    fetchMarkets()
      .then(setMarkets)
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
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
    setActiveIndex(-1);
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
      const tfParam = timeframe ? `?tf=${timeframe}` : "";
      router.push(`/coin/${urlSymbol}${tfParam}`);
      setIsOpen(false);
      setQuery("");
      setActiveIndex(-1);
    },
    [router]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isOpen || filtered.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => (prev < filtered.length - 1 ? prev + 1 : 0));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : filtered.length - 1));
      } else if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        handleSelect(filtered[activeIndex].symbol);
      } else if (e.key === "Escape") {
        setIsOpen(false);
        inputRef.current?.blur();
      }
    },
    [isOpen, filtered, activeIndex, handleSelect]
  );

  // 활성 항목이 보이도록 스크롤
  useEffect(() => {
    if (activeIndex >= 0 && listRef.current) {
      const activeEl = listRef.current.children[activeIndex] as HTMLElement;
      activeEl?.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex]);

  const listId = "coin-search-listbox";

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center gap-2 bg-body border border-border rounded-lg px-3 py-1.5">
        {loading ? (
          <Loader2 size={14} className="text-muted animate-spin" />
        ) : (
          <Search size={14} className="text-muted" />
        )}
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="코인 검색..."
          className="bg-transparent text-sm text-heading placeholder-muted outline-none w-40"
          role="combobox"
          aria-expanded={isOpen}
          aria-controls={listId}
          aria-activedescendant={activeIndex >= 0 ? `coin-option-${activeIndex}` : undefined}
          aria-autocomplete="list"
        />
        {query && (
          <button
            onClick={() => { setQuery(""); inputRef.current?.focus(); }}
            aria-label="검색 초기화"
          >
            <X size={14} className="text-muted hover:text-white" />
          </button>
        )}
      </div>

      {isOpen && loadError && (
        <div className="absolute top-full left-0 mt-1 w-[calc(100vw-2rem)] sm:w-80 bg-card border border-border rounded-lg shadow-dropdown z-50 p-4 text-center">
          <p className="text-sm text-danger mb-2">마켓 데이터 로드 실패</p>
          <button
            onClick={() => {
              setLoading(true);
              setLoadError(false);
              fetchMarkets()
                .then(setMarkets)
                .catch(() => setLoadError(true))
                .finally(() => setLoading(false));
            }}
            className="text-xs text-primary hover:underline"
          >
            다시 시도
          </button>
        </div>
      )}

      {isOpen && !loadError && filtered.length > 0 && (
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          className="absolute top-full left-0 mt-1 w-[calc(100vw-2rem)] sm:w-80 max-h-80 overflow-auto bg-card border border-border rounded-lg shadow-dropdown z-50 animate-dropdown-in"
        >
          {filtered.map((m, idx) => (
            <button
              key={m.symbol}
              id={`coin-option-${idx}`}
              role="option"
              aria-selected={activeIndex === idx}
              onClick={() => handleSelect(m.symbol)}
              className={`w-full px-4 py-2.5 flex items-center justify-between hover:bg-card-active transition-colors text-left ${
                activeIndex === idx ? "bg-card-active" : ""
              } ${currentSymbol === m.symbol.replace("/", "") ? "bg-primary/10" : ""}`}
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

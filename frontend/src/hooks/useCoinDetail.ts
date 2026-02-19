"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Signal, Candle, Ticker, analyzeSymbol, fetchOHLCV, fetchTicker } from "@/lib/api";
import { useWS } from "@/components/ClientLayout";

export function useCoinDetail(symbol: string, initialTimeframe: string = "1h") {
  const { connected, analysis, subscribe, unsubscribe } = useWS();

  const [signal, setSignal] = useState<Signal | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [timeframe, setTimeframe] = useState(initialTimeframe);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<string>("");

  const normalizedSymbol = symbol.includes("/") ? symbol : symbol.replace("USDT", "/USDT");
  const normalizedRef = useRef(normalizedSymbol);
  normalizedRef.current = normalizedSymbol;

  // 요청 ID로 race condition 방지
  const requestIdRef = useRef(0);

  const loadData = useCallback(
    async (tf: string) => {
      const reqId = ++requestIdRef.current;
      setLoading(true);
      setError(null);
      try {
        const [analysisData, ohlcvData, tickerData] = await Promise.all([
          analyzeSymbol(normalizedRef.current, tf),
          fetchOHLCV(normalizedRef.current, tf),
          fetchTicker(normalizedRef.current),
        ]);
        // 오래된 응답 무시 (타임프레임/심볼 변경 시)
        if (reqId !== requestIdRef.current) return;
        setSignal(analysisData);
        setCandles(ohlcvData);
        setTicker(tickerData);
        setLastRefresh(new Date().toISOString());
      } catch (err) {
        if (reqId !== requestIdRef.current) return;
        const message = err instanceof Error ? err.message : "데이터를 불러오는 데 실패했습니다";
        setError(message);
        console.error("데이터 로드 실패:", err);
      } finally {
        if (reqId === requestIdRef.current) setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadData(timeframe);
  }, [loadData, timeframe, normalizedSymbol]);

  useEffect(() => {
    if (connected) {
      subscribe(normalizedSymbol, timeframe);
    }
    return () => {
      unsubscribe();
    };
  }, [connected, normalizedSymbol, timeframe, subscribe, unsubscribe]);

  useEffect(() => {
    if (analysis && analysis.symbol === normalizedSymbol) {
      setSignal(analysis);
      setLastRefresh(new Date().toISOString());
    }
  }, [analysis, normalizedSymbol]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const t = await fetchTicker(normalizedRef.current);
        setTicker(t);
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(interval);
  }, [normalizedSymbol]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const ohlcv = await fetchOHLCV(normalizedRef.current, timeframe);
        setCandles(ohlcv);
      } catch { /* ignore */ }
    }, 30000);
    return () => clearInterval(interval);
  }, [normalizedSymbol, timeframe]);

  const changeTimeframe = useCallback((tf: string) => {
    setTimeframe(tf);
  }, []);

  const refresh = useCallback(() => {
    loadData(timeframe);
  }, [loadData, timeframe]);

  return {
    signal,
    candles,
    ticker,
    timeframe,
    loading,
    error,
    connected,
    lastRefresh,
    changeTimeframe,
    refresh,
  };
}

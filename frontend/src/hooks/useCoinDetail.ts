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
  const [lastRefresh, setLastRefresh] = useState<string>("");

  // BTC/USDT 형식으로 정규화
  const normalizedSymbol = symbol.includes("/") ? symbol : symbol.replace("USDT", "/USDT");
  const normalizedRef = useRef(normalizedSymbol);
  normalizedRef.current = normalizedSymbol;

  // 초기 데이터 로드
  const loadData = useCallback(
    async (tf: string) => {
      setLoading(true);
      try {
        const [analysisData, ohlcvData, tickerData] = await Promise.all([
          analyzeSymbol(normalizedRef.current, tf),
          fetchOHLCV(normalizedRef.current, tf),
          fetchTicker(normalizedRef.current),
        ]);
        setSignal(analysisData);
        setCandles(ohlcvData);
        setTicker(tickerData);
        setLastRefresh(new Date().toISOString());
      } catch (error) {
        console.error("데이터 로드 실패:", error);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // 초기 로드
  useEffect(() => {
    loadData(timeframe);
  }, [loadData, timeframe, normalizedSymbol]);

  // WebSocket 구독
  useEffect(() => {
    if (connected) {
      subscribe(normalizedSymbol, timeframe);
    }
    return () => {
      unsubscribe();
    };
  }, [connected, normalizedSymbol, timeframe, subscribe, unsubscribe]);

  // WS에서 분석 결과 수신 시 갱신
  useEffect(() => {
    if (analysis && analysis.symbol === normalizedSymbol) {
      setSignal(analysis);
      setLastRefresh(new Date().toISOString());
    }
  }, [analysis, normalizedSymbol]);

  // 티커 폴링 (5초)
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const t = await fetchTicker(normalizedRef.current);
        setTicker(t);
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(interval);
  }, [normalizedSymbol]);

  // 캔들 폴링 (30초)
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
    connected,
    lastRefresh,
    changeTimeframe,
    refresh,
  };
}

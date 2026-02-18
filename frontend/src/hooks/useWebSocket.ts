"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Signal, Alert, Prediction, PredictionProgress } from "@/lib/api";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
const MAX_RECONNECT_DELAY = 30000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  const [analysis, setAnalysis] = useState<Signal | null>(null);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [latestAlert, setLatestAlert] = useState<Alert | null>(null);
  const [predictionCreated, setPredictionCreated] = useState<Prediction | null>(null);
  const [predictionProgress, setPredictionProgress] = useState<PredictionProgress[]>([]);
  const [predictionVerified, setPredictionVerified] = useState<Prediction | null>(null);
  const reconnectTimer = useRef<NodeJS.Timeout>();
  const reconnectAttempts = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_BASE}/ws`);

    ws.onopen = () => {
      setConnected(true);
      reconnectAttempts.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        if (message.type === "initial" || message.type === "scan_update") {
          setSignals(message.data.signals || []);
          setLastUpdate(message.data.last_scan_time || "");
          if (message.data.unread_alerts !== undefined) {
            setUnreadAlerts(message.data.unread_alerts);
          }
        } else if (message.type === "analysis" || message.type === "subscription_update") {
          setAnalysis(message.data);
        } else if (message.type === "alert") {
          setLatestAlert(message.data);
          setUnreadAlerts((prev) => prev + 1);
        } else if (message.type === "prediction_created") {
          setPredictionCreated(message.data);
        } else if (message.type === "prediction_progress") {
          setPredictionProgress(message.data);
        } else if (message.type === "prediction_verified") {
          setPredictionVerified(message.data);
        }
      } catch (e) {
        console.error("메시지 파싱 오류:", e);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // 지수적 백오프 재연결
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), MAX_RECONNECT_DELAY);
      reconnectAttempts.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  const subscribe = useCallback(
    (symbol: string, timeframe: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({ type: "subscribe", symbol, timeframe })
        );
      }
    },
    []
  );

  const unsubscribe = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "unsubscribe" }));
    }
    setAnalysis(null);
  }, []);

  const clearLatestAlert = useCallback(() => {
    setLatestAlert(null);
  }, []);

  const clearPredictionCreated = useCallback(() => {
    setPredictionCreated(null);
  }, []);

  const clearPredictionVerified = useCallback(() => {
    setPredictionVerified(null);
  }, []);

  const resetUnreadAlerts = useCallback((count: number = 0) => {
    setUnreadAlerts(count);
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return {
    connected,
    signals,
    lastUpdate,
    analysis,
    unreadAlerts,
    latestAlert,
    predictionCreated,
    predictionProgress,
    predictionVerified,
    subscribe,
    unsubscribe,
    clearLatestAlert,
    clearPredictionCreated,
    clearPredictionVerified,
    resetUnreadAlerts,
  };
}

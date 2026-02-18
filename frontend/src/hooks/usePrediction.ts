"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Prediction,
  PredictionStats,
  PredictionProgress,
  createPrediction,
  fetchActivePrediction,
  fetchPredictions,
  fetchPredictionStats,
  verifyPrediction,
} from "@/lib/api";

interface WsPredictionEvents {
  predictionCreated?: Prediction | null;
  predictionProgress?: PredictionProgress[];
  predictionVerified?: Prediction | null;
}

export function usePrediction(
  symbol: string,
  timeframe: string,
  wsEvents?: WsPredictionEvents,
) {
  const [activePrediction, setActivePrediction] = useState<Prediction | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<PredictionStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  const normalizedSymbol = symbol.includes("/")
    ? symbol
    : symbol.replace("USDT", "/USDT");

  const loadPredictions = useCallback(async () => {
    setLoading(true);
    try {
      const [active, history, statsData] = await Promise.all([
        fetchActivePrediction(normalizedSymbol, timeframe),
        fetchPredictions(normalizedSymbol, { limit: 20 }),
        fetchPredictionStats(normalizedSymbol),
      ]);
      setActivePrediction(active);
      setPredictions(history.predictions);
      setStats(statsData);
    } catch (error) {
      console.error("예측 데이터 로드 실패:", error);
    } finally {
      setLoading(false);
    }
  }, [normalizedSymbol, timeframe]);

  useEffect(() => {
    loadPredictions();
  }, [loadPredictions]);

  // WebSocket: 자동 생성 예측 수신
  useEffect(() => {
    if (wsEvents?.predictionCreated && wsEvents.predictionCreated.symbol === normalizedSymbol) {
      setActivePrediction(wsEvents.predictionCreated);
      loadPredictions();
    }
  }, [wsEvents?.predictionCreated, normalizedSymbol, loadPredictions]);

  // WebSocket: 실시간 진행 업데이트
  useEffect(() => {
    if (!wsEvents?.predictionProgress || !activePrediction) return;
    const update = wsEvents.predictionProgress.find(
      (p) => p.prediction_id === activePrediction.id,
    );
    if (update) {
      setActivePrediction((prev) =>
        prev
          ? {
              ...prev,
              progress_pnl_pct: update.pnl_pct,
              progress_rr_current: update.rr_current,
              progress_time_pct: update.time_pct,
              progress_path_accuracy: update.path_accuracy,
            }
          : prev,
      );
    }
  }, [wsEvents?.predictionProgress, activePrediction?.id]);

  // WebSocket: 검증 완료
  useEffect(() => {
    if (wsEvents?.predictionVerified && wsEvents.predictionVerified.symbol === normalizedSymbol) {
      loadPredictions();
    }
  }, [wsEvents?.predictionVerified, normalizedSymbol, loadPredictions]);

  const generate = useCallback(
    async (horizonCandles: number = 24) => {
      setGenerating(true);
      try {
        const pred = await createPrediction(normalizedSymbol, timeframe, horizonCandles);
        setActivePrediction(pred);
        const history = await fetchPredictions(normalizedSymbol, { limit: 20 });
        setPredictions(history.predictions);
        return pred;
      } catch (error) {
        console.error("예측 생성 실패:", error);
        throw error;
      } finally {
        setGenerating(false);
      }
    },
    [normalizedSymbol, timeframe]
  );

  const verify = useCallback(
    async (predictionId: number) => {
      try {
        const result = await verifyPrediction(predictionId);
        await loadPredictions();
        return result;
      } catch (error) {
        console.error("예측 검증 실패:", error);
        throw error;
      }
    },
    [loadPredictions]
  );

  return {
    activePrediction,
    predictions,
    stats,
    loading,
    generating,
    generate,
    verify,
    reload: loadPredictions,
  };
}

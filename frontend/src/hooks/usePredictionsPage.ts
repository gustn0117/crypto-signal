"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Prediction,
  PredictionProgress,
  PredictionDashboardStats,
  fetchAllPredictions,
  fetchAllActivePredictions,
  fetchPredictionDashboard,
} from "@/lib/api";

export interface PredictionFilters {
  status?: string;
  direction?: string;
  timeframe?: string;
  result?: string;
}

interface UsePredictionsPageReturn {
  // Data
  activePredictions: Prediction[];
  historyPredictions: Prediction[];
  historyTotal: number;
  dashboardStats: PredictionDashboardStats | null;
  // State
  loading: boolean;
  activeLoading: boolean;
  historyLoading: boolean;
  // Filters & pagination
  filters: PredictionFilters;
  setFilters: (f: PredictionFilters) => void;
  page: number;
  setPage: (p: number) => void;
  pageSize: number;
  // WS integration
  applyProgress: (progress: PredictionProgress[]) => void;
  applyCreated: (prediction: Prediction) => void;
  applyVerified: (prediction: Prediction) => void;
  // Actions
  reload: () => void;
}

const PAGE_SIZE = 20;

export function usePredictionsPage(): UsePredictionsPageReturn {
  const [activePredictions, setActivePredictions] = useState<Prediction[]>([]);
  const [historyPredictions, setHistoryPredictions] = useState<Prediction[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [dashboardStats, setDashboardStats] = useState<PredictionDashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeLoading, setActiveLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [filters, setFiltersRaw] = useState<PredictionFilters>({});
  const [page, setPageRaw] = useState(0);
  const reqId = useRef(0);

  // ─── 활성 예측 로드 ─────────────────────────────────
  const loadActive = useCallback(async () => {
    setActiveLoading(true);
    try {
      const data = await fetchAllActivePredictions();
      setActivePredictions(data.predictions || []);
    } catch (e) {
      console.error("활성 예측 로드 실패:", e);
    } finally {
      setActiveLoading(false);
    }
  }, []);

  // ─── 히스토리 로드 ──────────────────────────────────
  const loadHistory = useCallback(
    async (f: PredictionFilters, p: number) => {
      setHistoryLoading(true);
      const id = ++reqId.current;
      try {
        const data = await fetchAllPredictions({
          ...f,
          limit: PAGE_SIZE,
          offset: p * PAGE_SIZE,
        });
        if (id !== reqId.current) return; // stale
        setHistoryPredictions(data.predictions || []);
        setHistoryTotal(data.total);
      } catch (e) {
        console.error("예측 히스토리 로드 실패:", e);
      } finally {
        if (id === reqId.current) setHistoryLoading(false);
      }
    },
    []
  );

  // ─── 대시보드 통계 ──────────────────────────────────
  const loadDashboard = useCallback(async () => {
    try {
      const data = await fetchPredictionDashboard();
      setDashboardStats(data);
    } catch (e) {
      console.error("대시보드 통계 로드 실패:", e);
    }
  }, []);

  // ─── 초기 로드 ─────────────────────────────────────
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([loadActive(), loadHistory(filters, page), loadDashboard()]);
      setLoading(false);
    };
    init();
    // 60초마다 활성 예측 갱신
    const interval = setInterval(loadActive, 60000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── 필터/페이지 변경 시 히스토리 재로드 ────────────
  const setFilters = useCallback(
    (f: PredictionFilters) => {
      setFiltersRaw(f);
      setPageRaw(0);
      loadHistory(f, 0);
    },
    [loadHistory]
  );

  const setPage = useCallback(
    (p: number) => {
      setPageRaw(p);
      loadHistory(filters, p);
    },
    [filters, loadHistory]
  );

  // ─── WebSocket 이벤트 핸들러 ───────────────────────
  const applyProgress = useCallback((progress: PredictionProgress[]) => {
    if (!progress.length) return;
    setActivePredictions((prev) =>
      prev.map((p) => {
        const match = progress.find((pg) => pg.prediction_id === p.id);
        if (!match) return p;
        return {
          ...p,
          progress_pnl_pct: match.pnl_pct,
          progress_rr_current: match.rr_current,
          progress_time_pct: match.time_pct,
          progress_path_accuracy: match.path_accuracy,
        };
      })
    );
  }, []);

  const applyCreated = useCallback((prediction: Prediction) => {
    setActivePredictions((prev) => {
      // 같은 심볼+TF 기존 것 제거 후 추가
      const filtered = prev.filter(
        (p) => !(p.symbol === prediction.symbol && p.timeframe === prediction.timeframe)
      );
      return [prediction, ...filtered];
    });
  }, []);

  const applyVerified = useCallback(
    (prediction: Prediction) => {
      setActivePredictions((prev) => prev.filter((p) => p.id !== prediction.id));
      // 히스토리 새로고침
      loadHistory(filters, page);
      loadDashboard();
    },
    [filters, page, loadHistory, loadDashboard]
  );

  const reload = useCallback(() => {
    loadActive();
    loadHistory(filters, page);
    loadDashboard();
  }, [filters, page, loadActive, loadHistory, loadDashboard]);

  return {
    activePredictions,
    historyPredictions,
    historyTotal,
    dashboardStats,
    loading,
    activeLoading,
    historyLoading,
    filters,
    setFilters,
    page,
    setPage,
    pageSize: PAGE_SIZE,
    applyProgress,
    applyCreated,
    applyVerified,
    reload,
  };
}

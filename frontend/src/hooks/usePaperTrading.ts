"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  PaperAccount,
  PaperTrade,
  PaperTradingStats,
  PaperPositionUpdate,
  fetchPaperAccount,
  fetchPaperPositions,
  fetchPaperTradeHistory,
  fetchPaperTradingStats,
  openPaperTrade,
  closePaperTrade,
  resetPaperAccount,
} from "@/lib/api";

interface UsePaperTradingReturn {
  account: PaperAccount | null;
  positions: PaperTrade[];
  history: PaperTrade[];
  historyTotal: number;
  stats: PaperTradingStats | null;
  loading: boolean;
  opening: boolean;
  historyPage: number;
  setHistoryPage: (p: number) => void;
  open: (params: {
    symbol: string;
    direction: "LONG" | "SHORT";
    position_usdt: number;
    stop_loss?: number | null;
    take_profit_1?: number | null;
    take_profit_2?: number | null;
    take_profit_3?: number | null;
  }) => Promise<PaperTrade | null>;
  close: (tradeId: number) => Promise<void>;
  reset: () => Promise<void>;
  reload: () => void;
  applyPositionUpdates: (updates: PaperPositionUpdate[]) => void;
  applyTradeOpened: (trade: PaperTrade) => void;
  applyTradeClosed: (trade: PaperTrade) => void;
}

const PAGE_SIZE = 20;

export function usePaperTrading(): UsePaperTradingReturn {
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [positions, setPositions] = useState<PaperTrade[]>([]);
  const [history, setHistory] = useState<PaperTrade[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [stats, setStats] = useState<PaperTradingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [historyPage, setHistoryPageRaw] = useState(0);
  const reqId = useRef(0);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [acct, pos, statsData] = await Promise.all([
        fetchPaperAccount(),
        fetchPaperPositions(),
        fetchPaperTradingStats(),
      ]);
      setAccount(acct);
      setPositions(pos.positions);
      setStats(statsData);
    } catch (e) {
      console.error("모의 트레이딩 데이터 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async (page: number) => {
    const id = ++reqId.current;
    try {
      const data = await fetchPaperTradeHistory({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      if (id !== reqId.current) return;
      setHistory(data.trades);
      setHistoryTotal(data.total);
    } catch (e) {
      console.error("거래 내역 로드 실패:", e);
    }
  }, []);

  useEffect(() => {
    loadAll();
    loadHistory(0);
  }, [loadAll, loadHistory]);

  const setHistoryPage = useCallback(
    (p: number) => {
      setHistoryPageRaw(p);
      loadHistory(p);
    },
    [loadHistory]
  );

  // WebSocket 핸들러
  const applyPositionUpdates = useCallback((updates: PaperPositionUpdate[]) => {
    if (!updates.length) return;
    setPositions((prev) =>
      prev.map((pos) => {
        const u = updates.find((upd) => upd.trade_id === pos.id);
        if (!u) return pos;
        return {
          ...pos,
          current_price: u.current_price,
          unrealized_pnl: u.unrealized_pnl,
          unrealized_pnl_pct: u.unrealized_pnl_pct,
        };
      })
    );
  }, []);

  const applyTradeOpened = useCallback(
    () => {
      loadAll();
    },
    [loadAll]
  );

  const applyTradeClosed = useCallback(
    () => {
      loadAll();
      loadHistory(historyPage);
    },
    [loadAll, loadHistory, historyPage]
  );

  const open = useCallback(
    async (params: {
      symbol: string;
      direction: "LONG" | "SHORT";
      position_usdt: number;
      stop_loss?: number | null;
      take_profit_1?: number | null;
      take_profit_2?: number | null;
      take_profit_3?: number | null;
    }) => {
      setOpening(true);
      try {
        const trade = await openPaperTrade(params);
        await loadAll();
        return trade;
      } catch (e) {
        console.error("포지션 진입 실패:", e);
        throw e;
      } finally {
        setOpening(false);
      }
    },
    [loadAll]
  );

  const close = useCallback(
    async (tradeId: number) => {
      try {
        await closePaperTrade(tradeId);
        await loadAll();
        await loadHistory(historyPage);
      } catch (e) {
        console.error("포지션 청산 실패:", e);
        throw e;
      }
    },
    [loadAll, loadHistory, historyPage]
  );

  const reset = useCallback(async () => {
    try {
      await resetPaperAccount();
      await loadAll();
      setHistory([]);
      setHistoryTotal(0);
      setHistoryPageRaw(0);
    } catch (e) {
      console.error("계좌 초기화 실패:", e);
      throw e;
    }
  }, [loadAll]);

  return {
    account,
    positions,
    history,
    historyTotal,
    stats,
    loading,
    opening,
    historyPage,
    setHistoryPage,
    open,
    close,
    reset,
    reload: loadAll,
    applyPositionUpdates,
    applyTradeOpened,
    applyTradeClosed,
  };
}

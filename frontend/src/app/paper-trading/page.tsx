"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useWS } from "@/components/ClientLayout";
import { usePaperTrading } from "@/hooks/usePaperTrading";
import { PaperTrade } from "@/lib/api";
import { formatPrice, timeAgo, formatTime } from "@/lib/utils";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  X,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Trophy,
  BarChart3,
  DollarSign,
  Target,
  Percent,
} from "lucide-react";

const COINS = [
  "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
  "ADA/USDT", "TRX/USDT", "AVAX/USDT", "MATIC/USDT", "LINK/USDT",
];

type Tab = "positions" | "history" | "stats";

export default function PaperTradingPage() {
  const { paperTradeOpened, paperTradeClosed, paperPositionUpdates } = useWS();
  const {
    account, positions, history, historyTotal, stats,
    loading, opening, historyPage, setHistoryPage,
    open, close, reset, reload,
    applyPositionUpdates, applyTradeOpened, applyTradeClosed,
  } = usePaperTrading();

  const searchParams = useSearchParams();
  const [tab, setTab] = useState<Tab>("positions");
  const [error, setError] = useState<string | null>(null);

  // 거래 폼 상태
  const [symbol, setSymbol] = useState(searchParams.get("symbol") || "BTC/USDT");
  const [direction, setDirection] = useState<"LONG" | "SHORT">(
    (searchParams.get("direction") as "LONG" | "SHORT") || "LONG"
  );
  const [amountPct, setAmountPct] = useState(10);
  const [customAmount, setCustomAmount] = useState("");
  const [sl, setSl] = useState(searchParams.get("sl") || "");
  const [tp1, setTp1] = useState(searchParams.get("tp1") || "");
  const [tp2, setTp2] = useState(searchParams.get("tp2") || "");
  const [tp3, setTp3] = useState(searchParams.get("tp3") || "");

  // WS 이벤트 연결
  useEffect(() => {
    if (paperPositionUpdates?.length) applyPositionUpdates(paperPositionUpdates);
  }, [paperPositionUpdates, applyPositionUpdates]);

  useEffect(() => {
    if (paperTradeOpened) applyTradeOpened(paperTradeOpened);
  }, [paperTradeOpened, applyTradeOpened]);

  useEffect(() => {
    if (paperTradeClosed) applyTradeClosed(paperTradeClosed);
  }, [paperTradeClosed, applyTradeClosed]);

  const positionUsdt = customAmount
    ? parseFloat(customAmount)
    : (account?.balance || 0) * (amountPct / 100);

  const handleOpen = useCallback(async () => {
    if (!positionUsdt || positionUsdt <= 0) return;
    setError(null);
    try {
      await open({
        symbol,
        direction,
        position_usdt: positionUsdt,
        stop_loss: sl ? parseFloat(sl) : null,
        take_profit_1: tp1 ? parseFloat(tp1) : null,
        take_profit_2: tp2 ? parseFloat(tp2) : null,
        take_profit_3: tp3 ? parseFloat(tp3) : null,
      });
      setCustomAmount("");
      setSl(""); setTp1(""); setTp2(""); setTp3("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "진입 실패");
    }
  }, [symbol, direction, positionUsdt, sl, tp1, tp2, tp3, open]);

  const handleReset = useCallback(async () => {
    if (!confirm("계좌를 초기화하시겠습니까? 모든 거래 기록이 삭제됩니다.")) return;
    await reset();
  }, [reset]);

  const totalPages = Math.ceil(historyTotal / 20);
  const equity = stats?.equity || account?.balance || 0;
  const totalPnl = account?.total_pnl || 0;
  const totalUnrealized = stats?.total_unrealized_pnl || 0;
  const winRate = account && account.total_trades > 0
    ? ((account.winning_trades / account.total_trades) * 100).toFixed(1)
    : "0.0";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-muted">로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-primary/15 flex items-center justify-center">
            <Wallet size={18} className="text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-heading">모의투자</h2>
            <p className="text-xs text-muted">가상 자금으로 트레이딩 연습</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={reload}
            className="p-2 rounded-card text-muted hover:text-heading hover:bg-card-active transition-colors"
          >
            <RefreshCw size={16} />
          </button>
          <button
            onClick={handleReset}
            className="px-3 py-1.5 text-xs font-medium text-danger bg-danger/10 rounded-card hover:bg-danger/20 transition-colors"
          >
            계좌 초기화
          </button>
        </div>
      </div>

      {/* 계좌 요약 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="총 자산" value={`$${equity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} color="var(--primary)" icon={DollarSign} />
        <StatCard
          label="실현 수익"
          value={`${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`}
          color={totalPnl >= 0 ? "var(--long)" : "var(--short)"}
          icon={TrendingUp}
        />
        <StatCard
          label="미실현 수익"
          value={`${totalUnrealized >= 0 ? "+" : ""}$${totalUnrealized.toFixed(2)}`}
          color={totalUnrealized >= 0 ? "var(--long)" : "var(--short)"}
          icon={BarChart3}
        />
        <StatCard label="승률" value={`${winRate}%`} color="var(--warning)" icon={Trophy} sub={`${account?.winning_trades || 0}W / ${account?.losing_trades || 0}L`} />
      </div>

      {/* 메인 그리드: 좌측 포지션/내역 + 우측 거래 폼 */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* 좌측 (8칸) */}
        <div className="xl:col-span-8">
          {/* 탭 */}
          <div className="cd-card p-0 overflow-hidden">
            <div className="flex border-b border-card-active">
              {([
                { key: "positions" as Tab, label: "포지션", count: positions.length },
                { key: "history" as Tab, label: "거래 내역", count: historyTotal },
                { key: "stats" as Tab, label: "통계" },
              ]).map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`px-4 py-3 text-sm font-medium transition-colors border-b-2 ${
                    tab === t.key
                      ? "border-primary text-primary"
                      : "border-transparent text-muted hover:text-heading"
                  }`}
                >
                  {t.label}
                  {t.count !== undefined && (
                    <span className="ml-1.5 text-xs opacity-60">({t.count})</span>
                  )}
                </button>
              ))}
            </div>

            <div className="p-4">
              {tab === "positions" && <PositionsTab positions={positions} onClose={close} />}
              {tab === "history" && (
                <HistoryTab
                  trades={history}
                  total={historyTotal}
                  page={historyPage}
                  totalPages={totalPages}
                  onPageChange={setHistoryPage}
                />
              )}
              {tab === "stats" && <StatsTab account={account} stats={stats} />}
            </div>
          </div>
        </div>

        {/* 우측: 거래 폼 (4칸) */}
        <div className="xl:col-span-4">
          <div className="cd-card space-y-4">
            <h3 className="text-sm font-semibold text-heading">새 거래</h3>

            {error && (
              <div className="px-3 py-2 text-xs text-danger bg-danger/10 rounded-card">
                {error}
              </div>
            )}

            {/* 심볼 */}
            <div>
              <label className="text-xs text-muted mb-1 block">코인</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-body border border-border text-sm px-3 py-2 rounded-card text-heading"
              >
                {COINS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            {/* 방향 */}
            <div>
              <label className="text-xs text-muted mb-1 block">방향</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setDirection("LONG")}
                  className={`py-2.5 rounded-card text-sm font-semibold transition-colors ${
                    direction === "LONG"
                      ? "bg-long/20 text-long border border-long/40"
                      : "bg-card-active text-muted border border-transparent"
                  }`}
                >
                  LONG
                </button>
                <button
                  onClick={() => setDirection("SHORT")}
                  className={`py-2.5 rounded-card text-sm font-semibold transition-colors ${
                    direction === "SHORT"
                      ? "bg-short/20 text-short border border-short/40"
                      : "bg-card-active text-muted border border-transparent"
                  }`}
                >
                  SHORT
                </button>
              </div>
            </div>

            {/* 포지션 크기 */}
            <div>
              <label className="text-xs text-muted mb-1 block">
                포지션 크기 {!customAmount && <span className="text-heading">({amountPct}% = ${positionUsdt.toFixed(2)})</span>}
              </label>
              <div className="flex gap-1.5 mb-2">
                {[10, 25, 50, 100].map((pct) => (
                  <button
                    key={pct}
                    onClick={() => { setAmountPct(pct); setCustomAmount(""); }}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-card transition-colors ${
                      amountPct === pct && !customAmount
                        ? "bg-primary/15 text-primary"
                        : "bg-card-active text-muted hover:text-heading"
                    }`}
                  >
                    {pct}%
                  </button>
                ))}
              </div>
              <input
                type="number"
                placeholder="직접 입력 (USDT)"
                value={customAmount}
                onChange={(e) => setCustomAmount(e.target.value)}
                className="w-full bg-body border border-border text-sm px-3 py-2 rounded-card text-heading placeholder-muted"
              />
            </div>

            {/* SL / TP */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-muted mb-1 block">손절가 (SL)</label>
                <input
                  type="number"
                  placeholder="선택"
                  value={sl}
                  onChange={(e) => setSl(e.target.value)}
                  className="w-full bg-body border border-border text-xs px-2.5 py-1.5 rounded-card text-heading placeholder-muted"
                />
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">목표가 1 (TP1)</label>
                <input
                  type="number"
                  placeholder="선택"
                  value={tp1}
                  onChange={(e) => setTp1(e.target.value)}
                  className="w-full bg-body border border-border text-xs px-2.5 py-1.5 rounded-card text-heading placeholder-muted"
                />
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">목표가 2 (TP2)</label>
                <input
                  type="number"
                  placeholder="선택"
                  value={tp2}
                  onChange={(e) => setTp2(e.target.value)}
                  className="w-full bg-body border border-border text-xs px-2.5 py-1.5 rounded-card text-heading placeholder-muted"
                />
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">목표가 3 (TP3)</label>
                <input
                  type="number"
                  placeholder="선택"
                  value={tp3}
                  onChange={(e) => setTp3(e.target.value)}
                  className="w-full bg-body border border-border text-xs px-2.5 py-1.5 rounded-card text-heading placeholder-muted"
                />
              </div>
            </div>

            {/* 잔고 정보 */}
            <div className="text-xs text-muted flex justify-between">
              <span>가용 잔고</span>
              <span className="text-heading font-medium">${(account?.balance || 0).toFixed(2)}</span>
            </div>

            {/* 진입 버튼 */}
            <button
              onClick={handleOpen}
              disabled={opening || positionUsdt <= 0}
              className={`w-full py-3 rounded-card text-sm font-semibold transition-colors disabled:opacity-50 ${
                direction === "LONG"
                  ? "bg-long text-white hover:bg-long/80"
                  : "bg-short text-white hover:bg-short/80"
              }`}
            >
              {opening ? "진입 중..." : `${direction} 진입`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── 하위 컴포넌트 ─────────────────────────────────────────

function StatCard({ label, value, color, icon: Icon, sub }: {
  label: string; value: string; color: string; icon: typeof DollarSign; sub?: string;
}) {
  return (
    <div className="cd-card flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: `${color}15` }}>
        <Icon size={20} style={{ color }} />
      </div>
      <div className="min-w-0">
        <div className="text-xs text-muted mb-0.5 truncate">{label}</div>
        <div className="text-lg font-bold text-heading">{value}</div>
        {sub && <div className="text-xs text-muted">{sub}</div>}
      </div>
    </div>
  );
}

function PositionsTab({ positions, onClose }: { positions: PaperTrade[]; onClose: (id: number) => void }) {
  if (!positions.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted">
        <Target size={32} className="mb-3 text-icon-muted" />
        <p className="text-sm font-medium text-heading mb-1">열린 포지션 없음</p>
        <p className="text-xs">우측 폼에서 새 거래를 시작하세요</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {positions.map((pos) => {
        const isLong = pos.direction === "LONG";
        const pnl = pos.unrealized_pnl || 0;
        const pnlPct = pos.unrealized_pnl_pct || 0;
        const isProfit = pnl >= 0;
        return (
          <div key={pos.id} className="cd-card p-3 space-y-2" style={{ borderLeft: `3px solid ${isLong ? "var(--long)" : "var(--short)"}` }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-heading">{pos.symbol}</span>
                <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                  isLong ? "bg-long/15 text-long" : "bg-short/15 text-short"
                }`}>
                  {pos.direction}
                </span>
              </div>
              <button
                onClick={() => onClose(pos.id)}
                className="p-1 rounded text-muted hover:text-danger hover:bg-danger/10 transition-colors"
                title="청산"
              >
                <X size={14} />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-muted">진입가</span>
                <span className="text-heading font-mono">${formatPrice(pos.entry_price)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">현재가</span>
                <span className="text-heading font-mono">${formatPrice(pos.current_price || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">크기</span>
                <span className="text-heading">${pos.position_usdt.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">수익</span>
                <span className={`font-semibold ${isProfit ? "text-long" : "text-short"}`}>
                  {isProfit ? "+" : ""}{pnlPct.toFixed(2)}%
                </span>
              </div>
            </div>

            {/* P&L 바 */}
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-card-active rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(Math.abs(pnlPct) * 5, 100)}%`,
                    backgroundColor: isProfit ? "var(--long)" : "var(--short)",
                  }}
                />
              </div>
              <span className={`text-xs font-mono font-semibold ${isProfit ? "text-long" : "text-short"}`}>
                {isProfit ? "+" : ""}${pnl.toFixed(2)}
              </span>
            </div>

            {/* SL/TP */}
            {(pos.stop_loss || pos.take_profit_1) && (
              <div className="flex gap-2 text-[10px] text-muted">
                {pos.stop_loss && <span>SL: ${formatPrice(pos.stop_loss)}</span>}
                {pos.take_profit_1 && <span>TP1: ${formatPrice(pos.take_profit_1)}</span>}
                {pos.take_profit_2 && <span>TP2: ${formatPrice(pos.take_profit_2)}</span>}
                {pos.take_profit_3 && <span>TP3: ${formatPrice(pos.take_profit_3)}</span>}
              </div>
            )}

            <div className="text-[10px] text-muted">{timeAgo(pos.opened_at)}</div>
          </div>
        );
      })}
    </div>
  );
}

function HistoryTab({ trades, total, page, totalPages, onPageChange }: {
  trades: PaperTrade[]; total: number; page: number; totalPages: number; onPageChange: (p: number) => void;
}) {
  if (!trades.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted">
        <BarChart3 size={32} className="mb-3 text-icon-muted" />
        <p className="text-sm font-medium text-heading mb-1">거래 내역 없음</p>
        <p className="text-xs">포지션을 청산하면 여기에 표시됩니다</p>
      </div>
    );
  }

  const reasonLabels: Record<string, string> = {
    MANUAL: "수동 청산",
    HIT_SL: "손절",
    HIT_TP1: "목표1 도달",
    HIT_TP2: "목표2 도달",
    HIT_TP3: "목표3 도달",
  };

  return (
    <div>
      <div className="overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-muted text-left text-xs">
              <th className="px-3 py-2 font-medium">시간</th>
              <th className="px-3 py-2 font-medium">코인</th>
              <th className="px-3 py-2 font-medium">방향</th>
              <th className="px-3 py-2 font-medium">진입가</th>
              <th className="px-3 py-2 font-medium">청산가</th>
              <th className="px-3 py-2 font-medium">P&L</th>
              <th className="px-3 py-2 font-medium">사유</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const isProfit = (t.realized_pnl || 0) >= 0;
              return (
                <tr key={t.id} className="border-t border-card-active">
                  <td className="px-3 py-2 text-xs text-muted">{formatTime(t.closed_at || t.updated_at)}</td>
                  <td className="px-3 py-2 text-heading font-medium">{t.symbol}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs font-bold ${t.direction === "LONG" ? "text-long" : "text-short"}`}>
                      {t.direction}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">${formatPrice(t.entry_price)}</td>
                  <td className="px-3 py-2 font-mono text-xs">${formatPrice(t.close_price || 0)}</td>
                  <td className={`px-3 py-2 font-mono text-xs font-semibold ${isProfit ? "text-long" : "text-short"}`}>
                    {isProfit ? "+" : ""}{(t.realized_pnl_pct || 0).toFixed(2)}%
                    <div className="text-[10px] opacity-70">
                      {isProfit ? "+" : ""}${(t.realized_pnl || 0).toFixed(2)}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted">
                    {reasonLabels[t.close_reason || ""] || t.close_reason}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-3 border-t border-card-active">
          <span className="text-xs text-muted">
            총 {total}건 / {page + 1} of {totalPages}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 0}
              className="p-1.5 rounded-card text-muted hover:text-heading disabled:opacity-30"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages - 1}
              className="p-1.5 rounded-card text-muted hover:text-heading disabled:opacity-30"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function StatsTab({ account, stats }: {
  account: ReturnType<typeof usePaperTrading>["account"];
  stats: ReturnType<typeof usePaperTrading>["stats"];
}) {
  if (!account) return null;

  const winRate = account.total_trades > 0
    ? (account.winning_trades / account.total_trades * 100).toFixed(1)
    : "0.0";
  const returnPct = account.initial_balance > 0
    ? ((account.total_pnl / account.initial_balance) * 100).toFixed(2)
    : "0.00";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <MiniStat label="총 거래" value={String(account.total_trades)} icon={BarChart3} />
        <MiniStat label="승리" value={String(account.winning_trades)} icon={TrendingUp} color="var(--long)" />
        <MiniStat label="패배" value={String(account.losing_trades)} icon={TrendingDown} color="var(--short)" />
        <MiniStat label="승률" value={`${winRate}%`} icon={Percent} />
        <MiniStat label="총 수익률" value={`${parseFloat(returnPct) >= 0 ? "+" : ""}${returnPct}%`} icon={Trophy} color={parseFloat(returnPct) >= 0 ? "var(--long)" : "var(--short)"} />
        <MiniStat label="실현 수익" value={`$${account.total_pnl.toFixed(2)}`} icon={DollarSign} color={account.total_pnl >= 0 ? "var(--long)" : "var(--short)"} />
      </div>

      <div className="cd-card bg-card-active">
        <div className="text-xs text-muted mb-2">계좌 정보</div>
        <div className="space-y-1.5 text-sm">
          <div className="flex justify-between">
            <span className="text-muted">초기 자본</span>
            <span className="text-heading">${account.initial_balance.toLocaleString()}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">현재 잔고</span>
            <span className="text-heading">${account.balance.toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">총 자산 (잔고+미실현)</span>
            <span className="text-heading font-semibold">${(stats?.equity || account.balance).toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">열린 포지션</span>
            <span className="text-heading">{stats?.open_positions || 0}개</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, icon: Icon, color }: {
  label: string; value: string; icon: typeof BarChart3; color?: string;
}) {
  return (
    <div className="cd-card p-3 text-center">
      <Icon size={16} className="mx-auto mb-1" style={{ color: color || "var(--text-muted)" }} />
      <div className="text-lg font-bold text-heading" style={color ? { color } : {}}>{value}</div>
      <div className="text-[10px] text-muted">{label}</div>
    </div>
  );
}

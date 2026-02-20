"use client";

import { useState, useEffect, useCallback } from "react";
import {
  AlertConfig,
  AutoTradeConfig,
  PortfolioRiskReport,
  BacktestStats,
  LearningWeights,
  MarketContext,
  fetchAlertConfig,
  updateAlertConfig,
  fetchAutoTradeConfig,
  updateAutoTradeConfig,
  fetchPortfolioRisk,
  fetchBacktestStats,
  fetchLearningWeights,
  triggerLearning,
  fetchMarketContext,
} from "@/lib/api";
import { signalColor } from "@/lib/utils";
import { TableSkeleton } from "@/components/Skeleton";
import {
  Settings,
  Bot,
  ShieldAlert,
  Bell,
  BarChart3,
  Brain,
  Globe,
  Check,
  RefreshCw,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

const SIGNAL_OPTIONS = ["STRONG_LONG", "LONG", "SHORT", "STRONG_SHORT"];

type Tab = "auto-trade" | "risk" | "alerts" | "backtest" | "learning" | "market";

const TABS: { id: Tab; label: string; icon: typeof Settings }[] = [
  { id: "auto-trade", label: "자동매매", icon: Bot },
  { id: "risk", label: "리스크", icon: ShieldAlert },
  { id: "alerts", label: "알림", icon: Bell },
  { id: "backtest", label: "백테스트", icon: BarChart3 },
  { id: "learning", label: "학습", icon: Brain },
  { id: "market", label: "시장 맥락", icon: Globe },
];

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("auto-trade");
  const [loading, setLoading] = useState(true);

  // Auto-trade
  const [atConfig, setAtConfig] = useState<AutoTradeConfig | null>(null);
  const [atSaving, setAtSaving] = useState(false);
  const [atSaved, setAtSaved] = useState(false);

  // Alert
  const [alertConfig, setAlertConfig] = useState<AlertConfig | null>(null);
  const [alertSaving, setAlertSaving] = useState(false);
  const [alertSaved, setAlertSaved] = useState(false);

  // Risk
  const [riskReport, setRiskReport] = useState<PortfolioRiskReport | null>(null);

  // Backtest
  const [btStats, setBtStats] = useState<BacktestStats | null>(null);

  // Learning
  const [weights, setWeights] = useState<LearningWeights | null>(null);
  const [learningRunning, setLearningRunning] = useState(false);

  // Market context
  const [marketCtx, setMarketCtx] = useState<MarketContext | null>(null);

  // 에러 상태
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    const newErrors: Record<string, string> = {};
    try {
      const [at, al, risk, bt, lw, mc] = await Promise.allSettled([
        fetchAutoTradeConfig(),
        fetchAlertConfig(),
        fetchPortfolioRisk(),
        fetchBacktestStats(),
        fetchLearningWeights(),
        fetchMarketContext(),
      ]);
      if (at.status === "fulfilled") setAtConfig(at.value);
      else newErrors["auto-trade"] = at.reason?.message || "로드 실패";
      if (al.status === "fulfilled") setAlertConfig(al.value);
      else newErrors["alerts"] = al.reason?.message || "로드 실패";
      if (risk.status === "fulfilled") setRiskReport(risk.value);
      else newErrors["risk"] = risk.reason?.message || "로드 실패";
      if (bt.status === "fulfilled") setBtStats(bt.value);
      else newErrors["backtest"] = bt.reason?.message || "로드 실패";
      if (lw.status === "fulfilled") setWeights(lw.value);
      else newErrors["learning"] = lw.reason?.message || "로드 실패";
      if (mc.status === "fulfilled") setMarketCtx(mc.value);
      else newErrors["market"] = mc.reason?.message || "로드 실패";
    } finally {
      setErrors(newErrors);
      setLoading(false);
    }
  };

  // ─── Auto-trade save
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSaveAutoTrade = useCallback(async () => {
    if (!atConfig) return;
    setAtSaving(true);
    setSaveError(null);
    try {
      const updated = await updateAutoTradeConfig(atConfig);
      setAtConfig(updated);
      setAtSaved(true);
      setTimeout(() => setAtSaved(false), 2000);
    } catch (e) {
      setSaveError(`자동매매 설정 저장 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setAtSaving(false);
    }
  }, [atConfig]);

  // ─── Alert save
  const handleSaveAlert = useCallback(async () => {
    if (!alertConfig) return;
    setAlertSaving(true);
    setSaveError(null);
    try {
      const updated = await updateAlertConfig(alertConfig);
      setAlertConfig(updated);
      setAlertSaved(true);
      setTimeout(() => setAlertSaved(false), 2000);
    } catch (e) {
      setSaveError(`알림 설정 저장 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setAlertSaving(false);
    }
  }, [alertConfig]);

  const toggleSignalType = (type: string) => {
    if (!alertConfig) return;
    const types = alertConfig.signal_types.includes(type)
      ? alertConfig.signal_types.filter((t) => t !== type)
      : [...alertConfig.signal_types, type];
    setAlertConfig({ ...alertConfig, signal_types: types });
  };

  // ─── Learning run
  const handleRunLearning = useCallback(async () => {
    setLearningRunning(true);
    try {
      const result = await triggerLearning();
      setWeights((prev) =>
        prev ? { ...prev, weights: result.weights, is_adaptive: true } : prev
      );
    } catch (e) {
      console.error("학습 실행 실패:", e);
    } finally {
      setLearningRunning(false);
    }
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-bold text-heading">설정 / 관리</h1>
        <TableSkeleton rows={8} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Settings size={22} className="text-primary" />
        <h1 className="text-xl font-bold text-heading">설정 / 관리</h1>
      </div>

      {/* 탭 */}
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto pb-px">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                tab === t.id
                  ? "border-primary text-heading"
                  : "border-transparent text-muted hover:text-heading"
              }`}
            >
              <Icon size={15} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* 에러 배너 */}
      {errors[tab] && (
        <div className="flex items-center gap-2 p-3 rounded-card bg-danger/10 border border-danger/30 text-sm text-danger">
          <AlertTriangle size={16} className="shrink-0" />
          <span>데이터 로드 실패: {errors[tab]}</span>
          <button
            onClick={loadAll}
            className="ml-auto text-xs underline hover:no-underline"
          >
            재시도
          </button>
        </div>
      )}
      {saveError && (
        <div className="flex items-center gap-2 p-3 rounded-card bg-danger/10 border border-danger/30 text-sm text-danger">
          <AlertTriangle size={16} className="shrink-0" />
          <span>{saveError}</span>
          <button
            onClick={() => setSaveError(null)}
            className="ml-auto text-xs underline hover:no-underline"
          >
            닫기
          </button>
        </div>
      )}

      {/* ═══ 자동매매 ═══ */}
      {tab === "auto-trade" && atConfig && (
        <div className="max-w-[640px] space-y-5">
          {/* ON/OFF */}
          <div className="cd-card">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-heading">자동매매 활성화</h3>
                <p className="text-sm text-muted mt-1">
                  CONFIRMED 시그널 발생 시 자동으로 모의투자 포지션을 오픈합니다
                </p>
              </div>
              <button
                onClick={() =>
                  setAtConfig({ ...atConfig, enabled: !atConfig.enabled })
                }
                className={`w-12 h-6 rounded-full transition-colors relative ${
                  atConfig.enabled ? "bg-primary" : "bg-icon-muted"
                }`}
              >
                <span
                  className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    atConfig.enabled ? "left-[26px]" : "left-0.5"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* 최대 동시 포지션 */}
          <div className="cd-card">
            <h3 className="font-semibold text-heading mb-3">
              최대 동시 포지션
            </h3>
            <p className="text-sm text-muted mb-3">
              한 번에 열 수 있는 최대 포지션 수 (1~10)
            </p>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={1}
                max={10}
                step={1}
                value={atConfig.max_positions}
                onChange={(e) =>
                  setAtConfig({
                    ...atConfig,
                    max_positions: parseInt(e.target.value),
                  })
                }
                className="flex-1 accent-primary"
              />
              <span className="text-sm font-mono font-bold text-heading w-10 text-right">
                {atConfig.max_positions}개
              </span>
            </div>
          </div>

          {/* 최대 포지션 비율 */}
          <div className="cd-card">
            <h3 className="font-semibold text-heading mb-3">
              포지션 최대 비율 (%)
            </h3>
            <p className="text-sm text-muted mb-3">
              자본 대비 개별 포지션 최대 크기 (1%~50%)
            </p>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={1}
                max={50}
                step={1}
                value={atConfig.max_position_pct}
                onChange={(e) =>
                  setAtConfig({
                    ...atConfig,
                    max_position_pct: parseFloat(e.target.value),
                  })
                }
                className="flex-1 accent-primary"
              />
              <span className="text-sm font-mono font-bold text-heading w-12 text-right">
                {atConfig.max_position_pct}%
              </span>
            </div>
          </div>

          <button
            onClick={handleSaveAutoTrade}
            disabled={atSaving}
            className="w-full py-3 bg-primary hover:bg-primary/80 text-white font-medium rounded-card transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {atSaved ? (
              <>
                <Check size={16} /> 저장됨
              </>
            ) : atSaving ? (
              "저장 중..."
            ) : (
              "설정 저장"
            )}
          </button>
        </div>
      )}

      {/* ═══ 리스크 ═══ */}
      {tab === "risk" && (
        <div className="max-w-[800px] space-y-5">
          {riskReport ? (
            <>
              {/* 리스크 요약 카드 */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="cd-card text-center">
                  <p className="text-xs text-muted mb-1">총 노출</p>
                  <p className="text-lg font-bold text-heading">
                    {(riskReport.total_exposure_pct ?? 0).toFixed(1)}%
                  </p>
                </div>
                <div className="cd-card text-center">
                  <p className="text-xs text-muted mb-1">포지션 수</p>
                  <p className="text-lg font-bold text-heading">
                    {riskReport.position_count ?? 0}
                  </p>
                </div>
                <div className="cd-card text-center">
                  <p className="text-xs text-muted mb-1">VaR (95%)</p>
                  <p className="text-lg font-bold text-danger">
                    {(riskReport.var_95 ?? 0).toFixed(2)}%
                  </p>
                </div>
                <div className="cd-card text-center">
                  <p className="text-xs text-muted mb-1">상관 그룹</p>
                  <p className="text-lg font-bold text-heading">
                    {riskReport.max_correlated ?? 0}
                  </p>
                </div>
              </div>

              {/* 경고 */}
              {riskReport.warnings && riskReport.warnings.length > 0 && (
                <div className="cd-card border-warning/40">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle size={16} className="text-warning" />
                    <h3 className="font-semibold text-heading">리스크 경고</h3>
                  </div>
                  <ul className="space-y-1.5">
                    {riskReport.warnings.map((w, i) => (
                      <li
                        key={i}
                        className="text-sm text-warning flex items-start gap-2"
                      >
                        <span className="shrink-0 mt-0.5">-</span>
                        {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 포지션 목록 */}
              {riskReport.positions && riskReport.positions.length > 0 && (
                <div className="cd-card">
                  <h3 className="font-semibold text-heading mb-3">
                    포지션 비중
                  </h3>
                  <div className="space-y-2">
                    {riskReport.positions.map((p) => (
                      <div
                        key={p.symbol}
                        className="flex items-center justify-between"
                      >
                        <span className="text-sm font-medium text-heading">
                          {p.symbol}
                        </span>
                        <div className="flex items-center gap-3 flex-1 ml-4">
                          <div className="flex-1 h-2 bg-card-active rounded-full overflow-hidden">
                            <div
                              className="h-full bg-primary rounded-full"
                              style={{
                                width: `${Math.min(p.weight_pct, 100)}%`,
                              }}
                            />
                          </div>
                          <span className="text-xs font-mono text-muted w-14 text-right">
                            {p.weight_pct.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <button
                onClick={async () => {
                  try {
                    setRiskReport(await fetchPortfolioRisk());
                  } catch (e) {
                    setSaveError(`리스크 갱신 실패: ${e instanceof Error ? e.message : String(e)}`);
                  }
                }}
                className="flex items-center gap-2 text-sm text-primary hover:underline"
              >
                <RefreshCw size={14} /> 새로고침
              </button>
            </>
          ) : (
            <div className="text-center py-12 text-muted">
              <ShieldAlert size={32} className="mx-auto mb-3 text-icon-muted" />
              <p>열린 포지션이 없어 리스크 보고서가 비어 있습니다</p>
            </div>
          )}
        </div>
      )}

      {/* ═══ 알림 ═══ */}
      {tab === "alerts" && alertConfig && (
        <div className="max-w-[600px] space-y-5">
          {/* ON/OFF */}
          <div className="cd-card">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-heading">알림 활성화</h3>
                <p className="text-sm text-muted mt-1">
                  시그널 감지 시 실시간 알림을 받습니다
                </p>
              </div>
              <button
                onClick={() =>
                  setAlertConfig({
                    ...alertConfig,
                    enabled: !alertConfig.enabled,
                  })
                }
                className={`w-12 h-6 rounded-full transition-colors relative ${
                  alertConfig.enabled ? "bg-primary" : "bg-icon-muted"
                }`}
              >
                <span
                  className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    alertConfig.enabled ? "left-[26px]" : "left-0.5"
                  }`}
                />
              </button>
            </div>
          </div>

          {/* 최소 신뢰도 */}
          <div className="cd-card">
            <h3 className="font-semibold text-heading mb-3">최소 신뢰도</h3>
            <p className="text-sm text-muted mb-3">
              이 값 이상의 신뢰도를 가진 시그널만 알림을 받습니다
            </p>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={0.3}
                max={0.9}
                step={0.05}
                value={alertConfig.min_confidence}
                onChange={(e) =>
                  setAlertConfig({
                    ...alertConfig,
                    min_confidence: parseFloat(e.target.value),
                  })
                }
                className="flex-1 accent-primary"
              />
              <span className="text-sm font-mono font-bold text-heading w-12 text-right">
                {(alertConfig.min_confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          {/* 시그널 타입 */}
          <div className="cd-card">
            <h3 className="font-semibold text-heading mb-3">시그널 타입</h3>
            <p className="text-sm text-muted mb-3">
              알림을 받을 시그널 타입을 선택합니다
            </p>
            <div className="grid grid-cols-2 gap-2">
              {SIGNAL_OPTIONS.map((type) => {
                const active = alertConfig.signal_types.includes(type);
                const color = signalColor(type);
                return (
                  <button
                    key={type}
                    onClick={() => toggleSignalType(type)}
                    className={`p-3 rounded-card border text-sm font-medium transition-colors ${
                      active
                        ? "border-current"
                        : "border-border text-muted hover:text-heading"
                    }`}
                    style={
                      active
                        ? {
                            color,
                            borderColor: color,
                            backgroundColor: `color-mix(in srgb, ${color} 8%, transparent)`,
                          }
                        : undefined
                    }
                  >
                    {type.replace("_", " ")}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 쿨다운 */}
          <div className="cd-card">
            <h3 className="font-semibold text-heading mb-3">쿨다운 (분)</h3>
            <p className="text-sm text-muted mb-3">
              같은 심볼+시그널에 대해 중복 알림을 방지하는 시간 간격
            </p>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={5}
                max={120}
                step={5}
                value={alertConfig.cooldown_minutes}
                onChange={(e) =>
                  setAlertConfig({
                    ...alertConfig,
                    cooldown_minutes: parseInt(e.target.value),
                  })
                }
                className="flex-1 accent-primary"
              />
              <span className="text-sm font-mono font-bold text-heading w-16 text-right">
                {alertConfig.cooldown_minutes}분
              </span>
            </div>
          </div>

          <button
            onClick={handleSaveAlert}
            disabled={alertSaving}
            className="w-full py-3 bg-primary hover:bg-primary/80 text-white font-medium rounded-card transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {alertSaved ? (
              <>
                <Check size={16} /> 저장됨
              </>
            ) : alertSaving ? (
              "저장 중..."
            ) : (
              "설정 저장"
            )}
          </button>
        </div>
      )}

      {/* ═══ 백테스트 ═══ */}
      {tab === "backtest" && (
        <div className="max-w-[800px] space-y-5">
          {btStats ? (
            <>
              {/* 기본 통계 */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard
                  label="총 예측"
                  value={String(btStats.total_predictions ?? 0)}
                />
                <StatCard
                  label="검증 완료"
                  value={String(btStats.verified_count ?? 0)}
                />
                <StatCard
                  label="승률"
                  value={`${((btStats.win_rate ?? 0) * 100).toFixed(1)}%`}
                  color={
                    (btStats.win_rate ?? 0) >= 0.5
                      ? "text-success"
                      : "text-danger"
                  }
                />
                <StatCard
                  label="평균 정확도"
                  value={`${((btStats.avg_accuracy ?? 0) * 100).toFixed(1)}%`}
                />
              </div>

              {/* 고급 통계 */}
              {btStats.advanced_stats && (
                <div className="cd-card">
                  <h3 className="font-semibold text-heading mb-4">
                    고급 통계
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-y-4 gap-x-6">
                    <AdvStat
                      label="Sharpe Ratio"
                      value={btStats.advanced_stats.sharpe_ratio?.toFixed(3)}
                    />
                    <AdvStat
                      label="Sortino Ratio"
                      value={btStats.advanced_stats.sortino_ratio?.toFixed(3)}
                    />
                    <AdvStat
                      label="Profit Factor"
                      value={btStats.advanced_stats.profit_factor?.toFixed(2)}
                    />
                    <AdvStat
                      label="Max Drawdown"
                      value={`${(
                        (btStats.advanced_stats.max_drawdown ?? 0) * 100
                      ).toFixed(2)}%`}
                      className="text-danger"
                    />
                    <AdvStat
                      label="평균 보유시간"
                      value={`${(
                        btStats.advanced_stats.avg_hold_hours ?? 0
                      ).toFixed(1)}h`}
                    />
                    <AdvStat
                      label="연속 승/패"
                      value={`${btStats.advanced_stats.consecutive_wins ?? 0}W / ${btStats.advanced_stats.consecutive_losses ?? 0}L`}
                    />
                  </div>
                </div>
              )}

              <button
                onClick={async () => {
                  try {
                    setBtStats(await fetchBacktestStats());
                  } catch (e) {
                    setSaveError(`백테스트 갱신 실패: ${e instanceof Error ? e.message : String(e)}`);
                  }
                }}
                className="flex items-center gap-2 text-sm text-primary hover:underline"
              >
                <RefreshCw size={14} /> 새로고침
              </button>
            </>
          ) : (
            <div className="text-center py-12 text-muted">
              <BarChart3 size={32} className="mx-auto mb-3 text-icon-muted" />
              <p>백테스트 데이터가 아직 없습니다</p>
              <p className="text-xs mt-1">
                예측이 검증되면 통계가 생성됩니다
              </p>
            </div>
          )}
        </div>
      )}

      {/* ═══ 학습 ═══ */}
      {tab === "learning" && (
        <div className="max-w-[640px] space-y-5">
          {weights ? (
            <>
              <div className="cd-card">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-heading">
                    시그널 카테고리 가중치
                  </h3>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      weights.is_adaptive
                        ? "bg-success/15 text-success"
                        : "bg-card-active text-muted"
                    }`}
                  >
                    {weights.is_adaptive ? "적응형" : "기본값"}
                  </span>
                </div>
                <div className="space-y-3">
                  {Object.entries(weights.weights).map(([key, val]) => {
                    const defVal = weights.default_weights[key] ?? 0;
                    const diff = val - defVal;
                    return (
                      <div key={key}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-body-text capitalize">
                            {key.replace(/_/g, " ")}
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-mono font-bold text-heading">
                              {(val * 100).toFixed(1)}%
                            </span>
                            {Math.abs(diff) > 0.001 && (
                              <span
                                className={`text-xs ${diff > 0 ? "text-success" : "text-danger"}`}
                              >
                                {diff > 0 ? "+" : ""}
                                {(diff * 100).toFixed(1)}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="h-2 bg-card-active rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full transition-all"
                            style={{ width: `${val * 100 * 2}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <button
                onClick={handleRunLearning}
                disabled={learningRunning}
                className="w-full py-3 bg-primary hover:bg-primary/80 text-white font-medium rounded-card transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {learningRunning ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" /> 학습 실행
                    중...
                  </>
                ) : (
                  <>
                    <Brain size={16} /> 자기학습 실행
                  </>
                )}
              </button>
            </>
          ) : (
            <div className="text-center py-12 text-muted">
              <Brain size={32} className="mx-auto mb-3 text-icon-muted" />
              <p>학습 데이터를 불러올 수 없습니다</p>
            </div>
          )}
        </div>
      )}

      {/* ═══ 시장 맥락 ═══ */}
      {tab === "market" && (
        <div className="max-w-[800px] space-y-5">
          {marketCtx && Object.keys(marketCtx).length > 0 ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {/* BTC Signal */}
                {marketCtx.btc_signal && (
                  <div className="cd-card text-center">
                    <p className="text-xs text-muted mb-1">BTC 시그널</p>
                    <p
                      className="text-lg font-bold"
                      style={{
                        color: signalColor(marketCtx.btc_signal),
                      }}
                    >
                      {marketCtx.btc_signal}
                    </p>
                  </div>
                )}

                {/* Market Sentiment */}
                {marketCtx.market_sentiment && (
                  <div className="cd-card text-center">
                    <p className="text-xs text-muted mb-1">시장 분위기</p>
                    <p className="text-lg font-bold text-heading flex items-center justify-center gap-1">
                      {marketCtx.market_sentiment === "BULLISH" ? (
                        <TrendingUp size={18} className="text-success" />
                      ) : marketCtx.market_sentiment === "BEARISH" ? (
                        <TrendingDown size={18} className="text-danger" />
                      ) : null}
                      {marketCtx.market_sentiment}
                    </p>
                  </div>
                )}

                {/* Fear & Greed */}
                {marketCtx.fear_greed != null && (
                  <div className="cd-card text-center">
                    <p className="text-xs text-muted mb-1">공포/탐욕 지수</p>
                    <p className="text-lg font-bold text-heading">
                      {marketCtx.fear_greed}
                    </p>
                    {marketCtx.fear_greed_label && (
                      <p className="text-xs text-muted">
                        {marketCtx.fear_greed_label}
                      </p>
                    )}
                  </div>
                )}

                {/* Breadth */}
                {marketCtx.breadth_ratio != null && (
                  <div className="cd-card text-center">
                    <p className="text-xs text-muted mb-1">상승 비율</p>
                    <p className="text-lg font-bold text-heading">
                      {((marketCtx.breadth_ratio as number) * 100).toFixed(0)}%
                    </p>
                  </div>
                )}

                {/* Sentiment Score */}
                {marketCtx.sentiment_score != null && (
                  <div className="cd-card text-center">
                    <p className="text-xs text-muted mb-1">감성 점수</p>
                    <p
                      className={`text-lg font-bold ${(marketCtx.sentiment_score as number) > 0 ? "text-success" : (marketCtx.sentiment_score as number) < 0 ? "text-danger" : "text-heading"}`}
                    >
                      {(marketCtx.sentiment_score as number) > 0 ? "+" : ""}
                      {(marketCtx.sentiment_score as number).toFixed(2)}
                    </p>
                  </div>
                )}
              </div>

              <button
                onClick={async () => {
                  try {
                    setMarketCtx(await fetchMarketContext());
                  } catch (e) {
                    setSaveError(`시장 맥락 갱신 실패: ${e instanceof Error ? e.message : String(e)}`);
                  }
                }}
                className="flex items-center gap-2 text-sm text-primary hover:underline"
              >
                <RefreshCw size={14} /> 새로고침
              </button>
            </>
          ) : (
            <div className="text-center py-12 text-muted">
              <Globe size={32} className="mx-auto mb-3 text-icon-muted" />
              <p>시장 맥락 데이터가 아직 없습니다</p>
              <p className="text-xs mt-1">
                1h 스캔이 실행되면 자동으로 갱신됩니다
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── 헬퍼 컴포넌트 ─────────────────────────────────

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="cd-card text-center">
      <p className="text-xs text-muted mb-1">{label}</p>
      <p className={`text-lg font-bold ${color || "text-heading"}`}>{value}</p>
    </div>
  );
}

function AdvStat({
  label,
  value,
  className,
}: {
  label: string;
  value?: string;
  className?: string;
}) {
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <p className={`text-sm font-mono font-bold ${className || "text-heading"}`}>
        {value ?? "-"}
      </p>
    </div>
  );
}

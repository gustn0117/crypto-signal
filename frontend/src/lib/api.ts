const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── 에러 처리 래퍼 ───────────────────────────────────

async function fetchWithError<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── 인터페이스 ────────────────────────────────────────

export interface SignalTrack {
  state: "FORMING" | "CONFIRMING" | "CONFIRMED" | "WEAKENING";
  consecutive_scans: number;
  first_detected_at: string;
  confirmed_at: string | null;
  peak_confidence: number;
}

export interface Signal {
  symbol: string;
  timeframe: string;
  signal: "STRONG_LONG" | "LONG" | "NEUTRAL" | "SHORT" | "STRONG_SHORT";
  confidence: number;
  current_price: number;
  indicators: Indicator[];
  candle_patterns: CandlePattern[];
  chart_patterns: CandlePattern[];
  volume_signals: VolumeSignal[];
  futures_signals: FuturesSignal[];
  summary: string;
  timestamp: string;
  trade_params?: TradeParamsData;
  mtf_confirmation?: MTFData;
  price_levels?: PriceLevelsData;
  track?: SignalTrack;
  quality?: SignalQuality;
}

export interface SignalQuality {
  signal_win_rate?: number;
  signal_total?: number;
  confidence_win_rate?: number;
  btc_beta?: number;
}

export interface TradeParamsData {
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  take_profit_3: number;
  risk_reward_ratio: number;
  risk_percent: number;
  position_direction: string;
}

export interface MTFData {
  higher_tf: string;
  higher_tf_trend: string;
  alignment: string;
  confidence_modifier: number;
  description: string;
}

export interface PriceLevelsData {
  atr: number;
  atr_percent: number;
  support_levels: number[];
  resistance_levels: number[];
  recent_high: number;
  recent_low: number;
}

export interface Indicator {
  name: string;
  signal: string;
  strength: number;
  value: number;
  description: string;
}

export interface CandlePattern {
  name: string;
  signal: string;
  strength: number;
  description: string;
}

export interface VolumeSignal {
  name: string;
  signal: string;
  strength: number;
  value: number;
  description: string;
}

export interface FuturesSignal {
  name: string;
  signal: string;
  strength: number;
  value: number;
  description: string;
}

export interface Market {
  symbol: string;
  price: number;
  change_24h: number;
  volume_usdt: number;
  high_24h: number;
  low_24h: number;
}

export interface Ticker {
  symbol: string;
  price: number;
  change_24h: number;
  volume_usdt: number;
  high_24h: number;
  low_24h: number;
  bid: number;
  ask: number;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Alert {
  id: number;
  symbol: string;
  signal: string;
  confidence: number;
  current_price: number;
  summary: string;
  trade_params?: TradeParamsData;
  timestamp: string;
  read: boolean;
}

export interface AlertConfig {
  enabled: boolean;
  min_confidence: number;
  signal_types: string[];
  cooldown_minutes: number;
}

export interface PredictionPoint {
  time: number;
  price: number;
}

export interface Prediction {
  id: number;
  symbol: string;
  timeframe: string;
  signal_direction: string;
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  take_profit_3: number;
  atr: number;
  atr_percent: number;
  predicted_path: PredictionPoint[];
  upper_bound_path: PredictionPoint[];
  lower_bound_path: PredictionPoint[];
  horizon_candles: number;
  created_at: string;
  status: "ACTIVE" | "VERIFIED" | "EXPIRED";
  verified_at: string | null;
  actual_path: PredictionPoint[] | null;
  result: string | null;
  accuracy_score: number | null;
  max_favorable: number | null;
  max_adverse: number | null;
  final_price: number | null;
  notes: string | null;
  auto_generated: boolean;
  regime: string | null;
  progress_pnl_pct: number | null;
  progress_rr_current: number | null;
  progress_time_pct: number | null;
  progress_path_accuracy: number | null;
}

export interface PredictionStats {
  total_predictions: number;
  avg_accuracy_score: number;
  tp_hit_rate: number;
  sl_hit_rate: number;
  avg_max_favorable_excursion: number;
  avg_max_adverse_excursion: number;
}

export interface PredictionDashboardStats {
  total_predictions: number;
  active_predictions: number;
  avg_accuracy: number;
  win_rate: number;
  leaderboard: { symbol: string; avg_acc: number; wins: number }[];
  recent_results: { symbol: string; result: string; accuracy_score: number }[];
}

export interface PredictionProgress {
  prediction_id: number;
  symbol: string;
  pnl_pct: number;
  rr_current: number;
  time_pct: number;
  path_accuracy: number;
  current_price: number;
}

// ─── REST API 호출 ────────────────────────────────────

export async function fetchHealth(): Promise<{
  status: string;
  checks: { server_started_at?: string; [key: string]: unknown };
}> {
  return fetchWithError(`${API_BASE}/api/health`);
}

export async function fetchTicker(symbol: string): Promise<Ticker> {
  const encoded = encodeURIComponent(symbol.replace("/", ""));
  return fetchWithError<Ticker>(`${API_BASE}/api/ticker/${encoded}`);
}

export async function fetchMarkets(): Promise<Market[]> {
  const data = await fetchWithError<{ markets: Market[] }>(`${API_BASE}/api/markets`);
  return data.markets || [];
}

export async function analyzeSymbol(
  symbol: string,
  timeframe: string = "1h"
): Promise<Signal> {
  const encoded = encodeURIComponent(symbol.replace("/", ""));
  return fetchWithError<Signal>(
    `${API_BASE}/api/analyze/${encoded}?timeframe=${timeframe}`
  );
}

// 타임프레임별 기본 캔들 수 (차트 표시용 - 충분한 데이터)
const TF_DEFAULT_LIMIT: Record<string, number> = {
  "1m": 500,    // ~8시간
  "5m": 500,    // ~1.7일
  "15m": 1500,  // ~15일
  "30m": 1500,  // ~31일
  "1h": 2000,   // ~83일
  "4h": 1000,   // ~166일
  "1d": 365,    // ~1년
};

export async function fetchOHLCV(
  symbol: string,
  timeframe: string = "1h",
  limit?: number
): Promise<Candle[]> {
  if (!limit) limit = TF_DEFAULT_LIMIT[timeframe] || 500;
  const encoded = encodeURIComponent(symbol.replace("/", ""));
  const data = await fetchWithError<{ candles: Candle[] }>(
    `${API_BASE}/api/ohlcv/${encoded}?timeframe=${timeframe}&limit=${limit}`
  );
  return data.candles || [];
}

// ─── 지표 시계열 API ─────────────────────────────────────

export interface IndicatorSeriesPoint {
  time: number;
  value: number;
}

export interface IndicatorSeriesData {
  [seriesName: string]: IndicatorSeriesPoint[];
}

export interface IndicatorSeriesResponse {
  symbol: string;
  timeframe: string;
  indicators: Record<string, IndicatorSeriesData>;
}

export async function fetchIndicatorSeries(
  symbol: string,
  timeframe: string = "1h",
  indicators: string[] = ["ema", "bb"],
  limit?: number
): Promise<IndicatorSeriesResponse> {
  if (!limit) limit = TF_DEFAULT_LIMIT[timeframe] || 500;
  const encoded = encodeURIComponent(symbol.replace("/", ""));
  const indParam = indicators.join(",");
  return fetchWithError<IndicatorSeriesResponse>(
    `${API_BASE}/api/indicators/${encoded}?timeframe=${timeframe}&indicators=${indParam}&limit=${limit}`
  );
}

export async function scanMarket(
  timeframe: string = "1h",
  topN: number = 30
): Promise<Signal[]> {
  const data = await fetchWithError<{ signals: Signal[] }>(
    `${API_BASE}/api/scan?timeframe=${timeframe}&top_n=${topN}`
  );
  return data.signals || [];
}

export async function fetchSignalHistory(params: {
  symbol?: string;
  timeframe?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ signals: Signal[]; total: number }> {
  const query = new URLSearchParams();
  if (params.symbol) query.set("symbol", params.symbol);
  if (params.timeframe) query.set("timeframe", params.timeframe);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  return fetchWithError(`${API_BASE}/api/signals/history?${query}`);
}

// ─── 알림 API ─────────────────────────────────────────

export async function fetchAlerts(limit = 50, unreadOnly = false): Promise<{
  alerts: Alert[];
  total: number;
  unread: number;
}> {
  return fetchWithError(
    `${API_BASE}/api/alerts?limit=${limit}&unread_only=${unreadOnly}`
  );
}

export async function markAlertsRead(alertIds: number[] = []): Promise<void> {
  const res = await fetch(`${API_BASE}/api/alerts/read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alert_ids: alertIds }),
  });
  if (!res.ok) {
    throw new Error(`알림 읽음 처리 실패: HTTP ${res.status}`);
  }
}

export async function fetchAlertConfig(): Promise<AlertConfig> {
  return fetchWithError(`${API_BASE}/api/alerts/config`);
}

export async function updateAlertConfig(config: Partial<AlertConfig>): Promise<AlertConfig> {
  const res = await fetch(`${API_BASE}/api/alerts/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    throw new Error(`알림 설정 저장 실패: HTTP ${res.status}`);
  }
  return res.json();
}

// ─── 예측 API ────────────────────────────────────────

export async function createPrediction(
  symbol: string,
  timeframe: string = "1h",
  horizonCandles: number = 24
): Promise<Prediction> {
  const encoded = encodeURIComponent(symbol.replace("/", ""));
  const res = await fetch(
    `${API_BASE}/api/predictions/${encoded}?timeframe=${timeframe}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ horizon_candles: horizonCandles }),
    }
  );
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchActivePrediction(
  symbol: string,
  timeframe: string = "1h"
): Promise<Prediction | null> {
  const encoded = encodeURIComponent(symbol.replace("/", ""));
  const data = await fetchWithError<{ prediction: Prediction | null }>(
    `${API_BASE}/api/predictions/${encoded}/active?timeframe=${timeframe}`
  );
  return data.prediction;
}

export async function fetchPredictions(
  symbol: string,
  params: { status?: string; limit?: number } = {}
): Promise<{ predictions: Prediction[]; total: number }> {
  const encoded = encodeURIComponent(symbol.replace("/", ""));
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.limit) query.set("limit", String(params.limit));
  return fetchWithError(
    `${API_BASE}/api/predictions/${encoded}?${query}`
  );
}

export async function fetchPredictionStats(
  symbol?: string
): Promise<PredictionStats> {
  const query = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  return fetchWithError(`${API_BASE}/api/predictions/stats${query}`);
}

export async function fetchPredictionDashboard(): Promise<PredictionDashboardStats> {
  return fetchWithError(`${API_BASE}/api/predictions/dashboard`);
}

export async function fetchAllPredictions(params: {
  status?: string;
  direction?: string;
  timeframe?: string;
  result?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ predictions: Prediction[]; total: number }> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.direction) query.set("direction", params.direction);
  if (params.timeframe) query.set("timeframe", params.timeframe);
  if (params.result) query.set("result", params.result);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  return fetchWithError(`${API_BASE}/api/predictions/all?${query}`);
}

export async function fetchAllActivePredictions(): Promise<{
  predictions: Prediction[];
  total: number;
}> {
  return fetchWithError(`${API_BASE}/api/predictions/active`);
}

export async function verifyPrediction(predictionId: number): Promise<Prediction> {
  const res = await fetch(
    `${API_BASE}/api/predictions/${predictionId}/verify`,
    { method: "POST" }
  );
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function expirePrediction(predictionId: number): Promise<{ success: boolean }> {
  const res = await fetch(
    `${API_BASE}/api/predictions/${predictionId}/expire`,
    { method: "POST" }
  );
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function expireAllPredictions(): Promise<{ success: boolean; expired_count: number }> {
  const res = await fetch(
    `${API_BASE}/api/predictions/expire-all`,
    { method: "POST" }
  );
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── 모의 트레이딩 ──────────────────────────────────────

export interface PaperAccount {
  id: number;
  name: string;
  initial_balance: number;
  balance: number;
  total_pnl: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  created_at: string;
  updated_at: string;
}

export interface PaperTrade {
  id: number;
  account_id: number;
  symbol: string;
  direction: "LONG" | "SHORT";
  status: "OPEN" | "CLOSED";
  entry_price: number;
  current_price: number | null;
  close_price: number | null;
  quantity: number;
  position_usdt: number;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  take_profit_3: number | null;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  close_reason: string | null;
  opened_at: string;
  closed_at: string | null;
  updated_at: string;
}

export interface PaperPositionUpdate {
  trade_id: number;
  symbol: string;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface PaperTradingStats {
  account: PaperAccount;
  open_positions: number;
  total_unrealized_pnl: number;
  equity: number;
}

export async function fetchPaperAccount(): Promise<PaperAccount> {
  return fetchWithError(`${API_BASE}/api/paper/account`);
}

export async function resetPaperAccount(): Promise<PaperAccount> {
  const res = await fetch(`${API_BASE}/api/paper/reset`, { method: "POST" });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function openPaperTrade(params: {
  symbol: string;
  direction: "LONG" | "SHORT";
  position_usdt: number;
  stop_loss?: number | null;
  take_profit_1?: number | null;
  take_profit_2?: number | null;
  take_profit_3?: number | null;
}): Promise<PaperTrade> {
  const res = await fetch(`${API_BASE}/api/paper/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function closePaperTrade(tradeId: number): Promise<PaperTrade> {
  const res = await fetch(`${API_BASE}/api/paper/close/${tradeId}`, {
    method: "POST",
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchPaperPositions(): Promise<{
  positions: PaperTrade[];
  total: number;
}> {
  return fetchWithError(`${API_BASE}/api/paper/positions`);
}

export async function fetchPaperTradeHistory(params: {
  limit?: number;
  offset?: number;
} = {}): Promise<{ trades: PaperTrade[]; total: number }> {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  return fetchWithError(`${API_BASE}/api/paper/history?${query}`);
}

export async function fetchPaperTradingStats(): Promise<PaperTradingStats> {
  return fetchWithError(`${API_BASE}/api/paper/stats`);
}


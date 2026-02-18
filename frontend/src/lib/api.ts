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

// 타임프레임별 기본 캔들 수 (2년치 기준)
const TF_DEFAULT_LIMIT: Record<string, number> = {
  "15m": 2000,  // ~20일
  "30m": 2000,  // ~41일
  "1h": 2000,   // ~83일
  "4h": 4380,   // ~2년
  "1d": 730,    // ~2년
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
  await fetch(`${API_BASE}/api/alerts/read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alert_ids: alertIds }),
  });
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


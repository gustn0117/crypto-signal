"""
FastAPI 메인 서버 (v2)
REST API + WebSocket + 멀티TF 스캔 + 선물 데이터 + DB 알림 + 시장 맥락
"""
import asyncio
import json
import logging
import math
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class _SafeEncoder(json.JSONEncoder):
    """NaN/Infinity/numpy를 안전하게 직렬화"""
    def default(self, o):
        if hasattr(o, "item"):
            return o.item()
        if hasattr(o, "tolist"):
            return o.tolist()
        return super().default(o)

    def encode(self, o):
        return super().encode(self._clean(o))

    def _clean(self, obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return 0.0
            return obj
        if isinstance(obj, dict):
            return {k: self._clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._clean(v) for v in obj]
        if hasattr(obj, "item"):
            return self._clean(obj.item())
        if hasattr(obj, "tolist"):
            return self._clean(obj.tolist())
        return obj


def _safe_dumps(obj) -> str:
    """NaN-safe json.dumps"""
    return json.dumps(obj, cls=_SafeEncoder)

from logging_config import setup_logging
from config import (
    HOST, PORT, SCAN_INTERVAL_SECONDS, TIMEFRAMES, DEFAULT_TIMEFRAME,
    ALLOWED_ORIGINS, LOG_LEVEL, LOG_DIR, HIGHER_TF_MAP,
    ALERT_ENABLED, ALERT_MIN_CONFIDENCE, ALERT_SIGNAL_TYPES, ALERT_COOLDOWN_MINUTES,
    ALERT_COOLDOWN_MAP, DEFAULT_HORIZON_CANDLES,
    ANALYSIS_CANDLE_LIMIT, REALTIME_CANDLE_LIMIT, REALTIME_HIGHER_TF_LIMIT,
    SUPABASE_URL, SUPABASE_KEY, SUPABASE_SCHEMA, SCAN_SYMBOLS, SCAN_TIMEFRAMES, SCALP_SYMBOLS_LIMIT,
    BACKFILL_DAYS, BACKFILL_DAYS_1M, BACKFILL_TIMEFRAMES, BACKFILL_BATCH_SIZE, BACKFILL_CONCURRENCY,
    CRYPTOPANIC_API_KEY,
    AUTO_TRADE_ENABLED, AUTO_TRADE_MAX_POSITIONS, AUTO_TRADE_MAX_PCT,
)
from exchange import AsyncBinanceClient
from scanner import MarketScanner
from analysis.signal_engine import SignalEngine
from analysis.regime import detect_regime
from analysis.funding import get_futures_signals
from analysis.market_context import build_market_context
from db import Database, CandleRepo, SignalRepo, SignalTrackRepo, PredictionRepo, AlertRepo
from db.paper_trading_repo import PaperTradingRepo
from data_collector import DataCollector
from analysis.prediction import generate_prediction, recalculate_remaining_path
from analysis.self_learning import SelfLearningEngine
from analysis.backtest import BacktestEngine
from analysis.correlation import CorrelationAnalyzer
from analysis.indicator_series import compute_indicator_series
from analysis.portfolio_risk import PortfolioRiskManager
from trade_executor import TradeExecutor

# 로깅 초기화
setup_logging(log_dir=LOG_DIR, level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# 전역 객체
database = Database()
async_client = AsyncBinanceClient()
engine = SignalEngine()
scheduler = AsyncIOScheduler()
scanner: MarketScanner | None = None
candle_repo: CandleRepo | None = None
signal_repo: SignalRepo | None = None
track_repo: SignalTrackRepo | None = None
prediction_repo: PredictionRepo | None = None
alert_repo: AlertRepo | None = None
learning_engine: SelfLearningEngine | None = None
backtest_engine: BacktestEngine | None = None
correlation_analyzer: CorrelationAnalyzer | None = None
paper_trading_repo: PaperTradingRepo | None = None
risk_manager: PortfolioRiskManager | None = None
trade_executor: TradeExecutor | None = None

# WebSocket 연결 관리
connected_clients: List[WebSocket] = []
client_subscriptions: Dict[WebSocket, Optional[dict]] = {}

# 런타임 알림 설정
_alert_enabled = ALERT_ENABLED
_alert_min_confidence = ALERT_MIN_CONFIDENCE
_alert_signal_types = list(ALERT_SIGNAL_TYPES)
_alert_cooldown_minutes = ALERT_COOLDOWN_MINUTES

# 시장 맥락 캐시
_market_context: dict = {}

# 분석 결과 캐시 (symbol:timeframe -> {result, timestamp})
_analysis_cache: Dict[str, dict] = {}
ANALYSIS_CACHE_TTL = 15  # 15초 내 동일 요청은 캐시 반환

# 선물 데이터 캐시 (symbol -> {data, timestamp})
_futures_cache: Dict[str, dict] = {}
FUTURES_CACHE_TTL = 60  # 60초

# OI 히스토리 캐시 (심볼 -> 이전 OI 값)
_oi_history: Dict[str, float] = {}

# 서버 시작(배포) 시간
_server_started_at: str = datetime.now(timezone.utc).isoformat()

# 배치 티커 캐시
_ticker_cache: Dict[str, dict] = {}
_ticker_cache_at: Optional[datetime] = None
TICKER_CACHE_TTL = 15  # 15초

# OHLCV 프리워밍 캐시 (symbol:timeframe -> {candles: list, ts: datetime})
_ohlcv_cache: Dict[str, dict] = {}
OHLCV_CACHE_TTL = 10  # 10초
_ticker_cache_lock = asyncio.Lock()
_market_context_lock = asyncio.Lock()


def _normalize_symbol(symbol: str) -> str:
    """심볼 정규화: BTCUSDT -> BTC/USDT"""
    if "/" not in symbol:
        if symbol.endswith("USDT"):
            symbol = symbol[:-4] + "/USDT"
    return symbol


def _validate_timeframe(timeframe: str) -> str:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 타임프레임: {timeframe}. 사용 가능: {', '.join(TIMEFRAMES)}"
        )
    return timeframe


async def _broadcast_ws(message: str):
    """모든 WS 클라이언트에 메시지 브로드캐스트"""
    disconnected = []
    for ws in list(connected_clients):  # 복사본으로 순회 (race condition 방지)
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in connected_clients:
            connected_clients.remove(ws)
        client_subscriptions.pop(ws, None)


async def _refresh_ticker_cache():
    """배치 티커 캐시 갱신 (전체 심볼 한 번에, Lock 보호)"""
    global _ticker_cache, _ticker_cache_at
    async with _ticker_cache_lock:
        now = datetime.now(timezone.utc)
        if _ticker_cache_at and (now - _ticker_cache_at).total_seconds() < TICKER_CACHE_TTL:
            return
        try:
            await async_client.ensure_markets()
            tickers = await async_client.exchange.fetch_tickers()
            new_cache: Dict[str, dict] = {}
            for sym, t in tickers.items():
                # 키 통일: "BTC/USDT" 형식으로 저장 (콜론 제거)
                clean = sym.split(":")[0] if ":" in sym else sym
                new_cache[clean] = t
            _ticker_cache = new_cache
            _ticker_cache_at = now
        except Exception as e:
            logger.warning("배치 티커 갱신 실패: %s", e)


async def _push_transition_alert(transition: dict):
    """상태 전환 기반 알림 생성 + WS push + DB 저장"""
    if not _alert_enabled:
        return

    now = datetime.now(timezone.utc)
    to_state = transition.get("to_state", "")
    direction = transition.get("direction", "")
    symbol = transition.get("symbol", "")

    # 쿨다운 체크 (DB 기반, 타임프레임별)
    cooldown_key = f"track_{transition.get('track_id', '')}"
    tf = transition.get("timeframe", "1h")
    cooldown_min = ALERT_COOLDOWN_MAP.get(tf, _alert_cooldown_minutes)
    if alert_repo:
        is_cooling = await alert_repo.check_cooldown(cooldown_key, cooldown_min)
        if is_cooling:
            return

    # 알림 메시지 생성
    if to_state == "CONFIRMED":
        signal_label = f"{'롱' if direction == 'LONG' else '숏'} 시그널 확정"
    elif to_state == "WEAKENING":
        signal_label = f"{'롱' if direction == 'LONG' else '숏'} 시그널 약화"
    else:
        return

    alert = {
        "symbol": symbol,
        "signal": f"{'STRONG_LONG' if direction == 'LONG' else 'STRONG_SHORT'}",
        "confidence": transition.get("confidence", 0),
        "current_price": transition.get("current_price", 0),
        "summary": signal_label,
        "trade_params": None,
        "timestamp": now.isoformat(),
        "read": False,
        "transition": cooldown_key,
    }

    # DB 저장
    if alert_repo:
        alert_id = await alert_repo.save_alert(alert)
        if alert_id:
            alert["id"] = alert_id

    await _broadcast_ws(_safe_dumps({"type": "alert", "data": alert}))


async def push_subscription_updates():
    """구독 중인 클라이언트에게 실시간 분석 push"""
    disconnected = []
    for ws, sub in list(client_subscriptions.items()):
        if sub is None:
            continue
        try:
            symbol = sub["symbol"]
            timeframe = sub["timeframe"]
            df = await candle_repo.get_candles(symbol, timeframe, limit=REALTIME_CANDLE_LIMIT)

            higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
            higher_tf_df = None
            if higher_tf != timeframe:
                try:
                    higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=REALTIME_HIGHER_TF_LIMIT)
                except Exception as e:
                    logger.warning("상위TF(%s) 조회 실패 [%s]: %s", higher_tf, symbol, e)

            # 선물 데이터 (캐시 활용)
            futures_data = await _get_futures_cached(symbol)

            signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df, futures_data=futures_data)
            signal_data = signal.to_dict()

            # 트랙 데이터 병합
            if track_repo:
                try:
                    active_track = await track_repo.get_active_track(symbol, timeframe)
                    if active_track:
                        signal_data["track"] = {
                            "state": active_track["state"],
                            "consecutive_scans": active_track["consecutive_scans"],
                            "first_detected_at": active_track["first_detected_at"],
                            "confirmed_at": active_track["confirmed_at"],
                            "peak_confidence": active_track["peak_confidence"],
                        }
                except Exception as e:
                    logger.debug("구독 트랙 조회 실패 [%s]: %s", symbol, e)

            await ws.send_text(_safe_dumps({
                "type": "subscription_update",
                "data": signal_data
            }))
        except Exception as e:
            logger.debug("구독 업데이트 전송 실패: %s", e)
            disconnected.append(ws)
    for ws in disconnected:
        client_subscriptions.pop(ws, None)
        if ws in connected_clients:
            connected_clients.remove(ws)


async def _auto_generate_prediction(symbol: str, timeframe: str):
    """시그널 CONFIRMED 시 자동 예측 생성."""
    df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

    if len(df) < 20:
        logger.warning("자동 예측 스킵 (데이터 부족): %s", symbol)
        return

    higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
    higher_tf_df = None
    if higher_tf != timeframe:
        try:
            higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
        except Exception as e:
            logger.debug("자동예측 상위TF(%s) 조회 실패 [%s]: %s", higher_tf, symbol, e)

    signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df)

    if signal.trade_params is None and signal.signal != "NEUTRAL":
        logger.warning("자동 예측 스킵 (트레이드 파라미터 없음): %s", symbol)
        return

    regime_result = detect_regime(df)

    sr_levels = []
    if signal.price_levels:
        for key in ("support_1", "support_2", "resistance_1", "resistance_2"):
            val = signal.price_levels.get(key)
            if val:
                sr_levels.append(val)

    cal = None
    stats = await prediction_repo.get_accuracy_stats(symbol=symbol)
    if stats["total_predictions"] >= 5:
        cal = {
            "avg_accuracy": stats["avg_accuracy_score"],
            "count": stats["total_predictions"],
        }

    # BTC 상관관계 (알트코인일 경우)
    btc_signal = _market_context.get("btc_signal")
    is_alt = symbol != "BTC/USDT"

    # 과거 수익률 추출 (몬테카를로 리샘플링용)
    hist_returns = None
    if len(df) >= 100:
        hist_returns = df["close"].pct_change().dropna().values

    horizon = DEFAULT_HORIZON_CANDLES.get(timeframe, 24)

    pl = signal.price_levels or {}
    prediction_data = generate_prediction(
        signal_direction=signal.signal,
        confidence=signal.confidence,
        entry_price=signal.current_price,
        trade_params=signal.trade_params,
        price_levels=pl,
        timeframe=timeframe,
        horizon_candles=horizon,
        indicator_snapshot=signal.indicator_snapshot,
        regime=regime_result.regime,
        calibration=cal,
        sr_levels=sr_levels,
        btc_signal_direction=btc_signal,
        is_altcoin=is_alt,
        historical_returns=hist_returns,
    )

    tp = signal.trade_params or {}
    pred_id = await prediction_repo.create_prediction(
        symbol=symbol,
        timeframe=timeframe,
        signal_direction=signal.signal,
        confidence=signal.confidence,
        entry_price=signal.current_price,
        stop_loss=tp.get("stop_loss") or 0,
        take_profit_1=tp.get("take_profit_1") or 0,
        take_profit_2=tp.get("take_profit_2") or 0,
        take_profit_3=tp.get("take_profit_3") or 0,
        atr=pl.get("atr", 0),
        atr_percent=pl.get("atr_percent", 0),
        predicted_path=prediction_data["predicted_path"],
        upper_bound_path=prediction_data["upper_bound_path"],
        lower_bound_path=prediction_data["lower_bound_path"],
        horizon_candles=horizon,
        auto_generated=True,
        regime=regime_result.regime,
        calibration_factor=cal["avg_accuracy"] if cal else 1.0,
    )

    logger.info("자동 예측 생성: %s #%d (레짐=%s)", symbol, pred_id, regime_result.regime)

    pred = await prediction_repo.get_prediction_by_id(pred_id)
    if pred and connected_clients:
        await _broadcast_ws(_safe_dumps({
            "type": "prediction_created",
            "data": pred,
        }))


async def _execute_auto_trade(symbol: str, timeframe: str):
    """CONFIRMED 시그널에 대한 자동매매 실행."""
    if not trade_executor or not paper_trading_repo:
        return
    # 최신 시그널에서 트레이드 파라미터 추출
    sig = None
    for s in (scanner.latest_signals.get(timeframe) or []):
        if s.get("symbol") == symbol:
            sig = s
            break
    if not sig or not sig.get("trade_params"):
        return

    account = await paper_trading_repo.get_or_create_account()
    open_trades = await paper_trading_repo.get_all_open_positions()
    equity = account.get("balance", 10000) + sum(
        t.get("unrealized_pnl", 0) for t in open_trades
    )

    result = await trade_executor.execute_signal(
        symbol=symbol,
        signal=sig["signal"],
        confidence=sig["confidence"],
        trade_params=sig["trade_params"],
        equity=equity,
        open_positions=[
            {"symbol": t["symbol"], "status": t["status"], "position_usdt": t.get("position_usdt", 0)}
            for t in open_trades
        ],
    )
    if result and result.success:
        logger.info("[자동매매] %s %s 체결 완료 (order_id=%s)", result.side, symbol, result.order_id)
        if connected_clients:
            await _broadcast_ws(_safe_dumps({
                "type": "auto_trade_executed",
                "data": result.to_dict(),
            }))


async def scheduled_scan_tf(timeframe: str):
    """특정 타임프레임 스캔"""
    global _market_context

    await scanner.scan_market(timeframe=timeframe)

    # 시장 맥락 갱신 (1h 스캔 시에만)
    if timeframe == "1h":
        try:
            signals_1h = scanner.latest_signals.get("1h", [])
            btc_ticker = None
            all_tickers = []
            await _refresh_ticker_cache()
            btc_ticker = _ticker_cache.get("BTC/USDT") or _ticker_cache.get("BTC/USDT:USDT")
            all_tickers = [{"change_24h": t.get("percentage", 0) or 0} for t in _ticker_cache.values()]

            ctx = await build_market_context(
                latest_signals=signals_1h,
                btc_ticker={"change_24h": btc_ticker.get("percentage", 0)} if btc_ticker else None,
                all_tickers=all_tickers,
                sentiment_api_key=CRYPTOPANIC_API_KEY,
            )
            async with _market_context_lock:
                _market_context = ctx
            engine.set_market_context(ctx)
        except Exception as e:
            logger.warning("시장 맥락 갱신 실패: %s", e)

    # 트랜지션 알림 + 자동 예측 + 자동매매
    for tr in (scanner.latest_transitions or []):
        try:
            if tr["to_state"] == "CONFIRMED":
                await _push_transition_alert(tr)
                if tr.get("from_state") == "CONFIRMING":
                    try:
                        await _auto_generate_prediction(tr["symbol"], timeframe)
                    except Exception as e:
                        logger.error("자동 예측 생성 실패 [%s]: %s", tr["symbol"], e)
                    # 자동매매 실행
                    if trade_executor and trade_executor.enabled:
                        try:
                            await _execute_auto_trade(tr["symbol"], timeframe)
                        except Exception as e:
                            logger.error("자동매매 실패 [%s]: %s", tr["symbol"], e)
            elif tr["to_state"] == "WEAKENING" and tr.get("from_state") == "CONFIRMED":
                await _push_transition_alert(tr)
        except Exception as e:
            logger.error("전환 알림 실패: %s", e)

    # signal_transition WS 브로드캐스트
    if connected_clients:
        for tr in (scanner.latest_transitions or []):
            if tr.get("to_state") in ("CONFIRMED", "WEAKENING", "EXPIRED"):
                try:
                    await _broadcast_ws(_safe_dumps({
                        "type": "signal_transition",
                        "data": tr
                    }))
                except Exception as e:
                    logger.debug("signal_transition 브로드캐스트 실패: %s", e)

    # scan_update 브로드캐스트
    if connected_clients:
        await _broadcast_ws(_safe_dumps({
            "type": "scan_update",
            "data": scanner.get_latest_signals(timeframe)
        }))


async def update_prediction_progress():
    """실시간 예측 진행 추적 (배치 티커 사용)."""
    if not prediction_repo:
        return
    try:
        active = await prediction_repo.get_all_active_predictions()
        if not active:
            return

        # 배치 티커 갱신 (1회 API 호출로 모든 심볼)
        await _refresh_ticker_cache()

        tf_seconds = {
            "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400,
        }
        now = datetime.now(timezone.utc)
        progress_updates = []

        for pred in active:
            try:
                symbol = pred["symbol"]
                timeframe = pred["timeframe"]
                entry_price = pred["entry_price"]
                is_long = pred["signal_direction"] in ("STRONG_LONG", "LONG")
                sl = pred["stop_loss"]
                tp3 = pred["take_profit_3"]
                atr = pred["atr"]

                # 배치 캐시에서 현재가 조회
                ticker = _ticker_cache.get(symbol)
                if not ticker:
                    continue
                current_price = ticker.get("last")
                if current_price is None:
                    continue

                # entry_price 유효성 검사
                if not entry_price or entry_price <= 0:
                    continue

                # PnL %
                if is_long:
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100

                # R:R
                risk = abs(entry_price - sl) if sl and sl > 0 else atr
                if risk <= 0:
                    risk = max(atr, entry_price * 0.01)
                reward = abs(current_price - entry_price)
                rr_current = reward / risk

                # 시간 진행률
                created = datetime.fromisoformat(pred["created_at"])
                candle_sec = tf_seconds.get(timeframe, 3600)
                total_sec = pred["horizon_candles"] * candle_sec
                elapsed = (now - created).total_seconds()
                time_pct = min(elapsed / total_sec, 1.0) if total_sec > 0 else 1.0

                # 경로 정확도
                path_accuracy = 0.5
                predicted_path = pred.get("predicted_path", [])
                if predicted_path and atr > 0:
                    now_ts = int(now.timestamp())
                    closest = min(predicted_path, key=lambda p: abs(p["time"] - now_ts))
                    error = abs(current_price - closest["price"])
                    path_accuracy = max(0.0, 1.0 - error / (2.0 * atr))

                # C3: 실시간 경로 재계산 (현재가 기반)
                predicted_path = pred.get("predicted_path", [])
                upper_path = pred.get("upper_bound_path", [])
                lower_path = pred.get("lower_bound_path", [])
                if predicted_path and atr > 0:
                    updated_paths = recalculate_remaining_path(
                        predicted_path=predicted_path,
                        upper_bound_path=upper_path,
                        lower_bound_path=lower_path,
                        current_price=current_price,
                        current_time=int(now.timestamp()),
                        atr=atr,
                    )
                    # 경로가 실제로 변경된 경우에만 DB 업데이트
                    if updated_paths["predicted_path"] is not predicted_path:
                        await prediction_repo.update_paths(
                            pred["id"],
                            updated_paths["predicted_path"],
                            updated_paths["upper_bound_path"],
                            updated_paths["lower_bound_path"],
                        )

                await prediction_repo.update_progress(
                    pred["id"], round(pnl_pct, 4), round(rr_current, 4),
                    round(time_pct, 4), round(path_accuracy, 4),
                )

                progress_updates.append({
                    "prediction_id": pred["id"],
                    "symbol": symbol,
                    "pnl_pct": round(pnl_pct, 4),
                    "rr_current": round(rr_current, 4),
                    "time_pct": round(time_pct, 4),
                    "path_accuracy": round(path_accuracy, 4),
                    "current_price": current_price,
                })

                # 조기 종료 체크 (None/0 값 안전 처리)
                if is_long:
                    hit_sl = bool(sl and sl > 0 and current_price <= sl)
                    hit_tp3 = bool(tp3 and tp3 > 0 and current_price >= tp3)
                else:
                    hit_sl = bool(sl and sl > 0 and current_price >= sl)
                    hit_tp3 = bool(tp3 and tp3 > 0 and current_price <= tp3)

                if hit_sl or hit_tp3:
                    try:
                        result = await _verify_single_prediction(pred)
                        logger.info("조기 검증 완료: %s #%d (%s)", symbol, pred["id"], "SL" if hit_sl else "TP3")
                        if connected_clients:
                            await _broadcast_ws(_safe_dumps({
                                "type": "prediction_verified",
                                "data": result,
                            }))
                    except Exception as e:
                        logger.error("조기 검증 실패 #%d: %s", pred["id"], e)

            except Exception as e:
                logger.debug("진행 추적 실패 [%s #%d]: %s", pred.get("symbol"), pred.get("id"), e)

        if progress_updates and connected_clients:
            await _broadcast_ws(_safe_dumps({
                "type": "prediction_progress",
                "data": progress_updates,
            }))

    except Exception as e:
        logger.error("예측 진행 추적 실패: %s", e)


async def verify_predictions():
    """주기적 예측 검증 (5분마다)"""
    if not prediction_repo:
        return
    try:
        pending = await prediction_repo.get_pending_verifications()
        now = datetime.now(timezone.utc)
        tf_seconds = {
            "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400,
        }
        for pred in pending:
            created = datetime.fromisoformat(pred["created_at"])
            candle_sec = tf_seconds.get(pred["timeframe"], 3600)
            horizon_total = pred["horizon_candles"] * candle_sec
            if (now - created).total_seconds() >= horizon_total:
                try:
                    await _verify_single_prediction(pred)
                    logger.info("예측 검증 완료: %s #%d", pred["symbol"], pred["id"])
                except Exception as e:
                    logger.error("예측 검증 실패 #%d: %s", pred["id"], e)
    except Exception as e:
        logger.error("예측 검증 작업 실패: %s", e)


async def _verify_single_prediction(prediction: dict) -> dict:
    """단일 예측 검증"""
    symbol = prediction["symbol"]
    timeframe = prediction["timeframe"]
    entry_price = prediction["entry_price"]
    is_long = prediction["signal_direction"] in ("STRONG_LONG", "LONG")
    sl = prediction["stop_loss"]
    tp1 = prediction["take_profit_1"]
    tp2 = prediction["take_profit_2"]
    tp3 = prediction["take_profit_3"]
    atr = prediction["atr"]

    df = await candle_repo.get_candles(symbol, timeframe, limit=500)
    if df.empty:
        return prediction

    if not entry_price or entry_price <= 0:
        logger.warning("예측 검증 스킵 (entry_price 무효): %s #%d", symbol, prediction["id"])
        return prediction

    pred_time = datetime.fromisoformat(prediction["created_at"])
    actual_candles = df[df.index >= pred_time]

    if len(actual_candles) < 1:
        return prediction

    actual_path = []
    for ts, row in actual_candles.iterrows():
        actual_path.append({
            "time": int(ts.timestamp()),
            "price": float(row["close"]),
        })

    if is_long:
        max_favorable = max(
            (((row["high"] - entry_price) / entry_price) * 100
             for _, row in actual_candles.iterrows()),
            default=0.0,
        )
        max_adverse = max(
            (((entry_price - row["low"]) / entry_price) * 100
             for _, row in actual_candles.iterrows()),
            default=0.0,
        )
    else:
        max_favorable = max(
            (((entry_price - row["low"]) / entry_price) * 100
             for _, row in actual_candles.iterrows()),
            default=0.0,
        )
        max_adverse = max(
            (((row["high"] - entry_price) / entry_price) * 100
             for _, row in actual_candles.iterrows()),
            default=0.0,
        )

    final_price = float(actual_candles["close"].iloc[-1])

    # TP를 먼저 체크 (TP3 → TP2 → TP1 → SL 순서)
    # 같은 캔들에서 TP와 SL 동시 도달 시 TP 우선
    # None/0 값은 안전하게 건너뛰기
    high_max = actual_candles["high"].max()
    low_min = actual_candles["low"].min()

    if is_long:
        if tp3 and tp3 > 0 and high_max >= tp3:
            result = "HIT_TP3"
        elif tp2 and tp2 > 0 and high_max >= tp2:
            result = "HIT_TP2"
        elif tp1 and tp1 > 0 and high_max >= tp1:
            result = "HIT_TP1"
        elif sl and sl > 0 and low_min <= sl:
            result = "HIT_SL"
        elif final_price > entry_price:
            result = "PARTIAL"
        else:
            result = "WRONG"
    else:
        if tp3 and tp3 > 0 and low_min <= tp3:
            result = "HIT_TP3"
        elif tp2 and tp2 > 0 and low_min <= tp2:
            result = "HIT_TP2"
        elif tp1 and tp1 > 0 and low_min <= tp1:
            result = "HIT_TP1"
        elif sl and sl > 0 and high_max >= sl:
            result = "HIT_SL"
        elif final_price < entry_price:
            result = "PARTIAL"
        else:
            result = "WRONG"

    predicted_path = prediction.get("predicted_path") or []
    actual_map = {p["time"]: p["price"] for p in actual_path}
    scores = []
    for point in predicted_path:
        t = point.get("time")
        pred_price = point.get("price")
        if t is None or pred_price is None:
            continue
        actual_price = actual_map.get(t)
        if actual_price is None:
            if not actual_map:
                continue
            closest_t = min(actual_map.keys(), key=lambda at: abs(at - t))
            actual_price = actual_map[closest_t]
        error = abs(pred_price - actual_price)
        score = max(0.0, 1.0 - error / (2.0 * atr)) if atr > 0 else 0.0
        scores.append(score)
    accuracy_score = round(sum(scores) / len(scores), 4) if scores else 0.0

    notes = f"MFE: {max_favorable:.2f}%, MAE: {max_adverse:.2f}%"

    await prediction_repo.update_verification(
        prediction_id=prediction["id"],
        status="VERIFIED",
        actual_path=actual_path,
        result=result,
        accuracy_score=accuracy_score,
        max_favorable=round(max_favorable, 4),
        max_adverse=round(max_adverse, 4),
        final_price=final_price,
        notes=notes,
    )

    return await prediction_repo.get_prediction_by_id(prediction["id"])


async def cleanup_expired_tracks():
    """만료된 트랙 정리 (6시간마다)"""
    if track_repo:
        try:
            count = await track_repo.cleanup_expired(older_than_hours=48)
            if count > 0:
                logger.info("만료 트랙 정리: %d개 삭제", count)
        except Exception as e:
            logger.error("트랙 정리 실패: %s", e)

    # 오래된 알림 정리
    if alert_repo:
        try:
            await alert_repo.cleanup_old(keep_count=500)
        except Exception as e:
            logger.debug("알림 정리 실패: %s", e)


async def run_self_learning():
    """자기학습 실행 (6시간마다)"""
    if not learning_engine:
        return
    try:
        await learning_engine.run_learning_cycle()
        weights = await learning_engine.get_adaptive_weights()
        engine.set_adaptive_weights(weights)
    except Exception as e:
        logger.error("자기학습 실패: %s", e)


async def run_backtest_update():
    """백테스트 통계 갱신 (6시간마다)"""
    if not backtest_engine:
        return
    try:
        stats = await backtest_engine.run_backtest()
        if stats:
            logger.info("백테스트 갱신 완료: %d개 예측 분석", stats.get("total_predictions", 0))
    except Exception as e:
        logger.error("백테스트 갱신 실패: %s", e)


async def run_correlation_update():
    """상관관계 분석 갱신 (5분마다)"""
    if not correlation_analyzer or not scanner:
        return
    try:
        symbols = list({s.get("symbol", "") for sigs in scanner.latest_signals.values() for s in sigs})
        if len(symbols) < 5:
            symbols = list(SCAN_SYMBOLS)
        await correlation_analyzer.update_correlation(symbols)
    except Exception as e:
        logger.error("상관관계 갱신 실패: %s", e)


async def run_backfill():
    """히스토리 백필 (1m은 7일, 나머지는 5년)"""
    try:
        collector = DataCollector(async_client, candle_repo)

        # 1m 제외 타임프레임: 5년치 백필
        tf_without_1m = [tf for tf in BACKFILL_TIMEFRAMES if tf != "1m"]
        results = await collector.backfill_all(
            symbols=SCAN_SYMBOLS,
            timeframes=tf_without_1m,
            days=BACKFILL_DAYS,
            batch_size=BACKFILL_BATCH_SIZE,
            concurrency=BACKFILL_CONCURRENCY,
        )
        total = sum(c for sym in results.values() for c in sym.values())

        # 1m: 7일치만, 코어 심볼 + 스캘핑 대상만
        if "1m" in BACKFILL_TIMEFRAMES:
            results_1m = await collector.backfill_all(
                symbols=SCAN_SYMBOLS[:SCALP_SYMBOLS_LIMIT],
                timeframes=["1m"],
                days=BACKFILL_DAYS_1M,
                batch_size=BACKFILL_BATCH_SIZE,
                concurrency=BACKFILL_CONCURRENCY,
            )
            total += sum(c for sym in results_1m.values() for c in sym.values())

        if total > 0:
            logger.info("백필 완료: 총 %d개 캔들 저장", total)
        else:
            logger.info("백필: 새로 저장할 데이터 없음 (이미 최신)")
    except Exception as e:
        logger.error("백필 실패: %s", e)


async def run_ohlcv_prewarmer():
    """10개 코인의 OHLCV를 백그라운드에서 프리워밍 (즉시 응답용)"""
    global _ohlcv_cache
    try:
        for symbol in SCAN_SYMBOLS:
            for tf in SCAN_TIMEFRAMES:
                cache_key = f"{symbol}:{tf}"
                try:
                    df = await candle_repo.get_candles(symbol, tf, limit=500)
                    candles = []
                    for ts, row in df.iterrows():
                        candles.append({
                            "time": int(ts.timestamp()),
                            "open": row["open"],
                            "high": row["high"],
                            "low": row["low"],
                            "close": row["close"],
                            "volume": row["volume"],
                        })
                    _ohlcv_cache[cache_key] = {
                        "candles": candles,
                        "ts": datetime.now(timezone.utc),
                    }
                except Exception as e:
                    logger.debug("OHLCV 프리워밍 실패 [%s/%s]: %s", symbol, tf, e)
        await _refresh_ticker_cache()
    except Exception as e:
        logger.warning("OHLCV 프리워밍 전체 실패: %s", e)


async def update_paper_positions():
    """모의 트레이딩 포지션 P&L 업데이트 + 자동 청산 (10초마다)."""
    if not paper_trading_repo:
        return
    try:
        open_trades = await paper_trading_repo.get_all_open_positions()
        if not open_trades:
            return

        await _refresh_ticker_cache()
        position_updates = []

        for trade in open_trades:
            try:
                symbol = trade["symbol"]
                ticker = _ticker_cache.get(symbol)
                if not ticker:
                    continue
                current_price = ticker.get("last")
                if current_price is None:
                    continue

                entry_price = trade["entry_price"]
                quantity = trade["quantity"]
                is_long = trade["direction"] == "LONG"

                if is_long:
                    unrealized_pnl = (current_price - entry_price) * quantity
                    unrealized_pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    unrealized_pnl = (entry_price - current_price) * quantity
                    unrealized_pnl_pct = ((entry_price - current_price) / entry_price) * 100

                await paper_trading_repo.update_unrealized_pnl(
                    trade["id"], current_price,
                    round(unrealized_pnl, 4),
                    round(unrealized_pnl_pct, 4),
                )

                position_updates.append({
                    "trade_id": trade["id"],
                    "symbol": symbol,
                    "current_price": current_price,
                    "unrealized_pnl": round(unrealized_pnl, 4),
                    "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
                })

                # SL/TP 자동 청산
                sl = trade.get("stop_loss")
                tp1 = trade.get("take_profit_1")
                tp2 = trade.get("take_profit_2")
                tp3 = trade.get("take_profit_3")
                close_reason = None

                if is_long:
                    if sl and current_price <= sl:
                        close_reason = "HIT_SL"
                    elif tp3 and current_price >= tp3:
                        close_reason = "HIT_TP3"
                    elif tp2 and current_price >= tp2:
                        close_reason = "HIT_TP2"
                    elif tp1 and current_price >= tp1:
                        close_reason = "HIT_TP1"
                else:
                    if sl and current_price >= sl:
                        close_reason = "HIT_SL"
                    elif tp3 and current_price <= tp3:
                        close_reason = "HIT_TP3"
                    elif tp2 and current_price <= tp2:
                        close_reason = "HIT_TP2"
                    elif tp1 and current_price <= tp1:
                        close_reason = "HIT_TP1"

                if close_reason:
                    closed = await paper_trading_repo.close_trade(
                        trade["id"], current_price, close_reason
                    )
                    logger.info("모의 트레이딩 자동 청산: %s #%d (%s)",
                                symbol, trade["id"], close_reason)
                    if connected_clients:
                        await _broadcast_ws(_safe_dumps({
                            "type": "paper_trade_closed",
                            "data": closed,
                        }))

            except Exception as e:
                logger.debug("모의 포지션 업데이트 실패 [%s #%d]: %s",
                             trade.get("symbol"), trade.get("id"), e)

        if position_updates and connected_clients:
            await _broadcast_ws(_safe_dumps({
                "type": "paper_position_update",
                "data": position_updates,
            }))

    except Exception as e:
        logger.error("모의 트레이딩 포지션 업데이트 실패: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scanner, candle_repo, signal_repo, track_repo, prediction_repo, alert_repo, learning_engine, backtest_engine, correlation_analyzer, paper_trading_repo, risk_manager, trade_executor, _market_context, _server_started_at

    # 서버 시작 시간 갱신 (리로더가 아닌 실제 워커 시작 시점)
    _server_started_at = datetime.now(timezone.utc).isoformat()

    # DB 초기화 + 스키마 자동 등록 (PostgREST 재시작 시 스키마 누락 방지)
    await database.connect()
    try:
        import httpx as _hx
        _pg_meta = SUPABASE_URL.rstrip("/") + "/pg/query"
        _auth_h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
        async with _hx.AsyncClient(timeout=10) as _hc:
            r = await _hc.post(_pg_meta, headers=_auth_h, json={
                "query": "SELECT string_agg(unnest, ', ') AS schemas FROM unnest(string_to_array((SELECT setting FROM pg_settings WHERE name='pgrst.db_schemas'), ', '));"
            })
            current = (r.json()[0]["schemas"] or "") if r.status_code == 200 and r.json() else ""
            if SUPABASE_SCHEMA not in current:
                new_schemas = f"{current}, {SUPABASE_SCHEMA}" if current else SUPABASE_SCHEMA
                await _hc.post(_pg_meta, headers=_auth_h, json={
                    "query": f"ALTER ROLE authenticator SET pgrst.db_schemas = '{new_schemas}';"
                })
                await _hc.post(_pg_meta, headers=_auth_h, json={"query": "NOTIFY pgrst, 'reload config';"})
                logger.info("PostgREST에 스키마 '%s' 자동 등록 완료", SUPABASE_SCHEMA)
    except Exception as e:
        logger.debug("PostgREST 스키마 자동 등록 시도 실패 (무시 가능): %s", e)
    candle_repo = CandleRepo(database.client, SUPABASE_SCHEMA)
    signal_repo = SignalRepo(database.client, SUPABASE_SCHEMA)
    track_repo = SignalTrackRepo(database.client, SUPABASE_SCHEMA)
    prediction_repo = PredictionRepo(database.client, SUPABASE_SCHEMA)
    alert_repo = AlertRepo(database.client, SUPABASE_SCHEMA)
    paper_trading_repo = PaperTradingRepo(database.client, SUPABASE_SCHEMA)
    learning_engine = SelfLearningEngine(database.client, SUPABASE_SCHEMA)
    backtest_engine = BacktestEngine(database.client, SUPABASE_SCHEMA)
    logger.info("Supabase 데이터베이스 연결 완료")

    # 스캐너 생성 (티커 캐시 연동으로 거래량 급증 감지)
    correlation_analyzer = CorrelationAnalyzer(candle_repo)
    risk_manager = PortfolioRiskManager(correlation_analyzer)
    trade_executor = TradeExecutor(
        exchange_client=async_client,
        paper_repo=paper_trading_repo,
        risk_manager=risk_manager,
        enabled=AUTO_TRADE_ENABLED,
        max_positions=AUTO_TRADE_MAX_POSITIONS,
        max_position_pct=AUTO_TRADE_MAX_PCT,
    )
    scanner = MarketScanner(async_client, candle_repo, signal_repo, track_repo,
                            ticker_cache_getter=lambda: _ticker_cache,
                            correlation_analyzer=correlation_analyzer)

    # 학습 가중치 로드
    try:
        saved_weights = await learning_engine.get_adaptive_weights()
        engine.set_adaptive_weights(saved_weights)
        logger.info("저장된 적응형 가중치 로드 완료")
    except Exception as e:
        logger.warning("적응형 가중치 로드 실패 (기본값 사용): %s", e)

    # 시장 맥락 초기화 (첫 1h 스캔까지 빈 상태 방지)
    try:
        await _refresh_ticker_cache()
        btc_ticker = _ticker_cache.get("BTC/USDT") or _ticker_cache.get("BTC/USDT:USDT")
        all_tickers = [{"change_24h": t.get("percentage", 0) or 0} for t in _ticker_cache.values()]
        ctx = await build_market_context(
            latest_signals=[],
            btc_ticker={"change_24h": btc_ticker.get("percentage", 0)} if btc_ticker else None,
            all_tickers=all_tickers,
            sentiment_api_key=CRYPTOPANIC_API_KEY,
        )
        _market_context = ctx
        engine.set_market_context(ctx)
        logger.info("초기 시장 맥락 로드 완료")
    except Exception as e:
        logger.warning("초기 시장 맥락 로드 실패: %s", e)

    # 상관관계 초기화
    try:
        await correlation_analyzer.update_correlation(list(SCAN_SYMBOLS))
        logger.info("초기 상관관계 데이터 로드 완료")
    except Exception as e:
        logger.warning("초기 상관관계 로드 실패: %s", e)

    # 멀티 타임프레임 스케줄링
    # 15m: 30초마다, 1h: 60초마다, 4h: 5분마다
    tf_intervals = {"1m": 15, "5m": 20, "15m": 30, "1h": 60, "4h": 300}
    for tf in SCAN_TIMEFRAMES:
        interval = tf_intervals.get(tf, SCAN_INTERVAL_SECONDS)
        scheduler.add_job(
            scheduled_scan_tf, "interval", seconds=interval,
            args=[tf], id=f"scan_{tf}", max_instances=1,
        )
        logger.info("스캔 스케줄 등록: %s (주기: %d초)", tf, interval)

    scheduler.add_job(push_subscription_updates, "interval", seconds=15)
    scheduler.add_job(cleanup_expired_tracks, "interval", hours=6)
    scheduler.add_job(verify_predictions, "interval", minutes=5)
    scheduler.add_job(update_prediction_progress, "interval", seconds=60)
    scheduler.add_job(run_self_learning, "interval", hours=6)
    scheduler.add_job(run_backtest_update, "interval", hours=6)
    scheduler.add_job(run_correlation_update, "interval", minutes=5)
    scheduler.add_job(run_backfill, "interval", hours=24)
    scheduler.add_job(run_ohlcv_prewarmer, "interval", seconds=10, id="ohlcv_prewarmer", max_instances=1)
    scheduler.add_job(update_paper_positions, "interval", seconds=10, id="paper_positions", max_instances=1)
    scheduler.start()
    logger.info("멀티TF 스캐너 시작: %s, OHLCV 프리워밍 활성화, 자기학습/백테스트/상관관계 활성화", SCAN_TIMEFRAMES)

    # 백필: 백그라운드로 즉시 시작
    asyncio.create_task(run_backfill())

    yield

    scheduler.shutdown()
    await async_client.close()
    await database.close()
    logger.info("서버 종료 완료")


class _SafeJSONResponse(JSONResponse):
    """NaN/numpy 안전 JSON 응답"""
    def render(self, content) -> bytes:
        return _safe_dumps(content).encode("utf-8")


app = FastAPI(
    title="Crypto Signal System",
    description="암호화폐 롱/숏 시그널 분석 시스템 v2",
    version="4.0.0",
    lifespan=lifespan,
    default_response_class=_SafeJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── REST API ───────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    checks = {
        "database": False,
        "exchange": False,
        "scanner_active": scanner is not None,
        "last_scan": scanner.last_scan_time if scanner else None,
        "connected_clients": len(connected_clients),
        "active_subscriptions": sum(1 for v in client_subscriptions.values() if v),
        "scan_timeframes": SCAN_TIMEFRAMES,
        "market_context": bool(_market_context),
    }
    try:
        await database.client.schema(SUPABASE_SCHEMA).table("ohlcv").select("symbol").limit(1).execute()
        checks["database"] = True
    except Exception as e:
        logger.debug("헬스체크 DB 연결 실패: %s", e)
    try:
        await async_client.ensure_markets()
        checks["exchange"] = True
    except Exception as e:
        logger.debug("헬스체크 거래소 연결 실패: %s", e)

    # 읽지 않은 알림 수 (DB)
    if alert_repo:
        checks["pending_alerts"] = await alert_repo.get_unread_count()

    checks["server_started_at"] = _server_started_at

    status = "healthy" if checks["database"] and checks["exchange"] else "degraded"
    return {"status": status, "checks": checks}


@app.get("/api/deploy-status")
async def deploy_status():
    """배포 상태 진단"""
    import httpx
    result = {"server_started_at": _server_started_at}
    try:
        async with httpx.AsyncClient(timeout=5) as hc:
            r = await hc.get("http://172.17.0.1:9000/status")
            if r.status_code == 200:
                result["webhook"] = r.json()
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=5) as hc:
            r = await hc.get("http://coin-frontend:3000/")
            result["frontend"] = {"status": r.status_code, "ok": r.status_code == 200}
    except Exception as e:
        result["frontend"] = {"ok": False, "error": str(e)}
    return result


@app.get("/api/markets")
async def get_markets():
    try:
        markets = await async_client.get_usdt_markets()
        return {"markets": markets, "total": len(markets)}
    except Exception as e:
        logger.error("마켓 목록 조회 실패: %s", e)
        raise HTTPException(status_code=502, detail="거래소 연결 실패")


async def _get_futures_cached(symbol: str) -> list:
    """선물 데이터를 캐시하여 반복 호출 방지 (TTL 60초)"""
    now = datetime.now(timezone.utc)
    cached = _futures_cache.get(symbol)
    if cached and (now - cached["ts"]).total_seconds() < FUTURES_CACHE_TTL:
        return cached["data"]

    data = await get_futures_signals(async_client, symbol)
    if data is None:
        data = []
    _futures_cache[symbol] = {"data": data, "ts": now}
    return data


def _enrich_signal_result(result: dict, symbol: str, signal_name: str, confidence: float) -> dict:
    """시그널 결과에 품질 점수 추가 (백테스트 승률 + BTC 베타)"""
    quality = {}
    if backtest_engine and signal_name != "NEUTRAL":
        wr = backtest_engine.get_signal_win_rate(signal_name, confidence)
        if wr:
            quality["signal_win_rate"] = wr.get("signal_win_rate")
            quality["signal_total"] = wr.get("signal_total")
            quality["confidence_win_rate"] = wr.get("confidence_win_rate")
    if correlation_analyzer and symbol != "BTC/USDT":
        beta = correlation_analyzer.get_beta(symbol)
        if beta is not None:
            quality["btc_beta"] = beta
    if quality:
        result["quality"] = quality
    return result


@app.get("/api/analyze/{symbol}")
async def analyze_symbol(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
):
    timeframe = _validate_timeframe(timeframe)
    symbol = _normalize_symbol(symbol)

    # 1) 스캐너가 이미 계산한 결과가 있으면 즉시 반환 (가장 빠름)
    if scanner and scanner.latest_signals.get(timeframe):
        for sig in scanner.latest_signals[timeframe]:
            if sig.get("symbol") == symbol:
                result = dict(sig)  # 복사
                result = _enrich_signal_result(result, symbol, result.get("signal", ""), result.get("confidence", 0))
                return result

    # 2) 분석 캐시 확인 (15초 내 동일 요청)
    cache_key = f"{symbol}:{timeframe}"
    now = datetime.now(timezone.utc)
    cached = _analysis_cache.get(cache_key)
    if cached and (now - cached["ts"]).total_seconds() < ANALYSIS_CACHE_TTL:
        return cached["result"]

    # 3) 캐시 미스 — 직접 분석 (폴백)
    try:
        df = await candle_repo.get_candles(symbol, timeframe, limit=REALTIME_CANDLE_LIMIT)

        if len(df) < 20:
            raise HTTPException(status_code=400, detail=f"데이터 부족: {len(df)}개 캔들 (최소 20개 필요)")

        higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
        higher_tf_df = None
        if higher_tf != timeframe:
            try:
                higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=REALTIME_HIGHER_TF_LIMIT)
            except Exception as e:
                logger.warning("상위TF(%s) 조회 실패 [%s]: %s", higher_tf, symbol, e)

        futures_data = await _get_futures_cached(symbol)

        signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df, futures_data=futures_data)
        result = signal.to_dict()

        if track_repo:
            try:
                active_track = await track_repo.get_active_track(symbol, timeframe)
                if active_track:
                    result["track"] = {
                        "state": active_track["state"],
                        "consecutive_scans": active_track["consecutive_scans"],
                        "first_detected_at": active_track["first_detected_at"],
                        "confirmed_at": active_track["confirmed_at"],
                        "peak_confidence": active_track["peak_confidence"],
                    }
            except Exception as e:
                logger.debug("분석 트랙 조회 실패 [%s]: %s", symbol, e)

        result = _enrich_signal_result(result, symbol, signal.signal, signal.confidence)

        _analysis_cache[cache_key] = {"result": result, "ts": now}

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("분석 실패 [%s/%s]: %s", symbol, timeframe, e, exc_info=True)
        raise HTTPException(status_code=500, detail="분석 중 오류가 발생했습니다")


@app.get("/api/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=500, le=5000),
):
    timeframe = _validate_timeframe(timeframe)
    symbol = _normalize_symbol(symbol)

    # 1) 프리워밍 캐시에서 즉시 반환 (limit=500, TTL 내)
    cache_key = f"{symbol}:{timeframe}"
    cached = _ohlcv_cache.get(cache_key)
    if cached and limit <= 500:
        age = (datetime.now(timezone.utc) - cached["ts"]).total_seconds()
        if age < OHLCV_CACHE_TTL:
            return {"symbol": symbol, "timeframe": timeframe, "candles": cached["candles"]}

    # 2) 캐시 미스 — DB 조회 (폴백)
    try:
        df = await candle_repo.get_candles(symbol, timeframe, limit=limit)
        candles = []
        for ts, row in df.iterrows():
            candles.append({
                "time": int(ts.timestamp()),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            })
        return {"symbol": symbol, "timeframe": timeframe, "candles": candles}
    except Exception as e:
        logger.error("OHLCV 조회 실패 [%s/%s]: %s", symbol, timeframe, e, exc_info=True)
        raise HTTPException(status_code=500, detail="캔들 데이터 조회 실패")


@app.get("/api/indicators/{symbol}")
async def get_indicator_series(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    indicators: str = Query(default="ema,bb"),
    limit: int = Query(default=500, le=2000),
):
    """지표 시계열 데이터 (차트 오버레이용)"""
    timeframe = _validate_timeframe(timeframe)
    symbol = _normalize_symbol(symbol)

    try:
        df = await candle_repo.get_candles(symbol, timeframe, limit=limit)
        if len(df) < 20:
            raise HTTPException(status_code=400, detail="데이터 부족")

        # df에 time 컬럼 추가 (unix timestamp)
        df = df.copy()
        df["time"] = df.index.astype(int) // 10**9

        requested = [i.strip().lower() for i in indicators.split(",") if i.strip()]
        result = compute_indicator_series(df, requested, timeframe)
        return {"symbol": symbol, "timeframe": timeframe, "indicators": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("지표 시계열 조회 실패 [%s/%s]: %s", symbol, timeframe, e, exc_info=True)
        raise HTTPException(status_code=500, detail="지표 데이터 조회 실패")


@app.get("/api/ticker/{symbol}")
async def get_ticker(symbol: str):
    symbol = _normalize_symbol(symbol)

    # 1) 배치 캐시에서 즉시 반환 (가장 빠름)
    await _refresh_ticker_cache()
    ticker = _ticker_cache.get(symbol)
    if ticker:
        return {
            "symbol": symbol,
            "price": ticker.get("last", 0),
            "change_24h": ticker.get("percentage", 0),
            "volume_usdt": ticker.get("quoteVolume", 0),
            "high_24h": ticker.get("high", 0),
            "low_24h": ticker.get("low", 0),
            "bid": ticker.get("bid", 0),
            "ask": ticker.get("ask", 0),
        }

    # 2) 캐시에 없으면 개별 조회 (폴백)
    try:
        await async_client.ensure_markets()
        t = await async_client.exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "price": t.get("last", 0),
            "change_24h": t.get("percentage", 0),
            "volume_usdt": t.get("quoteVolume", 0),
            "high_24h": t.get("high", 0),
            "low_24h": t.get("low", 0),
            "bid": t.get("bid", 0),
            "ask": t.get("ask", 0),
        }
    except Exception as e:
        logger.error("티커 조회 실패 [%s]: %s", symbol, e)
        raise HTTPException(status_code=502, detail="가격 조회 실패")


@app.get("/api/scan")
async def scan_market(timeframe: str = Query(default=DEFAULT_TIMEFRAME)):
    timeframe = _validate_timeframe(timeframe)
    await scanner.scan_market(timeframe=timeframe)
    return scanner.get_latest_signals(timeframe)


@app.get("/api/signals")
async def get_latest_signals(timeframe: str = Query(default=DEFAULT_TIMEFRAME)):
    return scanner.get_latest_signals(timeframe)


@app.get("/api/signals/all-timeframes")
async def get_all_tf_signals():
    """모든 타임프레임의 최근 시그널"""
    return scanner.get_all_timeframe_signals()


@app.get("/api/signals/history")
async def get_signal_history(
    symbol: str = Query(default=None),
    timeframe: str = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0),
):
    signals = await signal_repo.get_signal_history(
        symbol=symbol, timeframe=timeframe, limit=limit, offset=offset
    )
    return {"signals": signals, "total": len(signals)}


@app.get("/api/signals/tracks")
async def get_signal_tracks(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    state: str = Query(default=None),
):
    tracks = await track_repo.get_active_tracks(timeframe=timeframe, state_filter=state)
    return {"tracks": tracks, "total": len(tracks)}


@app.get("/api/signals/transitions")
async def get_signal_transitions(
    limit: int = Query(default=50, le=200),
    symbol: str = Query(default=None),
):
    transitions = await track_repo.get_recent_transitions(limit=limit, symbol=symbol)
    return {"transitions": transitions, "total": len(transitions)}


@app.get("/api/timeframes")
async def get_timeframes():
    return {"timeframes": TIMEFRAMES, "default": DEFAULT_TIMEFRAME, "scan_timeframes": SCAN_TIMEFRAMES}


@app.get("/api/market-context")
async def get_market_context():
    """현재 시장 맥락 데이터 조회"""
    return _market_context


# ─── 자기학습 API ─────────────────────────────────────────

@app.get("/api/learning/weights")
async def get_learning_weights():
    if not learning_engine:
        return {
            "weights": SignalEngine.DEFAULT_WEIGHTS,
            "is_adaptive": False,
            "default_weights": SignalEngine.DEFAULT_WEIGHTS,
        }
    weights = await learning_engine.get_adaptive_weights()
    return {
        "weights": weights or SignalEngine.DEFAULT_WEIGHTS,
        "is_adaptive": learning_engine._cached_weights is not None,
        "default_weights": SignalEngine.DEFAULT_WEIGHTS,
    }


@app.get("/api/learning/accuracy")
async def get_indicator_accuracy():
    stats = await learning_engine.get_indicator_stats() if learning_engine else []
    return {"indicators": stats, "total": len(stats)}


@app.get("/api/backfill/status")
async def get_backfill_status():
    status = {}
    for sym in SCAN_SYMBOLS:
        status[sym] = {}
        for tf in BACKFILL_TIMEFRAMES:
            count = await candle_repo.get_candle_count(sym, tf)
            status[sym][tf] = count
    return {"backfill": status}


@app.post("/api/backfill/run")
async def trigger_backfill():
    asyncio.create_task(run_backfill())
    return {"message": "백필 시작됨 (백그라운드)"}


@app.post("/api/learning/run")
async def trigger_learning():
    if not learning_engine:
        raise HTTPException(status_code=500, detail="학습 엔진 미초기화")
    await run_self_learning()
    weights = await learning_engine.get_adaptive_weights()
    return {"message": "학습 완료", "weights": weights}


# ─── 백테스트 API ──────────────────────────────────────

@app.get("/api/backtest/stats")
async def get_backtest_stats():
    """백테스트 통계 조회"""
    if not backtest_engine:
        return {}
    stats = await backtest_engine.run_backtest()
    return stats


@app.get("/api/backtest/win-rate")
async def get_backtest_win_rate(
    signal: str = Query(default="LONG"),
    confidence: float = Query(default=0.5),
):
    """특정 시그널 유형의 역대 승률 조회"""
    if not backtest_engine:
        return {"win_rate": None}
    result = backtest_engine.get_signal_win_rate(signal, confidence)
    return result or {"win_rate": None}


# ─── 상관관계 API ──────────────────────────────────────

@app.get("/api/correlation/summary")
async def get_correlation_summary():
    """상관관계 분석 요약"""
    if not correlation_analyzer:
        return {"symbol_count": 0, "beta_count": 0}
    return correlation_analyzer.get_summary()


@app.get("/api/correlation/beta/{symbol}")
async def get_symbol_beta(symbol: str):
    """특정 심볼의 BTC 대비 베타 계수"""
    symbol = _normalize_symbol(symbol)
    if not correlation_analyzer:
        return {"symbol": symbol, "beta": None}
    beta = correlation_analyzer.get_beta(symbol)
    return {"symbol": symbol, "beta": beta}


# ─── 포트폴리오 리스크 API ─────────────────────────────

@app.get("/api/portfolio/risk")
async def get_portfolio_risk():
    """현재 포트폴리오 리스크 평가"""
    if not risk_manager or not paper_trading_repo:
        return {"error": "리스크 매니저 미초기화"}
    account = await paper_trading_repo.get_or_create_account()
    positions = await paper_trading_repo.get_all_open_positions()
    equity = account.get("balance", 10000) + sum(
        t.get("unrealized_pnl", 0) for t in positions
    )
    report = risk_manager.assess_risk(
        [{"symbol": p["symbol"], "position_usdt": p.get("position_usdt", 0)} for p in positions],
        equity,
    )
    return report.to_dict()


@app.get("/api/auto-trade/config")
async def get_auto_trade_config():
    """자동매매 설정 조회"""
    return {
        "enabled": trade_executor.enabled if trade_executor else False,
        "max_positions": trade_executor.max_positions if trade_executor else 3,
        "max_position_pct": trade_executor.max_position_pct if trade_executor else 10.0,
    }


@app.post("/api/auto-trade/config")
async def update_auto_trade_config(request: Request):
    """자동매매 설정 변경"""
    if not trade_executor:
        raise HTTPException(status_code=500, detail="자동매매 미초기화")
    body = await request.json()
    if "enabled" in body:
        trade_executor.enabled = bool(body["enabled"])
    if "max_positions" in body:
        trade_executor.max_positions = max(1, min(10, int(body["max_positions"])))
    if "max_position_pct" in body:
        trade_executor.max_position_pct = max(1.0, min(50.0, float(body["max_position_pct"])))
    return await get_auto_trade_config()


# ─── 예측 API ──────────────────────────────────────────

@app.post("/api/predictions/expire-all")
async def expire_all_predictions():
    count = await prediction_repo.expire_all_predictions()
    return {"success": True, "expired_count": count}


@app.post("/api/predictions/{symbol}")
async def create_prediction(
    symbol: str,
    request: Request,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
):
    timeframe = _validate_timeframe(timeframe)
    symbol = _normalize_symbol(symbol)

    try:
        df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

        if len(df) < 20:
            raise HTTPException(status_code=400, detail="데이터 부족")

        higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
        higher_tf_df = None
        if higher_tf != timeframe:
            try:
                higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
            except Exception as e:
                logger.debug("예측 상위TF(%s) 조회 실패 [%s]: %s", higher_tf, symbol, e)

        signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df)

        if signal.trade_params is None and signal.signal != "NEUTRAL":
            raise HTTPException(status_code=400, detail="트레이드 파라미터 계산 불가")

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass  # body가 없는 경우 기본값 사용
        horizon = body.get("horizon_candles", DEFAULT_HORIZON_CANDLES.get(timeframe, 24))

        regime_result = detect_regime(df)

        sr_levels = []
        if signal.price_levels:
            for key in ("support_1", "support_2", "resistance_1", "resistance_2"):
                val = signal.price_levels.get(key)
                if val:
                    sr_levels.append(val)

        cal = None
        stats = await prediction_repo.get_accuracy_stats(symbol=symbol)
        if stats["total_predictions"] >= 5:
            cal = {
                "avg_accuracy": stats["avg_accuracy_score"],
                "count": stats["total_predictions"],
            }

        btc_signal = _market_context.get("btc_signal")
        is_alt = symbol != "BTC/USDT"

        # 과거 수익률 추출 (몬테카를로 리샘플링용)
        hist_returns = None
        if len(df) >= 100:
            hist_returns = df["close"].pct_change().dropna().values

        pl = signal.price_levels or {}
        prediction_data = generate_prediction(
            signal_direction=signal.signal,
            confidence=signal.confidence,
            entry_price=signal.current_price,
            trade_params=signal.trade_params,
            price_levels=pl,
            timeframe=timeframe,
            horizon_candles=horizon,
            indicator_snapshot=signal.indicator_snapshot,
            regime=regime_result.regime,
            calibration=cal,
            sr_levels=sr_levels,
            btc_signal_direction=btc_signal,
            is_altcoin=is_alt,
            historical_returns=hist_returns,
        )

        tp = signal.trade_params or {}
        pred_id = await prediction_repo.create_prediction(
            symbol=symbol,
            timeframe=timeframe,
            signal_direction=signal.signal,
            confidence=signal.confidence,
            entry_price=signal.current_price,
            stop_loss=tp.get("stop_loss") or 0,
            take_profit_1=tp.get("take_profit_1") or 0,
            take_profit_2=tp.get("take_profit_2") or 0,
            take_profit_3=tp.get("take_profit_3") or 0,
            atr=pl.get("atr", 0),
            atr_percent=pl.get("atr_percent", 0),
            predicted_path=prediction_data["predicted_path"],
            upper_bound_path=prediction_data["upper_bound_path"],
            lower_bound_path=prediction_data["lower_bound_path"],
            horizon_candles=horizon,
            regime=regime_result.regime,
            calibration_factor=cal["avg_accuracy"] if cal else 1.0,
        )

        result = await prediction_repo.get_prediction_by_id(pred_id)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("예측 생성 실패 [%s/%s]: %s", symbol, timeframe, e, exc_info=True)
        raise HTTPException(status_code=500, detail="예측 생성 중 오류가 발생했습니다")


@app.get("/api/predictions/stats")
async def get_prediction_stats(symbol: str = Query(default=None)):
    sym = _normalize_symbol(symbol) if symbol else None
    stats = await prediction_repo.get_accuracy_stats(symbol=sym)
    return stats


@app.get("/api/predictions/dashboard")
async def get_prediction_dashboard():
    stats = await prediction_repo.get_global_prediction_stats()
    return stats


@app.get("/api/predictions/all")
async def get_all_predictions(
    status: str = Query(default=None),
    direction: str = Query(default=None),
    timeframe: str = Query(default=None),
    result: str = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    """전체 코인의 예측 조회 (필터 + 페이지네이션)"""
    predictions = await prediction_repo.get_predictions_history(
        status=status, direction=direction, timeframe=timeframe,
        result=result, limit=limit, offset=offset,
    )
    total = await prediction_repo.get_predictions_count(
        status=status, direction=direction, timeframe=timeframe, result=result,
    )
    return {"predictions": predictions, "total": total}


@app.get("/api/predictions/active")
async def get_all_active_predictions():
    predictions = await prediction_repo.get_all_active_predictions()
    return {"predictions": predictions, "total": len(predictions)}


@app.get("/api/predictions/{symbol}/active")
async def get_active_prediction(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
):
    symbol = _normalize_symbol(symbol)
    prediction = await prediction_repo.get_active_prediction(symbol, timeframe)
    return {"prediction": prediction}


@app.get("/api/predictions/{symbol}")
async def get_predictions(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    status: str = Query(default=None),
    limit: int = Query(default=20, le=100),
):
    symbol = _normalize_symbol(symbol)
    predictions = await prediction_repo.get_predictions_history(
        symbol=symbol, status=status, limit=limit
    )
    return {"predictions": predictions, "total": len(predictions)}


@app.post("/api/predictions/{prediction_id}/verify")
async def verify_prediction_manual(prediction_id: int):
    prediction = await prediction_repo.get_prediction_by_id(prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="예측을 찾을 수 없습니다")
    if prediction["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="이미 검증된 예측입니다")
    result = await _verify_single_prediction(prediction)
    return result


@app.post("/api/predictions/{prediction_id}/expire")
async def expire_prediction(prediction_id: int):
    prediction = await prediction_repo.get_prediction_by_id(prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="예측을 찾을 수 없습니다")
    if prediction["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="활성 예측이 아닙니다")
    ok = await prediction_repo.expire_prediction(prediction_id)
    if not ok:
        raise HTTPException(status_code=500, detail="만료 처리 실패")
    return {"success": True, "prediction_id": prediction_id}


# ─── 알림 API (DB 기반) ──────────────────────────────────

@app.get("/api/alerts")
async def get_alerts(
    limit: int = Query(default=50, le=200),
    unread_only: bool = Query(default=False),
):
    if alert_repo:
        return await alert_repo.get_alerts(limit=limit, unread_only=unread_only)
    return {"alerts": [], "total": 0, "unread": 0}


@app.post("/api/alerts/read")
async def mark_alerts_read(request: Request):
    body = await request.json()
    alert_ids = body.get("alert_ids", [])
    if alert_repo:
        success = await alert_repo.mark_read(alert_ids if alert_ids else None)
        return {"success": success}
    return {"success": False}


@app.get("/api/alerts/config")
async def get_alert_config():
    return {
        "enabled": _alert_enabled,
        "min_confidence": _alert_min_confidence,
        "signal_types": _alert_signal_types,
        "cooldown_minutes": _alert_cooldown_minutes,
    }


@app.post("/api/alerts/config")
async def update_alert_config(request: Request):
    global _alert_enabled, _alert_min_confidence, _alert_signal_types, _alert_cooldown_minutes
    body = await request.json()

    if "enabled" in body:
        _alert_enabled = bool(body["enabled"])
    if "min_confidence" in body:
        _alert_min_confidence = max(0.1, min(0.95, float(body["min_confidence"])))
    if "signal_types" in body:
        valid_types = {"STRONG_LONG", "LONG", "SHORT", "STRONG_SHORT"}
        _alert_signal_types = [t for t in body["signal_types"] if t in valid_types]
    if "cooldown_minutes" in body:
        _alert_cooldown_minutes = max(1, min(1440, int(body["cooldown_minutes"])))

    return await get_alert_config()


# ─── WebSocket ──────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("WebSocket 연결 (%d명 접속 중)", len(connected_clients))

    try:
        latest = scanner.get_latest_signals()
        unread_count = await alert_repo.get_unread_count() if alert_repo else 0
        await websocket.send_text(_safe_dumps({
            "type": "initial",
            "data": {**latest, "unread_alerts": unread_count}
        }))

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                logger.warning("WS 잘못된 JSON 수신: %s", data[:100])
                continue

            if message.get("type") == "subscribe":
                symbol = message.get("symbol", "BTC/USDT")
                timeframe = message.get("timeframe", DEFAULT_TIMEFRAME)
                symbol = _normalize_symbol(symbol)
                client_subscriptions[websocket] = {
                    "symbol": symbol, "timeframe": timeframe
                }
                logger.info("WS 구독: %s/%s", symbol, timeframe)

                try:
                    df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

                    higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
                    higher_tf_df = None
                    if higher_tf != timeframe:
                        try:
                            higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
                        except Exception as e:
                            logger.debug("WS 상위TF(%s) 조회 실패 [%s]: %s", higher_tf, symbol, e)

                    futures_data = await get_futures_signals(async_client, symbol)
                    if futures_data is None:
                        futures_data = []
                    signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df, futures_data=futures_data)
                    signal_data = signal.to_dict()

                    if track_repo:
                        try:
                            active_track = await track_repo.get_active_track(symbol, timeframe)
                            if active_track:
                                signal_data["track"] = {
                                    "state": active_track["state"],
                                    "consecutive_scans": active_track["consecutive_scans"],
                                    "first_detected_at": active_track["first_detected_at"],
                                    "confirmed_at": active_track["confirmed_at"],
                                    "peak_confidence": active_track["peak_confidence"],
                                }
                        except Exception as e:
                            logger.debug("WS 트랙 조회 실패 [%s]: %s", symbol, e)

                    await websocket.send_text(_safe_dumps({
                        "type": "subscription_update",
                        "data": signal_data
                    }))
                except Exception as e:
                    await websocket.send_text(_safe_dumps({
                        "type": "error",
                        "message": str(e)
                    }))

            elif message.get("type") == "unsubscribe":
                client_subscriptions.pop(websocket, None)
                logger.info("WS 구독 해제")

            elif message.get("type") == "analyze":
                symbol = message.get("symbol", "BTC/USDT")
                timeframe = message.get("timeframe", DEFAULT_TIMEFRAME)

                try:
                    symbol = _normalize_symbol(symbol)
                    df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)
                    signal = engine.analyze(df, symbol, timeframe)
                    await websocket.send_text(_safe_dumps({
                        "type": "analysis",
                        "data": signal.to_dict()
                    }))
                except Exception as e:
                    await websocket.send_text(_safe_dumps({
                        "type": "error",
                        "message": str(e)
                    }))

    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        client_subscriptions.pop(websocket, None)
        logger.info("WebSocket 연결 해제 (%d명 접속 중)", len(connected_clients))


# ─── 모의 트레이딩 API ──────────────────────────────────────


@app.get("/api/paper/account")
async def get_paper_account():
    """모의 트레이딩 계좌 조회 (없으면 자동 생성)."""
    account = await paper_trading_repo.get_or_create_account()
    return account


@app.post("/api/paper/reset")
async def reset_paper_account():
    """모의 트레이딩 계좌 초기화."""
    account = await paper_trading_repo.get_or_create_account()
    result = await paper_trading_repo.reset_account(account["id"])
    return result


@app.post("/api/paper/open")
async def open_paper_trade(request: Request):
    """포지션 진입 (시장가)."""
    body = await request.json()
    symbol = _normalize_symbol(body["symbol"])
    direction = body["direction"]
    position_usdt = float(body["position_usdt"])

    await _refresh_ticker_cache()
    ticker = _ticker_cache.get(symbol)
    if not ticker or not ticker.get("last"):
        raise HTTPException(status_code=400, detail="현재가 조회 실패")
    entry_price = ticker["last"]
    quantity = position_usdt / entry_price

    account = await paper_trading_repo.get_or_create_account()
    if account["balance"] < position_usdt:
        raise HTTPException(status_code=400, detail="잔고 부족")

    trade = await paper_trading_repo.open_trade(
        account_id=account["id"],
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        position_usdt=position_usdt,
        quantity=quantity,
        stop_loss=body.get("stop_loss"),
        take_profit_1=body.get("take_profit_1"),
        take_profit_2=body.get("take_profit_2"),
        take_profit_3=body.get("take_profit_3"),
    )

    if connected_clients:
        await _broadcast_ws(_safe_dumps({
            "type": "paper_trade_opened",
            "data": trade,
        }))

    return trade


@app.post("/api/paper/close/{trade_id}")
async def close_paper_trade(trade_id: int):
    """포지션 수동 청산 (시장가)."""
    trade = await paper_trading_repo.get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="트레이드를 찾을 수 없습니다")
    if trade["status"] != "OPEN":
        raise HTTPException(status_code=400, detail="이미 종료된 포지션입니다")

    await _refresh_ticker_cache()
    ticker = _ticker_cache.get(trade["symbol"])
    if not ticker or not ticker.get("last"):
        raise HTTPException(status_code=400, detail="현재가 조회 실패")

    result = await paper_trading_repo.close_trade(
        trade_id=trade_id,
        close_price=ticker["last"],
        close_reason="MANUAL",
    )

    if connected_clients:
        await _broadcast_ws(_safe_dumps({
            "type": "paper_trade_closed",
            "data": result,
        }))

    return result


@app.get("/api/paper/positions")
async def get_paper_positions():
    """열린 포지션 목록."""
    account = await paper_trading_repo.get_or_create_account()
    positions = await paper_trading_repo.get_open_positions(account["id"])
    return {"positions": positions, "total": len(positions)}


@app.get("/api/paper/history")
async def get_paper_trade_history(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    """거래 히스토리 (종료된 트레이드)."""
    account = await paper_trading_repo.get_or_create_account()
    trades = await paper_trading_repo.get_trade_history(account["id"], limit=limit, offset=offset)
    total = await paper_trading_repo.get_trade_count(account["id"])
    return {"trades": trades, "total": total}


@app.get("/api/paper/stats")
async def get_paper_trading_stats():
    """트레이딩 통계."""
    account = await paper_trading_repo.get_or_create_account()
    positions = await paper_trading_repo.get_open_positions(account["id"])
    total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    return {
        "account": account,
        "open_positions": len(positions),
        "total_unrealized_pnl": round(total_unrealized, 2),
        "equity": round(account["balance"] + total_unrealized, 2),
    }


# ---------------------------------------------------------------------------
# 프론트엔드 리버스 프록시 (catch-all) — 반드시 모든 API 라우트 아래에 위치
# Cloudflare → 백엔드(8001)로만 라우팅되는 환경에서 프론트엔드를 서빙하기 위함
# ---------------------------------------------------------------------------
_FRONTEND_ORIGIN = "http://coin-frontend:3000"
_proxy_client = None


async def _get_proxy_client():
    global _proxy_client
    if _proxy_client is None:
        import httpx
        _proxy_client = httpx.AsyncClient(base_url=_FRONTEND_ORIGIN, timeout=30, follow_redirects=True)
    return _proxy_client


@app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"])
async def frontend_proxy(request: Request, path: str):
    """API가 아닌 모든 요청을 프론트엔드 컨테이너로 프록시"""
    client = await _get_proxy_client()
    url = f"/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    # 프론트엔드로 전달할 헤더 (hop-by-hop 제외)
    fwd_headers = {}
    for k, v in request.headers.items():
        if k.lower() not in ("host", "connection", "transfer-encoding"):
            fwd_headers[k] = v

    try:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=fwd_headers,
            content=await request.body() if request.method in ("POST", "PUT", "PATCH") else None,
        )
        # hop-by-hop 헤더 제거
        resp_headers = {k: v for k, v in resp.headers.items()
                        if k.lower() not in ("transfer-encoding", "connection", "content-encoding")}
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp_headers,
            media_type=resp.headers.get("content-type"),
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Frontend unavailable")


# 루트 경로도 프록시
@app.get("/", include_in_schema=False)
async def frontend_root(request: Request):
    return await frontend_proxy(request, "")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)

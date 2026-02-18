"""
FastAPI 메인 서버
REST API + WebSocket 엔드포인트
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from logging_config import setup_logging
from config import (
    HOST, PORT, SCAN_INTERVAL_SECONDS, TIMEFRAMES, DEFAULT_TIMEFRAME,
    ALLOWED_ORIGINS, LOG_LEVEL, LOG_DIR, HIGHER_TF_MAP,
    ALERT_ENABLED, ALERT_MIN_CONFIDENCE, ALERT_SIGNAL_TYPES, ALERT_COOLDOWN_MINUTES,
    ANALYSIS_CANDLE_LIMIT, SUPABASE_SCHEMA, SCAN_SYMBOLS,
    BACKFILL_DAYS, BACKFILL_TIMEFRAMES, BACKFILL_BATCH_SIZE, BACKFILL_CONCURRENCY,
)
from exchange import AsyncBinanceClient
from scanner import MarketScanner
from analysis.signal_engine import SignalEngine
from analysis.regime import detect_regime
from db import Database, CandleRepo, SignalRepo, SignalTrackRepo, PredictionRepo
from data_collector import DataCollector
from analysis.prediction import generate_prediction
from analysis.self_learning import SelfLearningEngine

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
learning_engine: SelfLearningEngine | None = None

# WebSocket 연결 관리
connected_clients: List[WebSocket] = []
client_subscriptions: Dict[WebSocket, Optional[dict]] = {}

# 알림 저장소 (인메모리)
alerts_store: List[dict] = []
alert_cooldowns: Dict[str, str] = {}  # "symbol_signal" -> last_alert_iso
ALERTS_MAX = 200

# 런타임 알림 설정 (config에서 초기화, POST로 변경 가능)
_alert_enabled = ALERT_ENABLED
_alert_min_confidence = ALERT_MIN_CONFIDENCE
_alert_signal_types = list(ALERT_SIGNAL_TYPES)
_alert_cooldown_minutes = ALERT_COOLDOWN_MINUTES


def _normalize_symbol(symbol: str) -> str:
    """심볼 정규화: BTCUSDT -> BTC/USDT"""
    if "/" not in symbol:
        symbol = symbol.replace("USDT", "/USDT")
    return symbol


def _validate_timeframe(timeframe: str) -> str:
    """타임프레임 검증"""
    if timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 타임프레임: {timeframe}. 사용 가능: {', '.join(TIMEFRAMES)}"
        )
    return timeframe


async def _broadcast_ws(message: str):
    """모든 WS 클라이언트에 메시지 브로드캐스트"""
    disconnected = []
    for ws in connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connected_clients.remove(ws)
        client_subscriptions.pop(ws, None)


async def _push_transition_alert(transition: dict):
    """상태 전환 기반 알림 생성 + WS push"""
    if not _alert_enabled:
        return

    now = datetime.now(timezone.utc)
    to_state = transition.get("to_state", "")
    direction = transition.get("direction", "")
    symbol = transition.get("symbol", "")

    # 쿨다운 체크 (트랙 단위)
    cooldown_key = f"track_{transition.get('track_id', '')}"
    if cooldown_key in alert_cooldowns:
        last_time = datetime.fromisoformat(alert_cooldowns[cooldown_key])
        if (now - last_time).total_seconds() < _alert_cooldown_minutes * 60:
            return

    alert_cooldowns[cooldown_key] = now.isoformat()

    # 알림 메시지 생성
    if to_state == "CONFIRMED":
        signal_label = f"{'롱' if direction == 'LONG' else '숏'} 시그널 확정"
    elif to_state == "WEAKENING":
        signal_label = f"{'롱' if direction == 'LONG' else '숏'} 시그널 약화"
    else:
        return

    alert = {
        "id": len(alerts_store) + 1,
        "symbol": symbol,
        "signal": f"{'STRONG_LONG' if direction == 'LONG' else 'STRONG_SHORT'}",
        "confidence": transition.get("confidence", 0),
        "current_price": transition.get("current_price", 0),
        "summary": signal_label,
        "trade_params": None,
        "timestamp": now.isoformat(),
        "read": False,
        "transition": to_state,
    }
    alerts_store.insert(0, alert)
    while len(alerts_store) > ALERTS_MAX:
        alerts_store.pop()

    await _broadcast_ws(json.dumps({"type": "alert", "data": alert}))


async def push_subscription_updates():
    """구독 중인 클라이언트에게 실시간 분석 push"""
    disconnected = []
    for ws, sub in list(client_subscriptions.items()):
        if sub is None:
            continue
        try:
            symbol = sub["symbol"]
            timeframe = sub["timeframe"]
            collector = DataCollector(async_client, candle_repo)
            await collector.collect(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)
            df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

            # 상위 TF 데이터 수집
            higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
            higher_tf_df = None
            if higher_tf != timeframe:
                try:
                    await collector.collect(symbol, higher_tf)
                    higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
                except Exception as e:
                    logger.warning("상위TF(%s) 수집 실패 [%s]: %s", higher_tf, symbol, e)

            signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df)
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
                except Exception:
                    pass

            await ws.send_text(json.dumps({
                "type": "subscription_update",
                "data": signal_data
            }))
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        client_subscriptions.pop(ws, None)
        if ws in connected_clients:
            connected_clients.remove(ws)


async def _auto_generate_prediction(symbol: str, timeframe: str):
    """시그널 CONFIRMED 시 자동 예측 생성."""
    collector = DataCollector(async_client, candle_repo)
    await collector.collect(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)
    df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

    if len(df) < 20:
        logger.warning("자동 예측 스킵 (데이터 부족): %s", symbol)
        return

    higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
    higher_tf_df = None
    if higher_tf != timeframe:
        try:
            await collector.collect(symbol, higher_tf)
            higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
        except Exception:
            pass

    signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df)

    if signal.trade_params is None and signal.signal != "NEUTRAL":
        logger.warning("자동 예측 스킵 (트레이드 파라미터 없음): %s", symbol)
        return

    # 레짐 감지
    regime_result = detect_regime(df)

    # S/R 레벨 추출
    sr_levels = []
    if signal.price_levels:
        for key in ("support_1", "support_2", "resistance_1", "resistance_2"):
            val = signal.price_levels.get(key)
            if val:
                sr_levels.append(val)

    # 캘리브레이션: 과거 정확도 피드백
    cal = None
    stats = await prediction_repo.get_accuracy_stats(symbol=symbol)
    if stats["total_predictions"] >= 5:
        cal = {
            "avg_accuracy": stats["avg_accuracy_score"],
            "count": stats["total_predictions"],
        }

    prediction_data = generate_prediction(
        signal_direction=signal.signal,
        confidence=signal.confidence,
        entry_price=signal.current_price,
        trade_params=signal.trade_params,
        price_levels=signal.price_levels,
        timeframe=timeframe,
        horizon_candles=24,
        indicator_snapshot=signal.indicator_snapshot,
        regime=regime_result.regime,
        calibration=cal,
        sr_levels=sr_levels,
    )

    tp = signal.trade_params or {}
    pred_id = await prediction_repo.create_prediction(
        symbol=symbol,
        timeframe=timeframe,
        signal_direction=signal.signal,
        confidence=signal.confidence,
        entry_price=signal.current_price,
        stop_loss=tp.get("stop_loss", 0),
        take_profit_1=tp.get("take_profit_1", 0),
        take_profit_2=tp.get("take_profit_2", 0),
        take_profit_3=tp.get("take_profit_3", 0),
        atr=signal.price_levels.get("atr", 0),
        atr_percent=signal.price_levels.get("atr_percent", 0),
        predicted_path=prediction_data["predicted_path"],
        upper_bound_path=prediction_data["upper_bound_path"],
        lower_bound_path=prediction_data["lower_bound_path"],
        horizon_candles=24,
        auto_generated=True,
        regime=regime_result.regime,
        calibration_factor=cal["avg_accuracy"] if cal else 1.0,
    )

    logger.info("자동 예측 생성: %s #%d (레짐=%s)", symbol, pred_id, regime_result.regime)

    # WS 브로드캐스트
    pred = await prediction_repo.get_prediction_by_id(pred_id)
    if pred and connected_clients:
        await _broadcast_ws(json.dumps({
            "type": "prediction_created",
            "data": pred,
        }))


async def scheduled_scan():
    """주기적 마켓 스캔"""
    await scanner.scan_market(timeframe=DEFAULT_TIMEFRAME)

    # 트랜지션 기반 알림 + 자동 예측 생성
    for tr in (scanner.latest_transitions or []):
        try:
            if tr["to_state"] == "CONFIRMED":
                await _push_transition_alert(tr)
                # CONFIRMING → CONFIRMED 전환 시 자동 예측 생성
                if tr.get("from_state") == "CONFIRMING":
                    try:
                        await _auto_generate_prediction(tr["symbol"], DEFAULT_TIMEFRAME)
                    except Exception as e:
                        logger.error("자동 예측 생성 실패 [%s]: %s", tr["symbol"], e)
            elif tr["to_state"] == "WEAKENING" and tr.get("from_state") == "CONFIRMED":
                await _push_transition_alert(tr)
        except Exception as e:
            logger.error("전환 알림 실패: %s", e)

    # signal_transition WS 브로드캐스트
    if connected_clients:
        for tr in (scanner.latest_transitions or []):
            if tr.get("to_state") in ("CONFIRMED", "WEAKENING", "EXPIRED"):
                try:
                    await _broadcast_ws(json.dumps({
                        "type": "signal_transition",
                        "data": tr
                    }))
                except Exception:
                    pass

    # scan_update 브로드캐스트 (10개 코인 전체)
    if connected_clients:
        await _broadcast_ws(json.dumps({
            "type": "scan_update",
            "data": scanner.get_latest_signals()
        }))


async def update_prediction_progress():
    """실시간 예측 진행 추적 (60초마다)."""
    if not prediction_repo:
        return
    try:
        active = await prediction_repo.get_all_active_predictions()
        if not active:
            return

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

                # 현재가 조회
                await async_client.ensure_markets()
                ticker = await async_client.exchange.fetch_ticker(symbol)
                current_price = ticker.get("last", 0)
                if not current_price:
                    continue

                # PnL %
                if is_long:
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100

                # R:R 현재 비율
                risk = abs(entry_price - sl) if sl else atr
                reward = abs(current_price - entry_price)
                rr_current = (reward / risk) if risk > 0 else 0

                # 시간 진행률
                created = datetime.fromisoformat(pred["created_at"])
                candle_sec = tf_seconds.get(timeframe, 3600)
                total_sec = pred["horizon_candles"] * candle_sec
                elapsed = (now - created).total_seconds()
                time_pct = min(elapsed / total_sec, 1.0) if total_sec > 0 else 1.0

                # 경로 정확도 (현재가 vs 예측경로의 현재 시점)
                path_accuracy = 0.5
                predicted_path = pred.get("predicted_path", [])
                if predicted_path and atr > 0:
                    now_ts = int(now.timestamp())
                    closest = min(predicted_path, key=lambda p: abs(p["time"] - now_ts))
                    error = abs(current_price - closest["price"])
                    path_accuracy = max(0.0, 1.0 - error / (2.0 * atr))

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

                # 조기 종료 체크: SL 또는 TP3 도달
                if is_long:
                    hit_sl = current_price <= sl
                    hit_tp3 = current_price >= tp3
                else:
                    hit_sl = current_price >= sl
                    hit_tp3 = current_price <= tp3

                if hit_sl or hit_tp3:
                    try:
                        result = await _verify_single_prediction(pred)
                        logger.info(
                            "조기 검증 완료: %s #%d (%s)",
                            symbol, pred["id"], "SL" if hit_sl else "TP3",
                        )
                        if connected_clients:
                            await _broadcast_ws(json.dumps({
                                "type": "prediction_verified",
                                "data": result,
                            }))
                    except Exception as e:
                        logger.error("조기 검증 실패 #%d: %s", pred["id"], e)

            except Exception as e:
                logger.debug("진행 추적 실패 [%s #%d]: %s", pred.get("symbol"), pred.get("id"), e)

        # 진행 업데이트 WS 브로드캐스트
        if progress_updates and connected_clients:
            await _broadcast_ws(json.dumps({
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

    pred_time = datetime.fromisoformat(prediction["created_at"])
    actual_candles = df[df.index >= pred_time]

    if len(actual_candles) < 1:
        return prediction

    # 실제 경로
    actual_path = []
    for ts, row in actual_candles.iterrows():
        actual_path.append({
            "time": int(ts.timestamp()),
            "price": float(row["close"]),
        })

    # MFE / MAE 계산
    if is_long:
        max_favorable = max(
            ((row["high"] - entry_price) / entry_price) * 100
            for _, row in actual_candles.iterrows()
        )
        max_adverse = max(
            ((entry_price - row["low"]) / entry_price) * 100
            for _, row in actual_candles.iterrows()
        )
    else:
        max_favorable = max(
            ((entry_price - row["low"]) / entry_price) * 100
            for _, row in actual_candles.iterrows()
        )
        max_adverse = max(
            ((row["high"] - entry_price) / entry_price) * 100
            for _, row in actual_candles.iterrows()
        )

    final_price = float(actual_candles["close"].iloc[-1])

    # 결과 분류
    if is_long:
        if actual_candles["low"].min() <= sl:
            result = "HIT_SL"
        elif actual_candles["high"].max() >= tp3:
            result = "HIT_TP3"
        elif actual_candles["high"].max() >= tp2:
            result = "HIT_TP2"
        elif actual_candles["high"].max() >= tp1:
            result = "HIT_TP1"
        elif final_price > entry_price:
            result = "PARTIAL"
        else:
            result = "WRONG"
    else:
        if actual_candles["high"].max() >= sl:
            result = "HIT_SL"
        elif actual_candles["low"].min() <= tp3:
            result = "HIT_TP3"
        elif actual_candles["low"].min() <= tp2:
            result = "HIT_TP2"
        elif actual_candles["low"].min() <= tp1:
            result = "HIT_TP1"
        elif final_price < entry_price:
            result = "PARTIAL"
        else:
            result = "WRONG"

    # 정확도 점수: 예측 경로 vs 실제 경로
    predicted_path = prediction["predicted_path"]
    actual_map = {p["time"]: p["price"] for p in actual_path}
    scores = []
    for point in predicted_path:
        t = point["time"]
        pred_price = point["price"]
        actual_price = actual_map.get(t)
        if actual_price is None:
            closest_t = min(actual_map.keys(), key=lambda at: abs(at - t), default=None)
            if closest_t is None:
                continue
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


async def run_self_learning():
    """자기학습 실행 (6시간마다) - 지표 정확도 분석 및 가중치 자동 조정"""
    if not learning_engine:
        return
    try:
        await learning_engine.run_learning_cycle()
        # 학습 결과를 시그널 엔진에 반영
        weights = await learning_engine.get_adaptive_weights()
        engine.set_adaptive_weights(weights)
    except Exception as e:
        logger.error("자기학습 실패: %s", e)


async def run_backfill():
    """히스토리 백필 (서버 시작 시 1회 + 이후 24시간마다 증분)"""
    try:
        collector = DataCollector(async_client, candle_repo)
        results = await collector.backfill_all(
            symbols=SCAN_SYMBOLS,
            timeframes=BACKFILL_TIMEFRAMES,
            days=BACKFILL_DAYS,
            batch_size=BACKFILL_BATCH_SIZE,
            concurrency=BACKFILL_CONCURRENCY,
        )
        total = sum(c for sym in results.values() for c in sym.values())
        if total > 0:
            logger.info("백필 완료: 총 %d개 캔들 저장", total)
        else:
            logger.info("백필: 새로 저장할 데이터 없음 (이미 최신)")
    except Exception as e:
        logger.error("백필 실패: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scanner, candle_repo, signal_repo, track_repo, prediction_repo, learning_engine

    # DB 초기화
    await database.connect()
    candle_repo = CandleRepo(database.client, SUPABASE_SCHEMA)
    signal_repo = SignalRepo(database.client, SUPABASE_SCHEMA)
    track_repo = SignalTrackRepo(database.client, SUPABASE_SCHEMA)
    prediction_repo = PredictionRepo(database.client, SUPABASE_SCHEMA)
    learning_engine = SelfLearningEngine(database.client, SUPABASE_SCHEMA)
    logger.info("Supabase 데이터베이스 연결 완료")

    # DB 연동 스캐너 생성 (트래커 포함)
    scanner = MarketScanner(async_client, candle_repo, signal_repo, track_repo)

    # 시작 시 저장된 학습 가중치 로드
    try:
        saved_weights = await learning_engine.get_adaptive_weights()
        engine.set_adaptive_weights(saved_weights)
        logger.info("저장된 적응형 가중치 로드 완료")
    except Exception as e:
        logger.warning("적응형 가중치 로드 실패 (기본값 사용): %s", e)

    # 주기적 작업 시작
    scheduler.add_job(scheduled_scan, "interval", seconds=SCAN_INTERVAL_SECONDS)
    scheduler.add_job(push_subscription_updates, "interval", seconds=15)
    scheduler.add_job(cleanup_expired_tracks, "interval", hours=6)
    scheduler.add_job(verify_predictions, "interval", minutes=5)
    scheduler.add_job(update_prediction_progress, "interval", seconds=60)
    scheduler.add_job(run_self_learning, "interval", hours=6)
    scheduler.add_job(run_backfill, "interval", hours=24)
    scheduler.start()
    logger.info("스캐너 시작 (주기: %d초), 자기학습 활성화", SCAN_INTERVAL_SECONDS)

    # 백필: 백그라운드로 즉시 시작 (서버 응답 차단 안 함)
    asyncio.create_task(run_backfill())

    yield

    # 종료
    scheduler.shutdown()
    await async_client.close()
    await database.close()
    logger.info("서버 종료 완료")


app = FastAPI(
    title="Crypto Signal System",
    description="암호화폐 롱/숏 시그널 분석 시스템",
    version="3.0.0",
    lifespan=lifespan,
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
    """시스템 상태 확인"""
    checks = {
        "database": False,
        "exchange": False,
        "scanner_active": scanner is not None,
        "last_scan": scanner.last_scan_time if scanner else None,
        "connected_clients": len(connected_clients),
        "active_subscriptions": sum(1 for v in client_subscriptions.values() if v),
        "pending_alerts": sum(1 for a in alerts_store if not a.get("read")),
    }
    try:
        await database.client.schema(SUPABASE_SCHEMA).table("ohlcv").select("symbol").limit(1).execute()
        checks["database"] = True
    except Exception:
        pass
    try:
        await async_client.ensure_markets()
        checks["exchange"] = True
    except Exception:
        pass

    status = "healthy" if checks["database"] and checks["exchange"] else "degraded"
    return {"status": status, "checks": checks}


@app.get("/api/markets")
async def get_markets():
    """USDT 마켓 목록 조회"""
    try:
        markets = await async_client.get_usdt_markets()
        return {"markets": markets, "total": len(markets)}
    except Exception as e:
        logger.error("마켓 목록 조회 실패: %s", e)
        raise HTTPException(status_code=502, detail="거래소 연결 실패")


@app.get("/api/analyze/{symbol}")
async def analyze_symbol(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
):
    """개별 코인 분석"""
    timeframe = _validate_timeframe(timeframe)
    symbol = _normalize_symbol(symbol)

    try:
        collector = DataCollector(async_client, candle_repo)
        await collector.collect(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)
        df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

        if len(df) < 20:
            raise HTTPException(status_code=400, detail=f"데이터 부족: {len(df)}개 캔들 (최소 20개 필요)")

        # 상위 TF 데이터
        higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
        higher_tf_df = None
        if higher_tf != timeframe:
            try:
                await collector.collect(symbol, higher_tf)
                higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
            except Exception as e:
                logger.warning("상위TF(%s) 수집 실패 [%s]: %s", higher_tf, symbol, e)

        signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df)
        result = signal.to_dict()

        # 트랙 데이터 병합
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
            except Exception:
                pass

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
    limit: int = Query(default=200, le=1000),
):
    """캔들 데이터 조회 (차트용)"""
    timeframe = _validate_timeframe(timeframe)
    symbol = _normalize_symbol(symbol)

    try:
        collector = DataCollector(async_client, candle_repo)
        await collector.collect(symbol, timeframe)
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


@app.get("/api/ticker/{symbol}")
async def get_ticker(symbol: str):
    """개별 코인 실시간 가격 조회"""
    symbol = _normalize_symbol(symbol)

    try:
        await async_client.ensure_markets()
        ticker = await async_client.exchange.fetch_ticker(symbol)
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
    except Exception as e:
        logger.error("티커 조회 실패 [%s]: %s", symbol, e)
        raise HTTPException(status_code=502, detail="가격 조회 실패")


@app.get("/api/scan")
async def scan_market(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
):
    """마켓 스캔 실행"""
    timeframe = _validate_timeframe(timeframe)
    await scanner.scan_market(timeframe=timeframe)
    return scanner.get_latest_signals()


@app.get("/api/signals")
async def get_latest_signals():
    """최근 스캔 결과 조회"""
    return scanner.get_latest_signals()


@app.get("/api/signals/history")
async def get_signal_history(
    symbol: str = Query(default=None),
    timeframe: str = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0),
):
    """시그널 히스토리 조회"""
    signals = await signal_repo.get_signal_history(
        symbol=symbol, timeframe=timeframe, limit=limit, offset=offset
    )
    return {"signals": signals, "total": len(signals)}


@app.get("/api/signals/tracks")
async def get_signal_tracks(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    state: str = Query(default=None),
):
    """활성 시그널 트랙 목록"""
    tracks = await track_repo.get_active_tracks(
        timeframe=timeframe, state_filter=state
    )
    return {"tracks": tracks, "total": len(tracks)}


@app.get("/api/signals/transitions")
async def get_signal_transitions(
    limit: int = Query(default=50, le=200),
    symbol: str = Query(default=None),
):
    """최근 상태 전환 로그"""
    transitions = await track_repo.get_recent_transitions(
        limit=limit, symbol=symbol
    )
    return {"transitions": transitions, "total": len(transitions)}


@app.get("/api/timeframes")
async def get_timeframes():
    """지원 타임프레임 목록"""
    return {"timeframes": TIMEFRAMES, "default": DEFAULT_TIMEFRAME}


# ─── 자기학습 API ─────────────────────────────────────────

@app.get("/api/learning/weights")
async def get_learning_weights():
    """현재 적응형 가중치 조회"""
    weights = await learning_engine.get_adaptive_weights() if learning_engine else {}
    return {
        "weights": weights,
        "is_adaptive": learning_engine._cached_weights is not None if learning_engine else False,
        "default_weights": SignalEngine.DEFAULT_WEIGHTS,
    }


@app.get("/api/learning/accuracy")
async def get_indicator_accuracy():
    """지표별 정확도 통계 조회"""
    stats = await learning_engine.get_indicator_stats() if learning_engine else []
    return {"indicators": stats, "total": len(stats)}


@app.get("/api/backfill/status")
async def get_backfill_status():
    """백필 상태 조회 - 심볼별/타임프레임별 저장된 캔들 수"""
    status = {}
    for sym in SCAN_SYMBOLS:
        status[sym] = {}
        for tf in BACKFILL_TIMEFRAMES:
            count = await candle_repo.get_candle_count(sym, tf)
            status[sym][tf] = count
    return {"backfill": status}


@app.post("/api/backfill/run")
async def trigger_backfill():
    """수동 백필 트리거 (백그라운드 실행)"""
    asyncio.create_task(run_backfill())
    return {"message": "백필 시작됨 (백그라운드)"}


@app.post("/api/learning/run")
async def trigger_learning():
    """수동 학습 트리거"""
    if not learning_engine:
        raise HTTPException(status_code=500, detail="학습 엔진 미초기화")
    await run_self_learning()
    weights = await learning_engine.get_adaptive_weights()
    return {"message": "학습 완료", "weights": weights}


# ─── 예측 API ──────────────────────────────────────────

@app.post("/api/predictions/{symbol}")
async def create_prediction(
    symbol: str,
    request: Request,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
):
    """예측 생성 - 현재 분석 기반으로 미래 가격 경로 예측"""
    timeframe = _validate_timeframe(timeframe)
    symbol = _normalize_symbol(symbol)

    try:
        collector = DataCollector(async_client, candle_repo)
        await collector.collect(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)
        df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

        if len(df) < 20:
            raise HTTPException(status_code=400, detail="데이터 부족")

        higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
        higher_tf_df = None
        if higher_tf != timeframe:
            try:
                await collector.collect(symbol, higher_tf)
                higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
            except Exception:
                pass

        signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df)

        if signal.trade_params is None and signal.signal != "NEUTRAL":
            raise HTTPException(status_code=400, detail="트레이드 파라미터 계산 불가")

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        horizon = body.get("horizon_candles", 24)

        # 레짐 감지
        regime_result = detect_regime(df)

        # S/R 레벨 추출
        sr_levels = []
        if signal.price_levels:
            for key in ("support_1", "support_2", "resistance_1", "resistance_2"):
                val = signal.price_levels.get(key)
                if val:
                    sr_levels.append(val)

        # 캘리브레이션
        cal = None
        stats = await prediction_repo.get_accuracy_stats(symbol=symbol)
        if stats["total_predictions"] >= 5:
            cal = {
                "avg_accuracy": stats["avg_accuracy_score"],
                "count": stats["total_predictions"],
            }

        prediction_data = generate_prediction(
            signal_direction=signal.signal,
            confidence=signal.confidence,
            entry_price=signal.current_price,
            trade_params=signal.trade_params,
            price_levels=signal.price_levels,
            timeframe=timeframe,
            horizon_candles=horizon,
            indicator_snapshot=signal.indicator_snapshot,
            regime=regime_result.regime,
            calibration=cal,
            sr_levels=sr_levels,
        )

        tp = signal.trade_params or {}
        pred_id = await prediction_repo.create_prediction(
            symbol=symbol,
            timeframe=timeframe,
            signal_direction=signal.signal,
            confidence=signal.confidence,
            entry_price=signal.current_price,
            stop_loss=tp.get("stop_loss", 0),
            take_profit_1=tp.get("take_profit_1", 0),
            take_profit_2=tp.get("take_profit_2", 0),
            take_profit_3=tp.get("take_profit_3", 0),
            atr=signal.price_levels.get("atr", 0),
            atr_percent=signal.price_levels.get("atr_percent", 0),
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
    """예측 정확도 통계"""
    sym = _normalize_symbol(symbol) if symbol else None
    stats = await prediction_repo.get_accuracy_stats(symbol=sym)
    return stats


@app.get("/api/predictions/dashboard")
async def get_prediction_dashboard():
    """전체 예측 통계 (승률, 리더보드, 최근 결과)"""
    stats = await prediction_repo.get_global_prediction_stats()
    return stats


@app.get("/api/predictions/active")
async def get_all_active_predictions():
    """모든 심볼의 활성 예측 목록"""
    predictions = await prediction_repo.get_all_active_predictions()
    return {"predictions": predictions, "total": len(predictions)}


@app.get("/api/predictions/{symbol}/active")
async def get_active_prediction(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
):
    """현재 활성 예측 조회"""
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
    """예측 히스토리 조회"""
    symbol = _normalize_symbol(symbol)
    predictions = await prediction_repo.get_predictions_history(
        symbol=symbol, status=status, limit=limit
    )
    return {"predictions": predictions, "total": len(predictions)}


@app.post("/api/predictions/{prediction_id}/verify")
async def verify_prediction_manual(prediction_id: int):
    """수동 검증 트리거"""
    prediction = await prediction_repo.get_prediction_by_id(prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="예측을 찾을 수 없습니다")
    if prediction["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="이미 검증된 예측입니다")

    result = await _verify_single_prediction(prediction)
    return result


# ─── 알림 API ──────────────────────────────────────────

@app.get("/api/alerts")
async def get_alerts(
    limit: int = Query(default=50, le=200),
    unread_only: bool = Query(default=False),
):
    """알림 목록 조회"""
    result = alerts_store
    if unread_only:
        result = [a for a in result if not a.get("read")]
    return {
        "alerts": result[:limit],
        "total": len(result),
        "unread": sum(1 for a in alerts_store if not a.get("read")),
    }


@app.post("/api/alerts/read")
async def mark_alerts_read(request: Request):
    """알림 읽음 처리"""
    body = await request.json()
    alert_ids = body.get("alert_ids", [])

    if not alert_ids:
        for a in alerts_store:
            a["read"] = True
    else:
        for a in alerts_store:
            if a["id"] in alert_ids:
                a["read"] = True
    return {"success": True}


@app.get("/api/alerts/config")
async def get_alert_config():
    """현재 알림 설정 조회"""
    return {
        "enabled": _alert_enabled,
        "min_confidence": _alert_min_confidence,
        "signal_types": _alert_signal_types,
        "cooldown_minutes": _alert_cooldown_minutes,
    }


@app.post("/api/alerts/config")
async def update_alert_config(request: Request):
    """알림 설정 업데이트 (런타임)"""
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
    """실시간 시그널 WebSocket"""
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("WebSocket 연결 (%d명 접속 중)", len(connected_clients))

    try:
        # 연결 시 최근 스캔 결과 + 미읽은 알림 수 전송
        latest = scanner.get_latest_signals()
        unread_count = sum(1 for a in alerts_store if not a.get("read"))
        await websocket.send_text(json.dumps({
            "type": "initial",
            "data": {**latest, "unread_alerts": unread_count}
        }))

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "subscribe":
                symbol = message.get("symbol", "BTC/USDT")
                timeframe = message.get("timeframe", DEFAULT_TIMEFRAME)
                symbol = _normalize_symbol(symbol)
                client_subscriptions[websocket] = {
                    "symbol": symbol, "timeframe": timeframe
                }
                logger.info("WS 구독: %s/%s", symbol, timeframe)

                try:
                    collector = DataCollector(async_client, candle_repo)
                    await collector.collect(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)
                    df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

                    higher_tf = HIGHER_TF_MAP.get(timeframe, timeframe)
                    higher_tf_df = None
                    if higher_tf != timeframe:
                        try:
                            await collector.collect(symbol, higher_tf)
                            higher_tf_df = await candle_repo.get_candles(symbol, higher_tf, limit=ANALYSIS_CANDLE_LIMIT)
                        except Exception:
                            pass

                    signal = engine.analyze(df, symbol, timeframe, higher_tf_df=higher_tf_df)
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
                        except Exception:
                            pass

                    await websocket.send_text(json.dumps({
                        "type": "subscription_update",
                        "data": signal_data
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
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
                    collector = DataCollector(async_client, candle_repo)
                    symbol = _normalize_symbol(symbol)
                    await collector.collect(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)

                    df = await candle_repo.get_candles(symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT)
                    signal = engine.analyze(df, symbol, timeframe)
                    await websocket.send_text(json.dumps({
                        "type": "analysis",
                        "data": signal.to_dict()
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": str(e)
                    }))

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        client_subscriptions.pop(websocket, None)
        logger.info("WebSocket 연결 해제 (%d명 접속 중)", len(connected_clients))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)

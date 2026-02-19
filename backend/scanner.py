"""
마켓 스캐너 - 전체 마켓을 스캔하여 시그널 발생 코인 탐지
(비동기 병렬 + DB 영구 저장 + 점진적 확인 + 동적 심볼 + 멀티 TF)
"""
import asyncio
import logging
import uuid
from typing import List, Optional, Dict
from datetime import datetime, timezone

from exchange import AsyncBinanceClient
from analysis.signal_engine import SignalEngine
from db.candle_repo import CandleRepo
from db.signal_repo import SignalRepo
from db.track_repo import SignalTrackRepo
from data_collector import DataCollector
from signal_tracker import SignalTracker
from config import (
    MARKET_CACHE_TTL, SCAN_CONCURRENCY, ANALYSIS_CANDLE_LIMIT,
    SCAN_SYMBOLS, DYNAMIC_SYMBOLS, SCAN_TOP_N, SCALP_SYMBOLS_LIMIT,
)
from analysis.indicators import TF_CATEGORY

logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(self, client: AsyncBinanceClient,
                 candle_repo: CandleRepo,
                 signal_repo: SignalRepo,
                 track_repo: SignalTrackRepo = None):
        self.client = client
        self.engine = SignalEngine()
        self.collector = DataCollector(client, candle_repo)
        self.candle_repo = candle_repo
        self.signal_repo = signal_repo
        self.track_repo = track_repo

        # 시그널 트래커 (점진적 확인)
        self.tracker = SignalTracker(track_repo) if track_repo else None

        # in-memory 상태 (타임프레임별)
        self.latest_signals: Dict[str, List[dict]] = {}  # tf -> signals
        self.latest_transitions: List[dict] = []
        self.last_scan_time: Optional[str] = None

        # 마켓 리스트 캐시
        self._cached_markets: List[dict] = []
        self._markets_cached_at: Optional[datetime] = None

        # 동적 심볼 캐시
        self._dynamic_symbols: List[str] = []
        self._dynamic_symbols_at: Optional[datetime] = None

        # 캔들 데이터 캐시 (심볼+TF -> (df, timestamp))
        self._candle_cache: Dict[str, tuple] = {}
        self._cache_ttl = 25  # 25초 TTL

        # 시그널 안정성: 이전 스캔에서 활성이었던 시그널 유지 (TF -> {symbol: grace_count})
        self._signal_grace: Dict[str, Dict[str, int]] = {}
        self._GRACE_MAX = 2  # NEUTRAL로 바뀌어도 2회 스캔까지 유지

    async def _get_markets(self) -> List[dict]:
        """TTL 기반 마켓 리스트 캐싱"""
        now = datetime.now(timezone.utc)
        if (self._cached_markets
                and self._markets_cached_at
                and (now - self._markets_cached_at).total_seconds() < MARKET_CACHE_TTL):
            return self._cached_markets

        logger.info("바이낸스에서 마켓 리스트 갱신")
        self._cached_markets = await self.client.get_usdt_markets()
        self._markets_cached_at = now
        return self._cached_markets

    async def _get_scan_symbols(self) -> List[str]:
        """스캔 대상 심볼 결정 (고정 + 동적)"""
        if not DYNAMIC_SYMBOLS:
            return SCAN_SYMBOLS

        now = datetime.now(timezone.utc)
        # 5분 TTL로 동적 심볼 캐싱
        if (self._dynamic_symbols
                and self._dynamic_symbols_at
                and (now - self._dynamic_symbols_at).total_seconds() < 300):
            return self._dynamic_symbols

        try:
            markets = await self._get_markets()
            # 거래량 기준 이미 정렬됨, Top N 선택
            top_symbols = [m["symbol"] for m in markets[:SCAN_TOP_N]]

            # 고정 심볼은 항상 포함 (합집합)
            all_symbols = list(dict.fromkeys(SCAN_SYMBOLS + top_symbols))
            self._dynamic_symbols = all_symbols
            self._dynamic_symbols_at = now
            logger.info("동적 심볼 갱신: %d개 (고정 %d + 동적 Top %d)", len(all_symbols), len(SCAN_SYMBOLS), SCAN_TOP_N)
            return all_symbols
        except Exception as e:
            logger.warning("동적 심볼 조회 실패, 고정 리스트 사용: %s", e)
            return SCAN_SYMBOLS

    def _get_cached_candle(self, symbol: str, timeframe: str):
        """캔들 캐시 조회 (TTL 확인)"""
        key = f"{symbol}_{timeframe}"
        cached = self._candle_cache.get(key)
        if cached:
            df, ts = cached
            if (datetime.now(timezone.utc) - ts).total_seconds() < self._cache_ttl:
                return df
        return None

    _CANDLE_CACHE_MAX = 150  # 최대 캐시 엔트리 수

    def _set_cached_candle(self, symbol: str, timeframe: str, df):
        """캔들 캐시 저장 (LRU 제한)"""
        key = f"{symbol}_{timeframe}"
        # 캐시 크기 제한: 가장 오래된 항목 제거
        if len(self._candle_cache) >= self._CANDLE_CACHE_MAX and key not in self._candle_cache:
            oldest_key = min(self._candle_cache, key=lambda k: self._candle_cache[k][1])
            del self._candle_cache[oldest_key]
        self._candle_cache[key] = (df, datetime.now(timezone.utc))

    async def scan_market(self, timeframe: str = "1h") -> List[dict]:
        """
        마켓 스캔 (병렬 + DB 저장 + 점진적 확인 + 동적 심볼)
        """
        target_symbols = await self._get_scan_symbols()

        # 스캘핑 TF는 코인 수 제한 (서버 부하 방지)
        is_scalp = TF_CATEGORY.get(timeframe) == "scalp"
        if is_scalp:
            target_symbols = target_symbols[:SCALP_SYMBOLS_LIMIT]

        candle_limit = 200 if is_scalp else ANALYSIS_CANDLE_LIMIT

        logger.info(f"마켓 스캔 시작 (타임프레임: {timeframe}, {len(target_symbols)}개 코인)")
        scan_id = uuid.uuid4().hex[:12]

        # 1) 캔들 병렬 수집
        await self.collector.collect_many(
            target_symbols, timeframe,
            concurrency=SCAN_CONCURRENCY, limit=candle_limit
        )

        # 2) 병렬 분석
        semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)
        all_results: dict[str, dict] = {}
        lock = asyncio.Lock()

        async def _analyze_one(symbol: str):
            async with semaphore:
                try:
                    # 캐시 확인
                    df = self._get_cached_candle(symbol, timeframe)
                    if df is None:
                        df = await self.candle_repo.get_candles(
                            symbol, timeframe, limit=candle_limit
                        )
                        self._set_cached_candle(symbol, timeframe, df)

                    if len(df) < 50:
                        return
                    signal = self.engine.analyze(df, symbol, timeframe)
                    async with lock:
                        all_results[symbol] = signal.to_dict()
                except Exception as e:
                    logger.warning(f"{symbol} 분석 실패: {e}")

        tasks = [_analyze_one(s) for s in target_symbols]
        await asyncio.gather(*tasks)

        # 3) 시그널 트래커 처리
        all_transitions: List[dict] = []
        if self.tracker:
            for symbol in target_symbols:
                sig = all_results.get(symbol)
                if sig:
                    signal_type = sig["signal"]
                    confidence = sig["confidence"]
                    price = sig["current_price"]
                else:
                    signal_type = "NEUTRAL"
                    confidence = 0.0
                    price = 0.0

                try:
                    transitions = await self.tracker.process_scan_result(
                        symbol, timeframe, signal_type, confidence, price
                    )
                    all_transitions.extend(transitions)
                except Exception as e:
                    logger.warning(f"{symbol} 트래커 처리 실패: {e}")

        # 4) 트랙 데이터 병합
        signals = list(all_results.values())

        if self.track_repo:
            try:
                active_tracks = await self.track_repo.get_active_tracks(timeframe)
                tracks_by_symbol = {t["symbol"]: t for t in active_tracks}
                for sig in signals:
                    track = tracks_by_symbol.get(sig["symbol"])
                    if track:
                        sig["track"] = {
                            "state": track["state"],
                            "consecutive_scans": track["consecutive_scans"],
                            "first_detected_at": track["first_detected_at"],
                            "confirmed_at": track["confirmed_at"],
                            "peak_confidence": track["peak_confidence"],
                        }
            except Exception as e:
                logger.warning(f"트랙 병합 실패: {e}")

        # 5) 시그널 안정성: 이전에 활성이었던 시그널이 NEUTRAL이 되어도 grace period 유지
        prev_signals = {s["symbol"]: s for s in self.latest_signals.get(timeframe, [])}
        current_symbols = {s["symbol"] for s in signals}
        grace = self._signal_grace.get(timeframe, {})
        new_grace: Dict[str, int] = {}

        for sym, prev_sig in prev_signals.items():
            if sym not in current_symbols and prev_sig["signal"] != "NEUTRAL":
                # 이전에 활성이었는데 이번에 없음 → grace 카운터
                count = grace.get(sym, 0) + 1
                if count <= self._GRACE_MAX:
                    new_grace[sym] = count
                    # 이전 시그널을 fading으로 유지 (신뢰도 감소)
                    faded = dict(prev_sig)
                    faded["confidence"] = max(0.1, prev_sig["confidence"] * 0.7)
                    faded["_fading"] = True
                    signals.append(faded)
            elif sym in current_symbols:
                # 현재 활성 → grace 리셋
                cur = next((s for s in signals if s["symbol"] == sym), None)
                if cur and cur["signal"] != "NEUTRAL":
                    new_grace.pop(sym, None)

        self._signal_grace[timeframe] = new_grace

        # 6) 신뢰도 순 정렬
        signals.sort(key=lambda x: x["confidence"], reverse=True)

        # 7) DB 저장 (fading 시그널은 제외)
        save_signals = [s for s in signals if not s.get("_fading")]
        if save_signals:
            try:
                await self.signal_repo.save_signals_batch(save_signals, scan_id)
            except Exception as e:
                logger.error(f"시그널 저장 실패: {e}")

        # 8) in-memory 상태 갱신 (타임프레임별, 스냅샷 복사)
        self.latest_signals[timeframe] = list(signals)
        self.latest_transitions = list(all_transitions)
        self.last_scan_time = datetime.now(timezone.utc).isoformat()

        confirmed = sum(1 for s in signals if s.get("track", {}).get("state") == "CONFIRMED")
        logger.info(
            f"스캔 완료 [{timeframe}]: {len(signals)}개 시그널 ({confirmed}개 확정), "
            f"{len(all_transitions)}개 전환 (scan_id={scan_id})"
        )
        return signals

    def get_latest_signals(self, timeframe: str = "1h") -> dict:
        """최근 스캔 결과 반환 (특정 TF)"""
        signals = self.latest_signals.get(timeframe, [])
        return {
            "signals": signals,
            "last_scan_time": self.last_scan_time,
            "total_signals": len(signals),
            "timeframe": timeframe,
        }

    def get_all_timeframe_signals(self) -> dict:
        """모든 타임프레임의 최근 스캔 결과"""
        return {
            "timeframes": {
                tf: {
                    "signals": sigs,
                    "total": len(sigs),
                }
                for tf, sigs in self.latest_signals.items()
            },
            "last_scan_time": self.last_scan_time,
        }

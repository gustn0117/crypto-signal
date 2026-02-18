"""
마켓 스캐너 - 전체 마켓을 스캔하여 시그널 발생 코인 탐지
(비동기 병렬 + DB 영구 저장 + 점진적 확인)
"""
import asyncio
import logging
import uuid
from typing import List, Optional
from datetime import datetime

from exchange import AsyncBinanceClient
from analysis.signal_engine import SignalEngine
from db.candle_repo import CandleRepo
from db.signal_repo import SignalRepo
from db.track_repo import SignalTrackRepo
from data_collector import DataCollector
from signal_tracker import SignalTracker
from config import MARKET_CACHE_TTL, SCAN_CONCURRENCY, ANALYSIS_CANDLE_LIMIT, SCAN_SYMBOLS

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

        # in-memory 상태
        self.latest_signals: List[dict] = []
        self.latest_transitions: List[dict] = []
        self.last_scan_time: Optional[str] = None

        # 마켓 리스트 캐시
        self._cached_markets: List[dict] = []
        self._markets_cached_at: Optional[datetime] = None

    async def _get_markets(self) -> List[dict]:
        """TTL 기반 마켓 리스트 캐싱"""
        now = datetime.utcnow()
        if (self._cached_markets
                and self._markets_cached_at
                and (now - self._markets_cached_at).total_seconds() < MARKET_CACHE_TTL):
            logger.debug("캐시된 마켓 리스트 사용")
            return self._cached_markets

        logger.info("바이낸스에서 마켓 리스트 갱신")
        self._cached_markets = await self.client.get_usdt_markets()
        self._markets_cached_at = now
        return self._cached_markets

    async def scan_market(self, timeframe: str = "1h") -> List[dict]:
        """
        고정 코인 리스트 스캔 (병렬 + DB 저장 + 점진적 확인)
        """
        logger.info(f"마켓 스캔 시작 (타임프레임: {timeframe}, {len(SCAN_SYMBOLS)}개 코인)")
        scan_id = uuid.uuid4().hex[:12]

        # 1) 고정 코인 리스트 사용
        target_symbols = SCAN_SYMBOLS

        # 2) 캔들 병렬 수집 (500개)
        await self.collector.collect_many(
            target_symbols, timeframe,
            concurrency=SCAN_CONCURRENCY, limit=ANALYSIS_CANDLE_LIMIT
        )

        # 3) 병렬 분석 - NEUTRAL도 수집하여 트래커에 전달
        semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)
        all_results: dict[str, dict] = {}  # symbol -> signal dict
        lock = asyncio.Lock()

        async def _analyze_one(symbol: str):
            async with semaphore:
                try:
                    df = await self.candle_repo.get_candles(
                        symbol, timeframe, limit=ANALYSIS_CANDLE_LIMIT
                    )
                    if len(df) < 50:
                        return
                    signal = self.engine.analyze(df, symbol, timeframe)
                    async with lock:
                        all_results[symbol] = signal.to_dict()
                except Exception as e:
                    logger.warning(f"{symbol} 분석 실패: {e}")

        tasks = [_analyze_one(s) for s in target_symbols]
        await asyncio.gather(*tasks)

        # 4) 시그널 트래커 처리 (점진적 확인)
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

        # 5) 비NEUTRAL 시그널만 필터 + 트랙 데이터 병합
        signals = [
            sig for sig in all_results.values()
            if sig["signal"] != "NEUTRAL"
        ]

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

        # 6) 신뢰도 순 정렬
        signals.sort(key=lambda x: x["confidence"], reverse=True)

        # 7) DB 저장
        if signals:
            try:
                await self.signal_repo.save_signals_batch(signals, scan_id)
            except Exception as e:
                logger.error(f"시그널 저장 실패: {e}")

        # 8) in-memory 상태 갱신
        self.latest_signals = signals
        self.latest_transitions = all_transitions
        self.last_scan_time = datetime.utcnow().isoformat()

        confirmed = sum(1 for s in signals if s.get("track", {}).get("state") == "CONFIRMED")
        logger.info(
            f"스캔 완료: {len(signals)}개 시그널 ({confirmed}개 확정), "
            f"{len(all_transitions)}개 전환 (scan_id={scan_id})"
        )
        return signals

    def get_latest_signals(self) -> dict:
        """최근 스캔 결과 반환"""
        return {
            "signals": self.latest_signals,
            "last_scan_time": self.last_scan_time,
            "total_signals": len(self.latest_signals),
        }

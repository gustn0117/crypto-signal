"""
바이낸스 거래소 데이터 수집 모듈
ccxt를 통한 캔들 데이터, 마켓 정보 조회
"""
import ccxt
import ccxt.async_support as ccxt_async
import pandas as pd
from typing import List, Optional
from config import BINANCE_API_KEY, BINANCE_SECRET, MIN_VOLUME_USDT


class BinanceClient:
    """동기 클라이언트 (하위 호환용)"""

    def __init__(self):
        self.exchange = ccxt.binance({
            "apiKey": BINANCE_API_KEY if BINANCE_API_KEY else None,
            "secret": BINANCE_SECRET if BINANCE_SECRET else None,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

    def get_usdt_markets(self) -> List[dict]:
        """USDT 페어 마켓 목록 조회 (거래량 필터링 포함)"""
        markets = self.exchange.load_markets()
        tickers = self.exchange.fetch_tickers()

        usdt_pairs = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith("/USDT"):
                continue
            if symbol not in markets:
                continue

            quote_volume = ticker.get("quoteVolume", 0) or 0
            if quote_volume < MIN_VOLUME_USDT:
                continue

            usdt_pairs.append({
                "symbol": symbol,
                "price": ticker.get("last", 0),
                "change_24h": ticker.get("percentage", 0),
                "volume_usdt": quote_volume,
                "high_24h": ticker.get("high", 0),
                "low_24h": ticker.get("low", 0),
            })

        usdt_pairs.sort(key=lambda x: x["volume_usdt"], reverse=True)
        return usdt_pairs

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        """캔들(OHLCV) 데이터 조회"""
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def get_ticker(self, symbol: str) -> dict:
        """개별 티커 정보 조회"""
        ticker = self.exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "price": ticker.get("last", 0),
            "change_24h": ticker.get("percentage", 0),
            "volume_usdt": ticker.get("quoteVolume", 0),
            "bid": ticker.get("bid", 0),
            "ask": ticker.get("ask", 0),
        }


class AsyncBinanceClient:
    """비동기 클라이언트 (병렬 스캔 + 증분 수집용)"""

    def __init__(self):
        self.exchange = ccxt_async.binance({
            "apiKey": BINANCE_API_KEY if BINANCE_API_KEY else None,
            "secret": BINANCE_SECRET if BINANCE_SECRET else None,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        self._markets_loaded = False

    async def ensure_markets(self):
        if not self._markets_loaded:
            await self.exchange.load_markets()
            self._markets_loaded = True

    async def get_usdt_markets(self) -> List[dict]:
        """비동기 USDT 마켓 목록 조회 (선물: BTC/USDT:USDT 포맷)"""
        await self.ensure_markets()
        tickers = await self.exchange.fetch_tickers()

        usdt_pairs = []
        for symbol, ticker in tickers.items():
            # 선물 심볼: "BTC/USDT:USDT" → 기본 심볼: "BTC/USDT"
            if "/USDT" not in symbol:
                continue
            if symbol not in self.exchange.markets:
                continue

            quote_volume = ticker.get("quoteVolume", 0) or 0
            if quote_volume < MIN_VOLUME_USDT:
                continue

            # 표준 심볼로 정규화 (BTC/USDT:USDT → BTC/USDT)
            base_symbol = symbol.split(":")[0] if ":" in symbol else symbol

            usdt_pairs.append({
                "symbol": base_symbol,
                "futures_symbol": symbol,
                "price": ticker.get("last", 0),
                "change_24h": ticker.get("percentage", 0),
                "volume_usdt": quote_volume,
                "high_24h": ticker.get("high", 0),
                "low_24h": ticker.get("low", 0),
            })

        usdt_pairs.sort(key=lambda x: x["volume_usdt"], reverse=True)
        return usdt_pairs

    async def fetch_ohlcv_raw(self, symbol: str, timeframe: str = "1h",
                               since: int = None, limit: int = 200) -> list[list]:
        """ccxt raw 포맷 반환 [[ts_ms, o, h, l, c, v], ...]. since로 증분 수집."""
        await self.ensure_markets()
        return await self.exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=since, limit=limit
        )

    async def get_ohlcv(self, symbol: str, timeframe: str = "1h",
                          limit: int = 200) -> pd.DataFrame:
        """비동기 DataFrame 반환 (동기 버전과 동일 포맷)"""
        ohlcv = await self.fetch_ohlcv_raw(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    async def fetch_funding_rate(self, symbol: str) -> float | None:
        """현재 펀딩레이트 조회"""
        await self.ensure_markets()
        try:
            funding = await self.exchange.fetch_funding_rate(symbol)
            return funding.get("fundingRate")
        except Exception:
            return None

    async def fetch_open_interest_change(self, symbol: str) -> dict | None:
        """미결제약정 변화율 조회"""
        await self.ensure_markets()
        try:
            oi = await self.exchange.fetch_open_interest(symbol)
            oi_value = oi.get("openInterestAmount") or oi.get("openInterestValue", 0)
            if not oi_value:
                return None

            # 현재 가격과 24h 변화율
            ticker = await self.exchange.fetch_ticker(symbol)
            price_change = ticker.get("percentage", 0) or 0

            # OI 히스토리가 없으므로 현재값만 반환하고 스캐너에서 이전값 비교
            return {
                "current": float(oi_value),
                "previous": None,
                "price_change_pct": float(price_change),
            }
        except Exception:
            return None

    async def fetch_long_short_ratio(self, symbol: str) -> float | None:
        """Long/Short Ratio 조회 (Binance 전용 API)"""
        await self.ensure_markets()
        try:
            # ccxt의 Binance 전용 메서드
            base = symbol.split("/")[0] if "/" in symbol else symbol.replace("USDT", "")
            params = {"symbol": f"{base}USDT", "period": "5m", "limit": 1}
            response = await self.exchange.fapiPublicGetGlobalLongShortAccountRatio(params)
            if response and len(response) > 0:
                return float(response[0].get("longShortRatio", 1.0))
        except Exception:
            pass
        return None

    async def close(self):
        await self.exchange.close()

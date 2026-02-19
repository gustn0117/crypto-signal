import os
from dotenv import load_dotenv

load_dotenv()

# Binance
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

# Scanner
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 30))
MIN_VOLUME_USDT = float(os.getenv("MIN_VOLUME_USDT", 1_000_000))
SCAN_CONCURRENCY = int(os.getenv("SCAN_CONCURRENCY", 15))

# 동적 심볼 스캔 설정 (false → 고정 10개만 스캔)
DYNAMIC_SYMBOLS = os.getenv("DYNAMIC_SYMBOLS", "false").lower() == "true"
SCAN_TOP_N = int(os.getenv("SCAN_TOP_N", 0))

# 거래량 급증 감지 설정
VOLUME_SPIKE_THRESHOLD = float(os.getenv("VOLUME_SPIKE_THRESHOLD", "2.0"))  # 거래량 급증 기준 배율
VOLUME_SPIKE_PRIORITY_COUNT = int(os.getenv("VOLUME_SPIKE_PRIORITY_COUNT", "5"))  # 급증 코인 최대 추가 수

# 고정 스캔 대상 (항상 포함되는 코어 코인)
SCAN_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "TRX/USDT",
    "AVAX/USDT",
    "MATIC/USDT",
    "LINK/USDT",
]

# 멀티 타임프레임 스캔 설정 (1m/5m 스캘핑 포함)
SCAN_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]

# 스캘핑 설정
SCALP_SYMBOLS_LIMIT = int(os.getenv("SCALP_SYMBOLS_LIMIT", "10"))  # 1m/5m은 상위 N개만 스캔

# Supabase (PostgreSQL)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://api.hsweb.pics")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UiLCJpYXQiOjE2NDE3NjkyMDAsImV4cCI6MTc5OTUzNTYwMH0.xTNteRFphY3F9W2PPWOwCQ9PDXD05ySRqkJu5d4Cej0",
)
SUPABASE_SCHEMA = "coin"
PG_META_URL = os.getenv("PG_META_URL", "https://api.hsweb.pics/pg/query")

# Market cache TTL (seconds)
MARKET_CACHE_TTL = int(os.getenv("MARKET_CACHE_TTL", 300))

# 지원 타임프레임
TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# 기본 타임프레임
DEFAULT_TIMEFRAME = "1h"

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")

# 로깅
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")

# 멀티 타임프레임 매핑 (현재 TF → 상위 TF)
HIGHER_TF_MAP = {
    "1m": "5m",
    "5m": "15m",
    "15m": "1h",
    "30m": "4h",
    "1h": "4h",
    "4h": "1d",
    "1d": "1d",
}

# 분석 캔들 수 (깊은 분석용 - 백필/배치 분석)
ANALYSIS_CANDLE_LIMIT = int(os.getenv("ANALYSIS_CANDLE_LIMIT", "2000"))

# 실시간 분석 캔들 수 (API 응답 속도 최적화)
REALTIME_CANDLE_LIMIT = int(os.getenv("REALTIME_CANDLE_LIMIT", "500"))
REALTIME_HIGHER_TF_LIMIT = int(os.getenv("REALTIME_HIGHER_TF_LIMIT", "200"))

# 히스토리 백필 설정 (대용량 스토리지 활용)
BACKFILL_DAYS = int(os.getenv("BACKFILL_DAYS", "1825"))  # 5년치
BACKFILL_DAYS_1M = int(os.getenv("BACKFILL_DAYS_1M", "7"))  # 1m은 7일치만
BACKFILL_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
BACKFILL_BATCH_SIZE = 1000  # 바이낸스 API 1회 최대 캔들 수
BACKFILL_CONCURRENCY = 5  # 동시 심볼 수 (넉넉한 트래픽 활용)

# 알림 설정
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "true").lower() == "true"
ALERT_MIN_CONFIDENCE = float(os.getenv("ALERT_MIN_CONFIDENCE", "0.5"))
ALERT_SIGNAL_TYPES = os.getenv("ALERT_SIGNAL_TYPES", "STRONG_LONG,STRONG_SHORT,LONG,SHORT").split(",")
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "30"))

# 타임프레임별 알림 쿨다운 (분)
ALERT_COOLDOWN_MAP = {
    "1m": 3, "5m": 5, "15m": 15, "1h": 30, "4h": 60, "1d": 120,
}

# 타임프레임별 예측 기본 호라이즌 (캔들 수)
DEFAULT_HORIZON_CANDLES = {
    "1m": 60, "5m": 36, "15m": 24, "30m": 24, "1h": 24, "4h": 12, "1d": 7,
}

# ─── Telegram/Discord 알림 ──────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# ─── 감성 분석 ──────────────────────────────────────────
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")

# ─── 자동매매 ────────────────────────────────────────────
AUTO_TRADE_ENABLED = os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true"
AUTO_TRADE_MAX_POSITIONS = int(os.getenv("AUTO_TRADE_MAX_POSITIONS", "3"))
AUTO_TRADE_MAX_PCT = float(os.getenv("AUTO_TRADE_MAX_PCT", "10.0"))

# ─── Bybit 멀티 거래소 ──────────────────────────────────
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_SECRET = os.getenv("BYBIT_SECRET", "")

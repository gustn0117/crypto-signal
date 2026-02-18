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
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", 60))
MIN_VOLUME_USDT = float(os.getenv("MIN_VOLUME_USDT", 1_000_000))
SCAN_CONCURRENCY = int(os.getenv("SCAN_CONCURRENCY", 10))

# 고정 스캔 대상 (안정적 대형 코인 10개)
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

# 분석 캔들 수 (깊은 분석용)
ANALYSIS_CANDLE_LIMIT = int(os.getenv("ANALYSIS_CANDLE_LIMIT", "500"))

# 알림 설정
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "true").lower() == "true"
ALERT_MIN_CONFIDENCE = float(os.getenv("ALERT_MIN_CONFIDENCE", "0.5"))
ALERT_SIGNAL_TYPES = os.getenv("ALERT_SIGNAL_TYPES", "STRONG_LONG,STRONG_SHORT,LONG,SHORT").split(",")
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "30"))

"""
Supabase (PostgreSQL) 스키마 설정 스크립트
coin 스키마에 테이블, 인덱스, RPC 함수를 생성합니다.

사용법: python scripts/setup_supabase.py
"""
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import PG_META_URL, SUPABASE_KEY

HEADERS = {
    "Content-Type": "application/json",
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

# ── 테이블 생성 ──────────────────────────────────────────

TABLES_SQL = """
-- ohlcv
CREATE TABLE IF NOT EXISTS coin.ohlcv (
    symbol        TEXT    NOT NULL,
    timeframe     TEXT    NOT NULL,
    timestamp_ms  BIGINT  NOT NULL,
    open          DOUBLE PRECISION NOT NULL,
    high          DOUBLE PRECISION NOT NULL,
    low           DOUBLE PRECISION NOT NULL,
    close         DOUBLE PRECISION NOT NULL,
    volume        DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp_ms)
);

-- signals
CREATE TABLE IF NOT EXISTS coin.signals (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    signal          TEXT NOT NULL,
    confidence      DOUBLE PRECISION NOT NULL,
    current_price   DOUBLE PRECISION NOT NULL,
    indicators      JSONB NOT NULL,
    candle_patterns JSONB NOT NULL,
    chart_patterns  JSONB DEFAULT '[]'::jsonb,
    volume_signals  JSONB NOT NULL,
    summary         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    scan_id         TEXT DEFAULT NULL
);

-- signal_tracks
CREATE TABLE IF NOT EXISTS coin.signal_tracks (
    id                BIGSERIAL PRIMARY KEY,
    symbol            TEXT NOT NULL,
    timeframe         TEXT NOT NULL,
    direction         TEXT NOT NULL,
    state             TEXT NOT NULL DEFAULT 'FORMING',
    current_signal    TEXT NOT NULL,
    confidence        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    peak_confidence   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    consecutive_scans INTEGER NOT NULL DEFAULT 1,
    weak_scans        INTEGER NOT NULL DEFAULT 0,
    first_detected_at TEXT NOT NULL,
    last_updated_at   TEXT NOT NULL,
    confirmed_at      TEXT DEFAULT NULL,
    first_price       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    current_price     DOUBLE PRECISION NOT NULL DEFAULT 0.0
);

-- signal_transitions
CREATE TABLE IF NOT EXISTS coin.signal_transitions (
    id              BIGSERIAL PRIMARY KEY,
    track_id        BIGINT NOT NULL,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    from_state      TEXT,
    to_state        TEXT NOT NULL,
    direction       TEXT NOT NULL,
    confidence      DOUBLE PRECISION NOT NULL,
    current_price   DOUBLE PRECISION NOT NULL,
    created_at      TEXT NOT NULL
);

-- predictions
CREATE TABLE IF NOT EXISTS coin.predictions (
    id                     BIGSERIAL PRIMARY KEY,
    symbol                 TEXT NOT NULL,
    timeframe              TEXT NOT NULL,
    signal_direction       TEXT NOT NULL,
    confidence             DOUBLE PRECISION NOT NULL,
    entry_price            DOUBLE PRECISION NOT NULL,
    stop_loss              DOUBLE PRECISION NOT NULL,
    take_profit_1          DOUBLE PRECISION NOT NULL,
    take_profit_2          DOUBLE PRECISION NOT NULL,
    take_profit_3          DOUBLE PRECISION NOT NULL,
    atr                    DOUBLE PRECISION NOT NULL,
    atr_percent            DOUBLE PRECISION NOT NULL,
    predicted_path         JSONB NOT NULL,
    upper_bound_path       JSONB NOT NULL,
    lower_bound_path       JSONB NOT NULL,
    horizon_candles        INTEGER NOT NULL DEFAULT 24,
    created_at             TEXT NOT NULL,
    status                 TEXT NOT NULL DEFAULT 'ACTIVE',
    verified_at            TEXT DEFAULT NULL,
    actual_path            JSONB DEFAULT NULL,
    result                 TEXT DEFAULT NULL,
    accuracy_score         DOUBLE PRECISION DEFAULT NULL,
    max_favorable          DOUBLE PRECISION DEFAULT NULL,
    max_adverse            DOUBLE PRECISION DEFAULT NULL,
    final_price            DOUBLE PRECISION DEFAULT NULL,
    notes                  TEXT DEFAULT NULL,
    auto_generated         INTEGER DEFAULT 0,
    regime                 TEXT DEFAULT NULL,
    num_simulations        INTEGER DEFAULT 200,
    calibration_factor     DOUBLE PRECISION DEFAULT 1.0,
    progress_pnl_pct       DOUBLE PRECISION DEFAULT NULL,
    progress_rr_current    DOUBLE PRECISION DEFAULT NULL,
    progress_time_pct      DOUBLE PRECISION DEFAULT NULL,
    progress_path_accuracy DOUBLE PRECISION DEFAULT NULL,
    progress_updated_at    TEXT DEFAULT NULL
);
-- indicator_accuracy (자기학습)
CREATE TABLE IF NOT EXISTS coin.indicator_accuracy (
    id              BIGSERIAL PRIMARY KEY,
    indicator_name  TEXT NOT NULL,
    category        TEXT NOT NULL,
    total_count     INTEGER NOT NULL DEFAULT 0,
    correct_count   INTEGER NOT NULL DEFAULT 0,
    accuracy        DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    last_updated    TEXT NOT NULL
);

-- adaptive_weights (자기학습)
CREATE TABLE IF NOT EXISTS coin.adaptive_weights (
    id              BIGSERIAL PRIMARY KEY,
    weights         JSONB NOT NULL,
    sample_count    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

-- paper_accounts (모의 트레이딩 계좌)
CREATE TABLE IF NOT EXISTS coin.paper_accounts (
    id                BIGSERIAL PRIMARY KEY,
    name              TEXT NOT NULL DEFAULT 'Default',
    initial_balance   DOUBLE PRECISION NOT NULL DEFAULT 10000.0,
    balance           DOUBLE PRECISION NOT NULL DEFAULT 10000.0,
    total_pnl         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    total_trades      INTEGER NOT NULL DEFAULT 0,
    winning_trades    INTEGER NOT NULL DEFAULT 0,
    losing_trades     INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- paper_trades (모의 트레이딩 거래)
CREATE TABLE IF NOT EXISTS coin.paper_trades (
    id                  BIGSERIAL PRIMARY KEY,
    account_id          BIGINT NOT NULL,
    symbol              TEXT NOT NULL,
    direction           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'OPEN',
    entry_price         DOUBLE PRECISION NOT NULL,
    current_price       DOUBLE PRECISION DEFAULT NULL,
    close_price         DOUBLE PRECISION DEFAULT NULL,
    quantity            DOUBLE PRECISION NOT NULL,
    position_usdt       DOUBLE PRECISION NOT NULL,
    stop_loss           DOUBLE PRECISION DEFAULT NULL,
    take_profit_1       DOUBLE PRECISION DEFAULT NULL,
    take_profit_2       DOUBLE PRECISION DEFAULT NULL,
    take_profit_3       DOUBLE PRECISION DEFAULT NULL,
    unrealized_pnl      DOUBLE PRECISION DEFAULT 0.0,
    unrealized_pnl_pct  DOUBLE PRECISION DEFAULT 0.0,
    realized_pnl        DOUBLE PRECISION DEFAULT NULL,
    realized_pnl_pct    DOUBLE PRECISION DEFAULT NULL,
    close_reason        TEXT DEFAULT NULL,
    opened_at           TEXT NOT NULL,
    closed_at           TEXT DEFAULT NULL,
    updated_at          TEXT NOT NULL
);
"""

# ── 인덱스 생성 ──────────────────────────────────────────

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_ohlcv_lookup
    ON coin.ohlcv (symbol, timeframe, timestamp_ms DESC);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_time
    ON coin.signals (symbol, timeframe, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_created
    ON coin.signals (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tracks_active
    ON coin.signal_tracks (state, timeframe);

CREATE INDEX IF NOT EXISTS idx_tracks_symbol
    ON coin.signal_tracks (symbol, timeframe, state);

CREATE INDEX IF NOT EXISTS idx_transitions_created
    ON coin.signal_transitions (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_symbol
    ON coin.predictions (symbol, timeframe, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_status
    ON coin.predictions (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_trades_status
    ON coin.paper_trades (account_id, status);

CREATE INDEX IF NOT EXISTS idx_paper_trades_history
    ON coin.paper_trades (account_id, closed_at DESC);
"""

# ── RPC 함수 ─────────────────────────────────────────────

RPC_ACCURACY_STATS = """
CREATE OR REPLACE FUNCTION coin.get_accuracy_stats(p_symbol TEXT DEFAULT NULL)
RETURNS JSON AS $$
  SELECT json_build_object(
    'total_predictions', COUNT(*)::int,
    'avg_accuracy_score', ROUND(COALESCE(AVG(accuracy_score), 0)::numeric, 3),
    'tp_hit_rate', CASE WHEN COUNT(*) > 0
      THEN ROUND((SUM(CASE WHEN result IN ('HIT_TP1','HIT_TP2','HIT_TP3') THEN 1 ELSE 0 END)::numeric / COUNT(*)), 3)
      ELSE 0 END,
    'sl_hit_rate', CASE WHEN COUNT(*) > 0
      THEN ROUND((SUM(CASE WHEN result = 'HIT_SL' THEN 1 ELSE 0 END)::numeric / COUNT(*)), 3)
      ELSE 0 END,
    'avg_max_favorable_excursion', ROUND(COALESCE(AVG(max_favorable), 0)::numeric, 3),
    'avg_max_adverse_excursion', ROUND(COALESCE(AVG(max_adverse), 0)::numeric, 3)
  )
  FROM coin.predictions
  WHERE status = 'VERIFIED'
    AND (p_symbol IS NULL OR symbol = p_symbol);
$$ LANGUAGE sql STABLE;
"""

RPC_GLOBAL_STATS = """
CREATE OR REPLACE FUNCTION coin.get_global_prediction_stats()
RETURNS JSON AS $$
  WITH base AS (
    SELECT
      COUNT(*)::int as total,
      SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END)::int as active,
      AVG(CASE WHEN status = 'VERIFIED' THEN accuracy_score END) as avg_acc,
      SUM(CASE WHEN status = 'VERIFIED' AND result IN ('HIT_TP1','HIT_TP2','HIT_TP3') THEN 1 ELSE 0 END)::int as wins,
      SUM(CASE WHEN status = 'VERIFIED' THEN 1 ELSE 0 END)::int as verified
    FROM coin.predictions
  ),
  leaderboard AS (
    SELECT COALESCE(json_agg(row_to_json(lb)), '[]'::json) as data FROM (
      SELECT symbol,
             ROUND(AVG(accuracy_score)::numeric, 3) as avg_acc,
             SUM(CASE WHEN result IN ('HIT_TP1','HIT_TP2','HIT_TP3') THEN 1 ELSE 0 END)::int as wins
      FROM coin.predictions WHERE status = 'VERIFIED'
      GROUP BY symbol HAVING COUNT(*) >= 2
      ORDER BY AVG(accuracy_score) DESC LIMIT 10
    ) lb
  ),
  recent AS (
    SELECT COALESCE(json_agg(row_to_json(rc)), '[]'::json) as data FROM (
      SELECT symbol, result, ROUND(COALESCE(accuracy_score, 0)::numeric, 3) as accuracy_score
      FROM coin.predictions WHERE status = 'VERIFIED'
      ORDER BY verified_at DESC LIMIT 10
    ) rc
  )
  SELECT json_build_object(
    'total_predictions', COALESCE(base.total, 0),
    'active_predictions', COALESCE(base.active, 0),
    'avg_accuracy', ROUND(COALESCE(base.avg_acc, 0)::numeric, 3),
    'win_rate', CASE WHEN COALESCE(base.verified, 0) > 0
      THEN ROUND((base.wins::numeric / base.verified), 3) ELSE 0 END,
    'leaderboard', leaderboard.data,
    'recent_results', recent.data
  ) FROM base, leaderboard, recent;
$$ LANGUAGE sql STABLE;
"""

RPC_CLEANUP_TRACKS = """
CREATE OR REPLACE FUNCTION coin.cleanup_expired_tracks(p_hours INTEGER DEFAULT 48)
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER;
  cutoff TEXT;
BEGIN
  cutoff := to_char(NOW() AT TIME ZONE 'UTC' - (p_hours || ' hours')::interval, 'YYYY-MM-DD"T"HH24:MI:SS');

  DELETE FROM coin.signal_transitions
    WHERE track_id IN (
      SELECT id FROM coin.signal_tracks
      WHERE state = 'EXPIRED' AND last_updated_at < cutoff
    );

  DELETE FROM coin.signal_tracks
    WHERE state = 'EXPIRED' AND last_updated_at < cutoff;

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
"""

# ── PostgREST 스키마 등록 ────────────────────────────────

GRANT_SQL = """
GRANT USAGE ON SCHEMA coin TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA coin TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA coin TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA coin TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA coin GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA coin GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
"""

REGISTER_SCHEMA_SQL = """
ALTER ROLE authenticator SET pgrst.db_schemas = 'haram, coinhost, maeum, soul, public, storage, graphql_public, coin';
NOTIFY pgrst, 'reload config';
"""

# ── 마이그레이션 SQL (기존 테이블 업데이트) ──────────────

MIGRATION_SQL = """
-- signals 테이블에 chart_patterns 컬럼 추가 (없으면)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'coin' AND table_name = 'signals' AND column_name = 'chart_patterns'
    ) THEN
        ALTER TABLE coin.signals ADD COLUMN chart_patterns JSONB DEFAULT '[]'::jsonb;
    END IF;
END $$;
"""


def run_sql(client: httpx.Client, sql: str, label: str):
    """pg-meta API로 SQL 실행"""
    resp = client.post(
        PG_META_URL,
        headers=HEADERS,
        json={"query": sql},
    )
    if resp.status_code >= 400:
        print(f"  [FAIL] {label}: {resp.status_code} - {resp.text}")
        return False
    print(f"  [OK] {label}")
    return True


def main():
    print("=== Supabase 스키마 설정 시작 ===\n")

    with httpx.Client(timeout=30) as client:
        # 0. 스키마 생성
        print("[Phase 0] coin 스키마 생성")
        run_sql(client, "CREATE SCHEMA IF NOT EXISTS coin;", "coin 스키마")

        # 1. 테이블 생성
        print("\n[Phase 1] 테이블 생성")
        run_sql(client, TABLES_SQL, "7개 테이블")

        # 1-b. 마이그레이션 (기존 테이블 컬럼 추가)
        print("\n[Phase 1-b] 마이그레이션")
        run_sql(client, MIGRATION_SQL, "signals.chart_patterns 컬럼 추가")

        # 2. 인덱스 생성
        print("\n[Phase 2] 인덱스 생성")
        run_sql(client, INDEXES_SQL, "8개 인덱스")

        # 3. 권한 부여
        print("\n[Phase 3] 권한 부여")
        run_sql(client, GRANT_SQL, "GRANT (anon, authenticated, service_role)")

        # 4. RPC 함수
        print("\n[Phase 4] RPC 함수 생성")
        run_sql(client, RPC_ACCURACY_STATS, "get_accuracy_stats")
        run_sql(client, RPC_GLOBAL_STATS, "get_global_prediction_stats")
        run_sql(client, RPC_CLEANUP_TRACKS, "cleanup_expired_tracks")

        # 5. PostgREST 스키마 등록
        print("\n[Phase 5] PostgREST 스키마 등록")
        run_sql(client, REGISTER_SCHEMA_SQL, "authenticator role + notify")

    print("\n=== 설정 완료 ===")
    print(">>> 이제 'docker compose restart rest'를 실행하세요.")


if __name__ == "__main__":
    main()

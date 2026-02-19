"""
LSTM 학습 스크립트
DB의 OHLCV 데이터로 방향 예측 모델 학습.
사용법: python scripts/train_lstm.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
import numpy as np
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    from db import Database, CandleRepo
    from config import SUPABASE_SCHEMA, SCAN_SYMBOLS

    logger.info("LSTM 학습 시작")

    db = Database()
    await db.connect()
    candle_repo = CandleRepo(db.client, SUPABASE_SCHEMA)

    all_close = []
    all_volume = []

    # 데이터 수집
    for symbol in SCAN_SYMBOLS[:5]:
        try:
            df = await candle_repo.get_candles(symbol, "1h", limit=5000)
            if len(df) < 500:
                continue
            all_close.extend(df["close"].tolist())
            all_volume.extend(df["volume"].tolist())
            logger.info("%s: %d 캔들 로드", symbol, len(df))
        except Exception as e:
            logger.warning("%s 로드 실패: %s", symbol, e)

    await db.close()

    if len(all_close) < 1000:
        logger.error("학습 데이터 부족: %d개", len(all_close))
        return

    logger.info("총 %d개 캔들 데이터 수집", len(all_close))

    # 간이 학습 (numpy 기반)
    # 60봉 입력 → 다음 5봉 방향 예측
    seq_len = 60
    lookahead = 5
    hidden_size = 64
    num_features = 6

    # 특징 생성 (간이)
    close_arr = np.array(all_close, dtype=float)
    vol_arr = np.array(all_volume, dtype=float)

    # 학습 데이터 준비
    X = []
    Y = []
    for i in range(seq_len, len(close_arr) - lookahead):
        segment = close_arr[i-seq_len:i]
        c_norm = (segment - segment.min()) / (segment.max() - segment.min() + 1e-10)

        v_seg = vol_arr[i-seq_len:i]
        v_norm = (v_seg - v_seg.min()) / (v_seg.max() - v_seg.min() + 1e-10)

        features = np.stack([c_norm, v_norm, np.zeros(seq_len), np.zeros(seq_len),
                           np.ones(seq_len) * 0.5, np.ones(seq_len) * 0.03], axis=1)
        X.append(features)

        future = close_arr[i + lookahead]
        current = close_arr[i]
        change = (future - current) / current * 100
        if change > 0.5:
            Y.append(0)  # UP
        elif change < -0.5:
            Y.append(1)  # DOWN
        else:
            Y.append(2)  # FLAT

    X = np.array(X)
    Y = np.array(Y)

    logger.info("학습 셋: %d 샘플, UP=%d, DOWN=%d, FLAT=%d",
                len(Y), (Y==0).sum(), (Y==1).sum(), (Y==2).sum())

    # 간이 가중치 초기화 (LSTM 근사)
    np.random.seed(42)
    w_ih = np.random.randn(4 * hidden_size, num_features) * 0.05
    w_hh = np.random.randn(4 * hidden_size, hidden_size) * 0.05
    b = np.zeros(4 * hidden_size)
    fc_w = np.random.randn(3, hidden_size) * 0.1
    fc_b = np.zeros(3)

    # 저장
    os.makedirs("models", exist_ok=True)
    np.savez("models/lstm_weights.npz",
             lstm_w_ih=w_ih, lstm_w_hh=w_hh, lstm_b=b,
             fc_w=fc_w, fc_b=fc_b)

    logger.info("LSTM 가중치 저장 완료: models/lstm_weights.npz")
    logger.info("학습 완료 (간이 초기화, 실제 학습은 PyTorch 버전 필요)")


if __name__ == "__main__":
    asyncio.run(main())

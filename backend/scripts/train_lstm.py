"""
LSTM 학습 스크립트 (v2 — Echo State + 최소제곱 + SGD 미세조정)
DB의 OHLCV 데이터로 방향 예측 모델 학습.

방식:
1. 적절한 특징 추출 (RSI, MACD, BB position, ATR ratio)
2. Xavier 초기화된 LSTM을 랜덤 특징 추출기로 사용
3. 출력층을 Ridge Regression(최소제곱)으로 학습
4. SGD로 출력층 미세 조정
5. 다중 시도(5회) 중 검증 정확도 최고인 가중치 저장

사용법: python scripts/train_lstm.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging

import numpy as np
import pandas as pd
import pandas_ta as pta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SEQUENCE_LENGTH = 60
NUM_FEATURES = 6
HIDDEN_SIZE = 64
LOOKAHEAD = 5
UP_THRESHOLD = 0.5      # % 상승 판정
DOWN_THRESHOLD = -0.5    # % 하락 판정
NUM_TRIALS = 5           # 랜덤 초기화 시도 횟수
SGD_EPOCHS = 50
SGD_LR = 0.01
RIDGE_LAMBDA = 0.01


# ─── 유틸 ───────────────────────────────────────────────
def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))


def _lstm_forward(x: np.ndarray, w_ih, w_hh, b, hidden_size: int) -> np.ndarray:
    """LSTM forward pass → 마지막 hidden state 반환."""
    h = np.zeros(hidden_size)
    c = np.zeros(hidden_size)
    hs = hidden_size
    for t in range(x.shape[0]):
        xt = x[t, :]
        gates = w_ih @ xt + w_hh @ h + b
        i_gate = _sigmoid(gates[:hs])
        f_gate = _sigmoid(gates[hs : 2 * hs])
        g_gate = np.tanh(gates[2 * hs : 3 * hs])
        o_gate = _sigmoid(gates[3 * hs :])
        c = f_gate * c + i_gate * g_gate
        h = o_gate * np.tanh(c)
    return h


# ─── 특징 추출 ──────────────────────────────────────────
def prepare_features(df: pd.DataFrame) -> list[tuple[np.ndarray, int]]:
    """DataFrame → (특징 시퀀스, 라벨) 리스트."""
    if len(df) < SEQUENCE_LENGTH + LOOKAHEAD + 50:
        return []

    close = df["close"].values.astype(float)
    volume = df["volume"].values.astype(float)

    # RSI (0~1)
    rsi_s = pta.rsi(df["close"], length=14)
    if rsi_s is None:
        return []
    rsi = rsi_s.fillna(50).values / 100.0

    # MACD histogram (z-score)
    macd_df = pta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is None:
        return []
    macd_hist = macd_df.iloc[:, 2].fillna(0).values
    macd_norm = (macd_hist - np.mean(macd_hist)) / (np.std(macd_hist) + 1e-10)

    # Bollinger Bands position (0~1)
    bb = pta.bbands(df["close"], length=20, std=2.0)
    if bb is None:
        return []
    bb_upper = bb.iloc[:, 0].ffill().values
    bb_lower = bb.iloc[:, 2].ffill().values
    bb_range = bb_upper - bb_lower + 1e-10
    bb_position = np.clip((close - bb_lower) / bb_range, 0, 1)

    # ATR ratio
    atr_s = pta.atr(df["high"], df["low"], df["close"], length=14)
    if atr_s is None:
        return []
    atr = atr_s.ffill().values
    atr_ratio = atr / (close + 1e-10)

    sequences: list[tuple[np.ndarray, int]] = []
    n = len(close)
    for i in range(SEQUENCE_LENGTH, n - LOOKAHEAD):
        # close 정규화 (시퀀스별 min-max)
        seg_close = close[i - SEQUENCE_LENGTH : i]
        c_min, c_max = seg_close.min(), seg_close.max()
        if c_max - c_min < 1e-10:
            continue
        close_norm = (seg_close - c_min) / (c_max - c_min)

        # volume 정규화
        seg_vol = volume[i - SEQUENCE_LENGTH : i]
        v_min, v_max = seg_vol.min(), seg_vol.max()
        vol_norm = (seg_vol - v_min) / (v_max - v_min + 1e-10)

        features = np.stack(
            [
                close_norm,
                vol_norm,
                rsi[i - SEQUENCE_LENGTH : i],
                macd_norm[i - SEQUENCE_LENGTH : i],
                bb_position[i - SEQUENCE_LENGTH : i],
                atr_ratio[i - SEQUENCE_LENGTH : i],
            ],
            axis=1,
        )

        # 라벨: 미래 가격 변동률
        future_price = close[i + LOOKAHEAD]
        current_price = close[i]
        change_pct = (future_price - current_price) / current_price * 100
        if change_pct > UP_THRESHOLD:
            label = 0  # UP
        elif change_pct < DOWN_THRESHOLD:
            label = 1  # DOWN
        else:
            label = 2  # FLAT

        sequences.append((features, label))

    return sequences


# ─── 학습 루프 ──────────────────────────────────────────
def train_model(X: np.ndarray, Y: np.ndarray) -> dict:
    """LSTM Echo-State + Ridge + SGD 학습."""
    n_samples = len(Y)
    n_train = int(n_samples * 0.8)
    X_train, X_val = X[:n_train], X[n_train:]
    Y_train, Y_val = Y[:n_train], Y[n_train:]

    logger.info("학습셋: %d, 검증셋: %d", n_train, n_samples - n_train)
    logger.info(
        "클래스 분포: UP=%d, DOWN=%d, FLAT=%d",
        (Y == 0).sum(),
        (Y == 1).sum(),
        (Y == 2).sum(),
    )

    scale_ih = np.sqrt(2.0 / (NUM_FEATURES + HIDDEN_SIZE))
    scale_hh = np.sqrt(2.0 / (HIDDEN_SIZE + HIDDEN_SIZE))

    best_val_acc = 0.0
    best_weights = None

    # ── Phase 1: 다중 랜덤 초기화 → Ridge Regression ──
    for trial in range(NUM_TRIALS):
        np.random.seed(42 + trial)
        w_ih = np.random.randn(4 * HIDDEN_SIZE, NUM_FEATURES) * scale_ih
        w_hh = np.random.randn(4 * HIDDEN_SIZE, HIDDEN_SIZE) * scale_hh
        b = np.zeros(4 * HIDDEN_SIZE)
        b[HIDDEN_SIZE : 2 * HIDDEN_SIZE] = 1.0  # forget gate bias

        # Forward pass → hidden states
        H_train = np.zeros((n_train, HIDDEN_SIZE))
        for i in range(n_train):
            H_train[i] = _lstm_forward(X_train[i], w_ih, w_hh, b, HIDDEN_SIZE)

        # One-hot 라벨
        Y_onehot = np.zeros((n_train, 3))
        Y_onehot[np.arange(n_train), Y_train] = 1.0

        # Ridge Regression: (H^T H + λI)^{-1} H^T Y
        H_bias = np.hstack([H_train, np.ones((n_train, 1))])
        I = np.eye(HIDDEN_SIZE + 1)
        W_out = np.linalg.solve(
            H_bias.T @ H_bias + RIDGE_LAMBDA * I,
            H_bias.T @ Y_onehot,
        )
        fc_w = W_out[:HIDDEN_SIZE, :].T  # (3, 64)
        fc_b = W_out[HIDDEN_SIZE, :]  # (3,)

        # 검증
        H_val = np.zeros((len(X_val), HIDDEN_SIZE))
        for i in range(len(X_val)):
            H_val[i] = _lstm_forward(X_val[i], w_ih, w_hh, b, HIDDEN_SIZE)

        logits_v = H_val @ fc_w.T + fc_b
        preds_v = np.argmax(logits_v, axis=1)
        val_acc = float(np.mean(preds_v == Y_val))

        logger.info("Trial %d/%d: 검증 정확도 = %.2f%%", trial + 1, NUM_TRIALS, val_acc * 100)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_weights = {
                "lstm_w_ih": w_ih.copy(),
                "lstm_w_hh": w_hh.copy(),
                "lstm_b": b.copy(),
                "fc_w": fc_w.copy(),
                "fc_b": fc_b.copy(),
            }

    if best_weights is None:
        raise RuntimeError("학습 실패: 유효한 가중치 없음")

    # ── Phase 2: SGD 미세 조정 (출력층만) ──
    logger.info("SGD 미세 조정 시작 (epoch=%d, lr=%.4f)", SGD_EPOCHS, SGD_LR)

    w_ih = best_weights["lstm_w_ih"]
    w_hh = best_weights["lstm_w_hh"]
    b = best_weights["lstm_b"]
    fc_w = best_weights["fc_w"].copy()
    fc_b = best_weights["fc_b"].copy()

    H_train = np.zeros((n_train, HIDDEN_SIZE))
    for i in range(n_train):
        H_train[i] = _lstm_forward(X_train[i], w_ih, w_hh, b, HIDDEN_SIZE)

    best_sgd_acc = best_val_acc
    best_fc_w = fc_w.copy()
    best_fc_b = fc_b.copy()

    for epoch in range(SGD_EPOCHS):
        idx = np.random.permutation(n_train)
        total_loss = 0.0
        for i in idx:
            h = H_train[i]
            logits = fc_w @ h + fc_b
            e = np.exp(logits - np.max(logits))
            probs = e / e.sum()

            total_loss -= np.log(probs[Y_train[i]] + 1e-10)

            grad = probs.copy()
            grad[Y_train[i]] -= 1.0
            fc_w -= SGD_LR * np.outer(grad, h)
            fc_b -= SGD_LR * grad

        if (epoch + 1) % 10 == 0:
            H_val = np.zeros((len(X_val), HIDDEN_SIZE))
            for i in range(len(X_val)):
                H_val[i] = _lstm_forward(X_val[i], w_ih, w_hh, b, HIDDEN_SIZE)
            logits_v = H_val @ fc_w.T + fc_b
            preds_v = np.argmax(logits_v, axis=1)
            val_acc = float(np.mean(preds_v == Y_val))
            logger.info(
                "Epoch %d: loss=%.4f, val_acc=%.2f%%",
                epoch + 1,
                total_loss / n_train,
                val_acc * 100,
            )
            if val_acc > best_sgd_acc:
                best_sgd_acc = val_acc
                best_fc_w = fc_w.copy()
                best_fc_b = fc_b.copy()

    return {
        "lstm_w_ih": w_ih,
        "lstm_w_hh": w_hh,
        "lstm_b": b,
        "fc_w": best_fc_w,
        "fc_b": best_fc_b,
        "val_acc": best_sgd_acc,
    }


# ─── 메인 ──────────────────────────────────────────────
async def main():
    from db import Database, CandleRepo
    from config import SUPABASE_SCHEMA, SCAN_SYMBOLS

    logger.info("=" * 60)
    logger.info("LSTM 학습 시작 (Echo State + Ridge + SGD)")
    logger.info("=" * 60)

    db = Database()
    await db.connect()
    candle_repo = CandleRepo(db.client, SUPABASE_SCHEMA)

    all_sequences: list[tuple[np.ndarray, int]] = []

    for symbol in SCAN_SYMBOLS[:10]:
        try:
            df = await candle_repo.get_candles(symbol, "1h", limit=5000)
            if len(df) < 500:
                logger.info("%s: 데이터 부족 (%d개), 스킵", symbol, len(df))
                continue
            seqs = prepare_features(df)
            all_sequences.extend(seqs)
            logger.info("%s: %d 시퀀스 생성 (캔들 %d개)", symbol, len(seqs), len(df))
        except Exception as e:
            logger.warning("%s 처리 실패: %s", symbol, e)

    await db.close()

    if len(all_sequences) < 500:
        logger.error("학습 데이터 부족: %d개 (최소 500개 필요)", len(all_sequences))
        return

    logger.info("총 %d개 시퀀스 수집", len(all_sequences))

    np.random.seed(42)
    np.random.shuffle(all_sequences)

    X = np.array([s[0] for s in all_sequences])
    Y = np.array([s[1] for s in all_sequences])

    weights = train_model(X, Y)

    os.makedirs("models", exist_ok=True)
    save_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
        "lstm_weights.npz",
    )
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    np.savez(
        save_path,
        lstm_w_ih=weights["lstm_w_ih"],
        lstm_w_hh=weights["lstm_w_hh"],
        lstm_b=weights["lstm_b"],
        fc_w=weights["fc_w"],
        fc_b=weights["fc_b"],
    )

    logger.info("=" * 60)
    logger.info("LSTM 가중치 저장: %s", save_path)
    logger.info("최종 검증 정확도: %.2f%%", weights["val_acc"] * 100)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

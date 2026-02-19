"""
ML 가격 예측 모듈 (LSTM)
경량 LSTM 모델로 다음 N봉 방향 확률 예측
- 사전 학습된 가중치 파일 로드 (학습은 별도 스크립트)
- prediction.py와 앙상블: 몬테카를로 60% + LSTM 40%
"""
import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# 모델 캐시
_model_cache: dict = {"model": None, "loaded": False}

# 입력 특징
FEATURE_NAMES = ["close_norm", "volume_norm", "rsi_norm", "macd_norm", "bb_position", "atr_ratio"]
SEQUENCE_LENGTH = 60
NUM_FEATURES = len(FEATURE_NAMES)


class LSTMPredictor:
    """
    경량 LSTM 예측기.
    PyTorch 없이도 동작하는 간이 구현 (numpy 기반 추론).
    실제 PyTorch 모델 로드는 가중치 파일이 있을 때만 활성화.
    """

    def __init__(self, weights_path: str = "models/lstm_weights.npz"):
        self.weights_path = weights_path
        self._weights: Optional[dict] = None
        self._hidden_size = 64
        self._loaded = False

    def load_weights(self) -> bool:
        """사전 학습된 가중치 로드."""
        if self._loaded:
            return True
        if not os.path.exists(self.weights_path):
            logger.info("LSTM 가중치 파일 없음: %s (간이 모드 사용)", self.weights_path)
            return False
        try:
            data = np.load(self.weights_path, allow_pickle=True)
            self._weights = {k: data[k] for k in data.files}
            self._loaded = True
            logger.info("LSTM 가중치 로드 완료: %s", self.weights_path)
            return True
        except Exception as e:
            logger.error("LSTM 가중치 로드 실패: %s", e)
            return False

    def _prepare_features(
        self,
        close_prices: list[float],
        volumes: list[float],
        rsi_values: list[float],
        macd_values: list[float],
        bb_positions: list[float],
        atr_ratios: list[float],
    ) -> Optional[np.ndarray]:
        """입력 데이터를 LSTM 입력 형태로 변환. shape: (1, seq_len, num_features)"""
        if len(close_prices) < SEQUENCE_LENGTH:
            return None

        # 정규화
        close = np.array(close_prices[-SEQUENCE_LENGTH:], dtype=float)
        close_norm = (close - close.min()) / (close.max() - close.min() + 1e-10)

        vol = np.array(volumes[-SEQUENCE_LENGTH:], dtype=float)
        vol_norm = (vol - vol.min()) / (vol.max() - vol.min() + 1e-10)

        rsi = np.array(rsi_values[-SEQUENCE_LENGTH:], dtype=float) / 100.0
        macd = np.array(macd_values[-SEQUENCE_LENGTH:], dtype=float)
        macd_norm = (macd - macd.mean()) / (macd.std() + 1e-10)

        bb = np.array(bb_positions[-SEQUENCE_LENGTH:], dtype=float)
        atr = np.array(atr_ratios[-SEQUENCE_LENGTH:], dtype=float)

        features = np.stack([close_norm, vol_norm, rsi, macd_norm, bb, atr], axis=1)
        return features.reshape(1, SEQUENCE_LENGTH, NUM_FEATURES)

    def predict_direction(
        self,
        close_prices: list[float],
        volumes: list[float],
        rsi_values: list[float],
        macd_values: list[float],
        bb_positions: list[float],
        atr_ratios: list[float],
    ) -> dict:
        """
        방향 예측: up/down/flat 확률 반환.
        가중치 미로드 시 간이 통계 기반 예측.
        """
        # 간이 모드 (가중치 없을 때): 최근 모멘텀 기반
        if not self._loaded:
            return self._simple_predict(close_prices, rsi_values)

        # LSTM 추론 (가중치 있을 때)
        x = self._prepare_features(
            close_prices, volumes, rsi_values, macd_values, bb_positions, atr_ratios
        )
        if x is None:
            return {"up": 0.33, "down": 0.33, "flat": 0.34, "confidence": 0.0}

        try:
            # 간이 LSTM forward pass (numpy)
            probs = self._forward(x)
            return {
                "up": round(float(probs[0]), 4),
                "down": round(float(probs[1]), 4),
                "flat": round(float(probs[2]), 4),
                "confidence": round(float(max(probs) - 0.33), 4),
            }
        except Exception as e:
            logger.error("LSTM 추론 실패: %s", e)
            return self._simple_predict(close_prices, rsi_values)

    def _simple_predict(self, close_prices: list[float], rsi_values: list[float]) -> dict:
        """간이 통계 기반 예측 (LSTM 미사용 시 폴백)."""
        if len(close_prices) < 20:
            return {"up": 0.33, "down": 0.33, "flat": 0.34, "confidence": 0.0}

        # 최근 모멘텀
        recent = close_prices[-10:]
        momentum = (recent[-1] - recent[0]) / recent[0] * 100

        # RSI 기반
        rsi = rsi_values[-1] if rsi_values else 50.0

        up_prob = 0.33
        down_prob = 0.33

        # 모멘텀 반영
        if momentum > 1.0:
            up_prob += 0.15
            down_prob -= 0.10
        elif momentum < -1.0:
            down_prob += 0.15
            up_prob -= 0.10

        # RSI 반영
        if rsi < 30:
            up_prob += 0.10
        elif rsi > 70:
            down_prob += 0.10

        flat_prob = max(0.0, 1.0 - up_prob - down_prob)
        total = up_prob + down_prob + flat_prob
        up_prob /= total
        down_prob /= total
        flat_prob /= total

        confidence = max(up_prob, down_prob, flat_prob) - 0.33

        return {
            "up": round(up_prob, 4),
            "down": round(down_prob, 4),
            "flat": round(flat_prob, 4),
            "confidence": round(max(0.0, confidence), 4),
        }

    def _forward(self, x: np.ndarray) -> np.ndarray:
        """간이 LSTM forward pass (numpy). 가중치 행렬 기반."""
        if not self._weights:
            return np.array([0.33, 0.33, 0.34])

        # 가중치 추출
        w_ih = self._weights.get("lstm_w_ih", np.random.randn(4 * self._hidden_size, NUM_FEATURES) * 0.1)
        w_hh = self._weights.get("lstm_w_hh", np.random.randn(4 * self._hidden_size, self._hidden_size) * 0.1)
        b = self._weights.get("lstm_b", np.zeros(4 * self._hidden_size))
        w_out = self._weights.get("fc_w", np.random.randn(3, self._hidden_size) * 0.1)
        b_out = self._weights.get("fc_b", np.zeros(3))

        h = np.zeros(self._hidden_size)
        c = np.zeros(self._hidden_size)
        hs = self._hidden_size

        for t in range(x.shape[1]):
            xt = x[0, t, :]
            gates = w_ih @ xt + w_hh @ h + b
            i_gate = self._sigmoid(gates[:hs])
            f_gate = self._sigmoid(gates[hs:2*hs])
            g_gate = np.tanh(gates[2*hs:3*hs])
            o_gate = self._sigmoid(gates[3*hs:])
            c = f_gate * c + i_gate * g_gate
            h = o_gate * np.tanh(c)

        logits = w_out @ h + b_out
        probs = self._softmax(logits)
        return probs

    @staticmethod
    def _sigmoid(x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        e = np.exp(x - np.max(x))
        return e / e.sum()

    def get_ensemble_modifier(self, prediction: dict, signal: str) -> float:
        """LSTM 예측 기반 신뢰도 보정값."""
        conf = prediction.get("confidence", 0)
        if conf < 0.05:
            return 0.0

        is_long = "LONG" in signal
        is_short = "SHORT" in signal
        up = prediction.get("up", 0.33)
        down = prediction.get("down", 0.33)

        if is_long and up > 0.5:
            return min(conf * 0.4, 0.08)
        elif is_short and down > 0.5:
            return min(conf * 0.4, 0.08)
        elif is_long and down > 0.5:
            return -min(conf * 0.3, 0.05)
        elif is_short and up > 0.5:
            return -min(conf * 0.3, 0.05)

        return 0.0

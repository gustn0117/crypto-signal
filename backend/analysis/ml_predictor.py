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
        # 간이 모드 (가중치 없을 때): A4 중복 제거된 폴백
        if not self._loaded:
            return self._simple_predict(close_prices, volumes, bb_positions, atr_ratios)

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
            return self._simple_predict(close_prices, volumes, bb_positions, atr_ratios)

    def _simple_predict(
        self,
        close_prices: list[float],
        volumes: list[float],
        bb_positions: list[float],
        atr_ratios: list[float],
    ) -> dict:
        """A4: 중복 제거된 간이 예측 (RSI/momentum 제거 → BB/거래량/변동성 추세 활용).

        signal_engine이 이미 RSI, MACD, 모멘텀을 분석하므로
        여기서는 다른 차원의 정보만 사용:
        - BB 위치 추세 (밴드 내 위치 변화)
        - 거래량 추세 (증가/감소)
        - ATR 추세 (변동성 확장/수축)
        """
        if len(close_prices) < 20:
            return {"up": 0.33, "down": 0.33, "flat": 0.34, "confidence": 0.0}

        up_prob = 0.33
        down_prob = 0.33

        # 1) BB 위치 추세: 최근 5봉의 BB position 변화
        if len(bb_positions) >= 10:
            bb_recent = bb_positions[-5:]
            bb_prev = bb_positions[-10:-5]
            bb_trend = (sum(bb_recent) / len(bb_recent)) - (sum(bb_prev) / len(bb_prev))
            if bb_trend > 0.15:
                up_prob += 0.10
                down_prob -= 0.05
            elif bb_trend < -0.15:
                down_prob += 0.10
                up_prob -= 0.05
            # 극단적 BB 위치 + 방향 전환
            bb_last = bb_positions[-1] if bb_positions else 0.5
            if bb_last < 0.1 and bb_trend > 0:
                up_prob += 0.05  # 바닥에서 반등
            elif bb_last > 0.9 and bb_trend < 0:
                down_prob += 0.05  # 천장에서 하락

        # 2) 거래량 추세: 최근 5봉 vs 이전 10봉
        if len(volumes) >= 15:
            vol_recent = sum(volumes[-5:]) / 5
            vol_prev = sum(volumes[-15:-5]) / 10
            vol_change = (vol_recent - vol_prev) / (vol_prev + 1e-10)
            # 거래량 급등 + 가격 상승 = 강한 매수세
            if len(close_prices) >= 5:
                price_dir = close_prices[-1] - close_prices[-5]
                if vol_change > 0.5 and price_dir > 0:
                    up_prob += 0.08
                elif vol_change > 0.5 and price_dir < 0:
                    down_prob += 0.08

        # 3) ATR 추세: 변동성 확장/수축
        if len(atr_ratios) >= 10:
            atr_recent = sum(atr_ratios[-3:]) / 3
            atr_prev = sum(atr_ratios[-10:-3]) / 7
            if atr_recent > atr_prev * 1.3:
                # 변동성 확장 = flat 감소, 방향성 증가
                up_prob *= 1.05
                down_prob *= 1.05

        flat_prob = max(0.05, 1.0 - up_prob - down_prob)
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

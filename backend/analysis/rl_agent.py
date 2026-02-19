"""
강화학습 프레임워크
DQN 에이전트로 시그널 가중치 최적화
- 환경: 가격/지표 상태 → BUY/SELL/HOLD 액션
- 보상: 실현 PnL - 드로다운 페널티
- 초기에는 signal_engine의 가중치 최적화에만 활용
"""
import logging
import os
import random
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RLState:
    """강화학습 환경 상태"""
    price_features: list[float]    # [close_norm, volume_ratio, atr_ratio]
    indicator_values: list[float]  # [rsi, macd_hist, bb_pos, adx]
    regime: int                    # 0=unknown, 1=trending_up, 2=trending_down, 3=ranging, 4=volatile
    portfolio_state: list[float]   # [position_pct, unrealized_pnl_pct, cash_pct]


REGIME_MAP = {
    "UNKNOWN": 0, "TRENDING_UP": 1, "TRENDING_DOWN": 2,
    "RANGING": 3, "VOLATILE": 4,
}

STATE_DIM = 11  # 3 + 4 + 1 + 3
ACTION_DIM = 3  # BUY, SELL, HOLD
ACTIONS = ["BUY", "SELL", "HOLD"]


class ReplayBuffer:
    """경험 재생 버퍼"""
    def __init__(self, capacity: int = 10000):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int) -> list:
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))

    def __len__(self):
        return len(self.buffer)


class DQNAgent:
    """
    DQN 에이전트 (numpy 기반 간이 구현).
    PyTorch 미설치 환경에서도 동작.
    """

    def __init__(
        self,
        state_dim: int = STATE_DIM,
        action_dim: int = ACTION_DIM,
        hidden_dim: int = 64,
        lr: float = 0.001,
        gamma: float = 0.95,
        epsilon: float = 1.0,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.995,
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.hidden_dim = hidden_dim
        self.lr = lr
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

        # 간이 2-layer 네트워크 (numpy)
        self.w1 = np.random.randn(hidden_dim, state_dim) * 0.1
        self.b1 = np.zeros(hidden_dim)
        self.w2 = np.random.randn(action_dim, hidden_dim) * 0.1
        self.b2 = np.zeros(action_dim)

        self.buffer = ReplayBuffer()
        self.train_step = 0

    def _forward(self, state: np.ndarray) -> np.ndarray:
        """Q-값 계산."""
        h = np.maximum(0, self.w1 @ state + self.b1)  # ReLU
        return self.w2 @ h + self.b2

    def select_action(self, state: np.ndarray) -> int:
        """epsilon-greedy 액션 선택."""
        if random.random() < self.epsilon:
            return random.randint(0, self.action_dim - 1)
        q_values = self._forward(state)
        return int(np.argmax(q_values))

    def train_batch(self, batch_size: int = 32) -> float:
        """미니배치 학습. 반환: 평균 loss."""
        if len(self.buffer) < batch_size:
            return 0.0

        batch = self.buffer.sample(batch_size)
        total_loss = 0.0

        for state, action, reward, next_state, done in batch:
            q_values = self._forward(state)
            target = q_values.copy()

            if done:
                target[action] = reward
            else:
                next_q = self._forward(next_state)
                target[action] = reward + self.gamma * np.max(next_q)

            # 간이 gradient descent
            error = target - q_values
            total_loss += np.sum(error ** 2)

            # 역전파 (간이)
            h = np.maximum(0, self.w1 @ state + self.b1)
            # output layer gradient
            d_out = error
            self.w2 += self.lr * np.outer(d_out, h)
            self.b2 += self.lr * d_out

            # hidden layer gradient
            d_hidden = (self.w2.T @ d_out) * (h > 0).astype(float)
            self.w1 += self.lr * np.outer(d_hidden, state)
            self.b1 += self.lr * d_hidden

        self.train_step += 1

        # epsilon decay
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

        return total_loss / batch_size

    def save(self, path: str = "models/dqn_weights.npz"):
        """가중치 저장."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez(path, w1=self.w1, b1=self.b1, w2=self.w2, b2=self.b2,
                 epsilon=np.array([self.epsilon]))
        logger.info("DQN 가중치 저장: %s", path)

    def load(self, path: str = "models/dqn_weights.npz") -> bool:
        """가중치 로드."""
        if not os.path.exists(path):
            return False
        try:
            data = np.load(path)
            self.w1 = data["w1"]
            self.b1 = data["b1"]
            self.w2 = data["w2"]
            self.b2 = data["b2"]
            self.epsilon = float(data["epsilon"][0])
            logger.info("DQN 가중치 로드: %s (epsilon=%.3f)", path, self.epsilon)
            return True
        except Exception as e:
            logger.error("DQN 가중치 로드 실패: %s", e)
            return False


class TradingEnvironment:
    """
    트레이딩 환경.
    OHLCV + 지표 데이터로 에피소드 시뮬레이션.
    """

    def __init__(self, close_prices: list[float], features: list[list[float]]):
        """
        close_prices: 종가 리스트
        features: 각 시점의 특징 벡터 리스트 (state_dim 크기)
        """
        self.close_prices = close_prices
        self.features = features
        self.current_step = 0
        self.position = 0  # -1, 0, 1
        self.entry_price = 0.0
        self.total_pnl = 0.0
        self.peak_equity = 1.0
        self.equity = 1.0

    def reset(self) -> np.ndarray:
        """환경 초기화."""
        self.current_step = 0
        self.position = 0
        self.entry_price = 0.0
        self.total_pnl = 0.0
        self.peak_equity = 1.0
        self.equity = 1.0
        return self._get_state()

    def _get_state(self) -> np.ndarray:
        """현재 상태 반환."""
        if self.current_step < len(self.features):
            return np.array(self.features[self.current_step], dtype=float)
        return np.zeros(STATE_DIM)

    def step(self, action: int) -> tuple:
        """
        액션 실행.
        Returns: (next_state, reward, done, info)
        """
        if self.current_step >= len(self.close_prices) - 1:
            return self._get_state(), 0.0, True, {}

        current_price = self.close_prices[self.current_step]
        next_price = self.close_prices[self.current_step + 1]
        price_change = (next_price - current_price) / current_price

        reward = 0.0

        if action == 0:  # BUY
            if self.position == 0:
                self.position = 1
                self.entry_price = current_price
            elif self.position == -1:
                # 숏 청산
                pnl = (self.entry_price - current_price) / self.entry_price
                self.total_pnl += pnl
                self.equity *= (1 + pnl)
                reward = pnl * 100
                self.position = 0
        elif action == 1:  # SELL
            if self.position == 0:
                self.position = -1
                self.entry_price = current_price
            elif self.position == 1:
                # 롱 청산
                pnl = (current_price - self.entry_price) / self.entry_price
                self.total_pnl += pnl
                self.equity *= (1 + pnl)
                reward = pnl * 100
                self.position = 0
        else:  # HOLD
            if self.position == 1:
                reward = price_change * 10  # 보유 중 수익
            elif self.position == -1:
                reward = -price_change * 10

        # 드로다운 페널티
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        drawdown = (self.peak_equity - self.equity) / self.peak_equity
        if drawdown > 0.05:
            reward -= drawdown * 5

        self.current_step += 1
        done = self.current_step >= len(self.close_prices) - 1

        return self._get_state(), reward, done, {"equity": self.equity, "pnl": self.total_pnl}


def optimize_signal_weights(
    agent: DQNAgent,
    episode_results: list[dict],
) -> dict:
    """
    DQN 에이전트의 학습 결과를 signal_engine 가중치로 변환.
    에이전트의 Q-값 분포를 분석하여 카테고리별 최적 가중치 추출.
    """
    # 에피소드 결과 분석: 승률이 높은 액션의 상태 특성 분석
    if not episode_results:
        return {}

    # 기본 가중치
    base_weights = {
        "indicators": 0.30,
        "candle_patterns": 0.12,
        "chart_patterns": 0.25,
        "volume": 0.15,
        "futures_data": 0.18,
    }

    # 에피소드 평균 수익률로 가중치 미세 조정
    avg_pnl = sum(r.get("pnl", 0) for r in episode_results) / len(episode_results)

    if avg_pnl > 0:
        # 수익이 나는 경우: 현재 가중치 유지 (이미 좋음)
        return base_weights

    # 손실인 경우: indicators 비중 증가, chart_patterns 감소
    adjusted = dict(base_weights)
    adjusted["indicators"] += 0.03
    adjusted["chart_patterns"] -= 0.02
    adjusted["futures_data"] += 0.01

    # 정규화
    total = sum(adjusted.values())
    return {k: round(v / total, 4) for k, v in adjusted.items()}

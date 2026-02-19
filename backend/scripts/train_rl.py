"""
강화학습 학습 스크립트
OHLCV 데이터로 DQN 에이전트 훈련.
사용법: python scripts/train_rl.py
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
    from analysis.rl_agent import DQNAgent, TradingEnvironment, STATE_DIM

    logger.info("DQN 강화학습 시작")

    db = Database()
    await db.connect()
    candle_repo = CandleRepo(db.client, SUPABASE_SCHEMA)

    # BTC/USDT 1h 데이터로 학습
    try:
        df = await candle_repo.get_candles("BTC/USDT", "1h", limit=5000)
        logger.info("BTC/USDT: %d 캔들 로드", len(df))
    except Exception as e:
        logger.error("데이터 로드 실패: %s", e)
        await db.close()
        return

    await db.close()

    if len(df) < 500:
        logger.error("학습 데이터 부족")
        return

    close_prices = df["close"].tolist()
    volumes = df["volume"].tolist()

    # 특징 벡터 생성 (각 시점)
    features = []
    for i in range(len(close_prices)):
        # 가격 특징
        if i < 20:
            price_norm = 0.5
            vol_ratio = 1.0
            atr_ratio = 0.03
        else:
            segment = close_prices[max(0, i-20):i]
            price_norm = (close_prices[i] - min(segment)) / (max(segment) - min(segment) + 1e-10)
            vol_avg = np.mean(volumes[max(0, i-20):i])
            vol_ratio = volumes[i] / vol_avg if vol_avg > 0 else 1.0
            returns = [(close_prices[j] - close_prices[j-1]) / close_prices[j-1]
                      for j in range(max(1, i-14), i+1)]
            atr_ratio = np.std(returns) if returns else 0.03

        # RSI 근사
        if i < 15:
            rsi_norm = 0.5
        else:
            gains = [max(0, close_prices[j] - close_prices[j-1]) for j in range(i-13, i+1)]
            losses = [max(0, close_prices[j-1] - close_prices[j]) for j in range(i-13, i+1)]
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            rs = avg_gain / (avg_loss + 1e-10)
            rsi_norm = 1.0 - (1.0 / (1.0 + rs))

        # 상태 벡터 (STATE_DIM=11)
        state = [
            price_norm, vol_ratio, atr_ratio,  # price features (3)
            rsi_norm, 0.0, 0.5, 0.0,           # indicator values (4)
            0,                                    # regime (1)
            0.0, 0.0, 1.0,                       # portfolio state (3)
        ]
        features.append(state)

    # DQN 에이전트 생성
    agent = DQNAgent(
        state_dim=STATE_DIM,
        action_dim=3,
        lr=0.0005,
        gamma=0.95,
        epsilon=1.0,
        epsilon_min=0.05,
        epsilon_decay=0.998,
    )

    # 학습: 에피소드 반복
    num_episodes = 50
    episode_length = 200
    best_pnl = -float('inf')

    for ep in range(num_episodes):
        # 랜덤 시작점
        start = np.random.randint(0, max(1, len(close_prices) - episode_length - 1))
        ep_close = close_prices[start:start + episode_length]
        ep_features = features[start:start + episode_length]

        env = TradingEnvironment(ep_close, ep_features)
        state = env.reset()
        total_reward = 0.0

        for step in range(episode_length - 1):
            action = agent.select_action(state)
            next_state, reward, done, info = env.step(action)
            agent.buffer.push(state, action, reward, next_state, done)
            state = next_state
            total_reward += reward

            if len(agent.buffer) >= 32:
                agent.train_batch(32)

            if done:
                break

        pnl = info.get("pnl", 0)
        if pnl > best_pnl:
            best_pnl = pnl

        if (ep + 1) % 10 == 0:
            logger.info("에피소드 %d/%d: reward=%.2f, pnl=%.4f, epsilon=%.3f, best_pnl=%.4f",
                       ep+1, num_episodes, total_reward, pnl, agent.epsilon, best_pnl)

    # 가중치 저장
    os.makedirs("models", exist_ok=True)
    agent.save("models/dqn_weights.npz")
    logger.info("DQN 학습 완료, 가중치 저장: models/dqn_weights.npz")


if __name__ == "__main__":
    asyncio.run(main())

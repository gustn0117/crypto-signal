"""
오더북 분석 모듈
매수/매도 불균형, 벽 감지, 유동성 공백 분석
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderbookResult:
    """오더북 분석 결과"""
    imbalance_ratio: float   # -1 ~ +1 (양수=매수 우세)
    bid_wall: float           # 매수벽 가격 (0이면 없음)
    ask_wall: float           # 매도벽 가격 (0이면 없음)
    spread_pct: float         # 스프레드 비율 (%)
    signal: str               # long / short / neutral
    strength: float           # 0.0 ~ 1.0
    description: str


def analyze_orderbook(orderbook: dict | None, current_price: float = 0) -> OrderbookResult | None:
    """
    오더북 데이터 분석.
    orderbook: {"bids": [[price, amount], ...], "asks": [[price, amount], ...]}
    """
    if not orderbook:
        return None

    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    if not bids or not asks:
        return None

    try:
        # 상위 20레벨 합산
        bid_vol = sum(float(b[1]) for b in bids[:20])
        ask_vol = sum(float(a[1]) for a in asks[:20])
        total = bid_vol + ask_vol

        if total <= 0:
            return None

        # 1) 불균형 비율 (-1 ~ +1)
        imbalance = (bid_vol - ask_vol) / total

        # 2) 스프레드
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid = (best_bid + best_ask) / 2
        spread_pct = (best_ask - best_bid) / mid * 100 if mid > 0 else 0

        # 3) 벽 감지: 상위 5레벨에서 평균의 3배 이상 물량
        bid_amounts = [float(b[1]) for b in bids[:10]]
        ask_amounts = [float(a[1]) for a in asks[:10]]
        avg_bid = sum(bid_amounts) / len(bid_amounts) if bid_amounts else 1
        avg_ask = sum(ask_amounts) / len(ask_amounts) if ask_amounts else 1

        bid_wall = 0.0
        for b in bids[:5]:
            if float(b[1]) > avg_bid * 3:
                bid_wall = float(b[0])
                break

        ask_wall = 0.0
        for a in asks[:5]:
            if float(a[1]) > avg_ask * 3:
                ask_wall = float(a[0])
                break

        # 4) 시그널 결정
        if imbalance > 0.3:
            signal = "long"
            strength = min(imbalance, 0.8)
            desc = f"매수 불균형 {imbalance:+.2f} — 매수세 우세"
        elif imbalance < -0.3:
            signal = "short"
            strength = min(abs(imbalance), 0.8)
            desc = f"매도 불균형 {imbalance:+.2f} — 매도세 우세"
        else:
            signal = "neutral"
            strength = 0.0
            desc = f"오더북 균형 {imbalance:+.2f}"

        # 벽이 있으면 강도 부스트
        if bid_wall > 0 and signal == "long":
            strength = min(strength + 0.15, 0.9)
            desc += f" | 매수벽 {bid_wall:,.2f}"
        if ask_wall > 0 and signal == "short":
            strength = min(strength + 0.15, 0.9)
            desc += f" | 매도벽 {ask_wall:,.2f}"

        return OrderbookResult(
            imbalance_ratio=round(imbalance, 4),
            bid_wall=bid_wall,
            ask_wall=ask_wall,
            spread_pct=round(spread_pct, 4),
            signal=signal,
            strength=round(strength, 3),
            description=desc,
        )
    except Exception as e:
        logger.warning("오더북 분석 오류: %s", e)
        return None

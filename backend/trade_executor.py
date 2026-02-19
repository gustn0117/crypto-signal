"""
자동매매 실행 모듈
CONFIRMED 시그널 → 자동 주문 (포트폴리오 리스크 체크 후)
"""
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """주문 실행 결과"""
    success: bool
    symbol: str
    side: str           # "buy" / "sell"
    amount: float
    price: float
    order_id: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class TradeExecutor:
    """
    자동매매 실행기.
    - 시그널 확인(CONFIRMED) 시 자동 주문
    - 포트폴리오 리스크 체크 후 실행
    - SL/TP 주문 동시 설정
    """

    def __init__(
        self,
        exchange_client,
        paper_repo=None,
        risk_manager=None,
        enabled: bool = False,
        max_positions: int = 3,
        max_position_pct: float = 10.0,
    ):
        self.client = exchange_client
        self.paper_repo = paper_repo
        self.risk_manager = risk_manager
        self.enabled = enabled
        self.max_positions = max_positions
        self.max_position_pct = max_position_pct
        self._active_orders: dict[str, dict] = {}

    async def execute_signal(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        trade_params: dict,
        equity: float,
        open_positions: list[dict],
    ) -> Optional[ExecutionResult]:
        """
        시그널 기반 자동 주문 실행.
        Returns: ExecutionResult 또는 None (실행하지 않음)
        """
        if not self.enabled:
            logger.debug("[자동매매] 비활성화 상태")
            return None

        if signal in ("NEUTRAL",):
            return None

        is_long = signal in ("STRONG_LONG", "LONG")
        side = "buy" if is_long else "sell"

        # 1) 포지션 수 제한
        if len(open_positions) >= self.max_positions:
            logger.info("[자동매매] 최대 포지션 수 초과 (%d/%d)", len(open_positions), self.max_positions)
            return None

        # 2) 이미 같은 심볼에 포지션 있으면 스킵
        for pos in open_positions:
            if pos.get("symbol") == symbol and pos.get("status") == "OPEN":
                logger.debug("[자동매매] %s 이미 포지션 보유", symbol)
                return None

        # 3) 포지션 사이즈 계산
        suggested_pct = trade_params.get("suggested_position_pct", 5.0)
        position_pct = min(suggested_pct, self.max_position_pct)
        position_usdt = equity * (position_pct / 100)

        # 4) 리스크 체크
        if self.risk_manager:
            warnings = self.risk_manager.check_new_position(
                symbol, position_usdt, open_positions, equity
            )
            critical = [w for w in warnings if w.level == "critical"]
            if critical:
                logger.warning("[자동매매] 리스크 경고로 주문 거부: %s", critical[0].message)
                return None

        # 5) 주문 실행 (현재는 모의투자)
        try:
            entry_price = trade_params.get("entry_price", 0)
            if entry_price <= 0:
                return None

            quantity = position_usdt / entry_price

            if self.paper_repo:
                # 모의투자로 실행
                account = await self.paper_repo.get_or_create_account()
                trade = await self.paper_repo.open_trade(
                    account_id=account["id"],
                    symbol=symbol,
                    direction="LONG" if is_long else "SHORT",
                    entry_price=entry_price,
                    quantity=quantity,
                    position_usdt=position_usdt,
                    stop_loss=trade_params.get("stop_loss"),
                    take_profit_1=trade_params.get("take_profit_1"),
                    take_profit_2=trade_params.get("take_profit_2"),
                    take_profit_3=trade_params.get("take_profit_3"),
                )
                order_id = str(trade.get("id", ""))
            else:
                # 실거래 (Binance API)
                order = await self._place_real_order(symbol, side, quantity, entry_price)
                order_id = order.get("id", "")

            logger.info(
                "[자동매매] %s %s %.4f @ %.2f (%.1f USDT, %.1f%%)",
                side.upper(), symbol, quantity, entry_price, position_usdt, position_pct,
            )

            return ExecutionResult(
                success=True,
                symbol=symbol,
                side=side,
                amount=quantity,
                price=entry_price,
                order_id=order_id,
            )

        except Exception as e:
            logger.error("[자동매매] 주문 실패: %s", e)
            return ExecutionResult(
                success=False, symbol=symbol, side=side,
                amount=0, price=0, error=str(e),
            )

    async def _place_real_order(self, symbol: str, side: str, amount: float, price: float) -> dict:
        """실거래 주문 (Binance Futures). 현재 구현은 시장가."""
        try:
            order = await self.client.exchange.create_market_order(
                symbol, side, amount
            )
            return order
        except Exception as e:
            raise RuntimeError(f"주문 실행 실패: {e}") from e

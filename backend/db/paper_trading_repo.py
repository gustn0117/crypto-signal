"""
모의 트레이딩 저장소 (Supabase PostgREST)
"""
from datetime import datetime, timezone
from supabase import AsyncClient


class PaperTradingRepo:
    def __init__(self, client: AsyncClient, schema: str = "coin"):
        self._client = client
        self._schema = schema

    def _accounts(self):
        return self._client.schema(self._schema).table("paper_accounts")

    def _trades(self):
        return self._client.schema(self._schema).table("paper_trades")

    # ─── 계좌 ───────────────────────────────────────────────

    async def get_or_create_account(self) -> dict:
        """기본 계좌 조회/생성."""
        resp = await (
            self._accounts()
            .select("*")
            .order("id")
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]

        now = datetime.now(timezone.utc).isoformat()
        resp = await (
            self._accounts()
            .insert({
                "name": "Default",
                "initial_balance": 10000.0,
                "balance": 10000.0,
                "created_at": now,
                "updated_at": now,
            })
            .execute()
        )
        return resp.data[0]

    async def get_account(self, account_id: int) -> dict | None:
        resp = await (
            self._accounts()
            .select("*")
            .eq("id", account_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    async def reset_account(self, account_id: int) -> dict:
        """계좌 초기화: 잔고 리셋 + 모든 거래 삭제."""
        account = await self.get_account(account_id)
        if not account:
            raise RuntimeError("계좌를 찾을 수 없습니다")

        # 열린 포지션의 position_usdt 복구 불필요 — 전체 삭제 후 초기 잔고로
        await self._trades().delete().eq("account_id", account_id).execute()

        now = datetime.now(timezone.utc).isoformat()
        await (
            self._accounts()
            .update({
                "balance": account["initial_balance"],
                "total_pnl": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "updated_at": now,
            })
            .eq("id", account_id)
            .execute()
        )
        return await self.get_account(account_id)

    # ─── 포지션 열기 ────────────────────────────────────────

    async def open_trade(
        self,
        account_id: int,
        symbol: str,
        direction: str,
        entry_price: float,
        position_usdt: float,
        quantity: float,
        stop_loss: float | None = None,
        take_profit_1: float | None = None,
        take_profit_2: float | None = None,
        take_profit_3: float | None = None,
    ) -> dict:
        """포지션 진입. 잔고에서 position_usdt 차감."""
        account = await self.get_account(account_id)
        if not account or account["balance"] < position_usdt:
            raise RuntimeError("잔고 부족")

        now = datetime.now(timezone.utc).isoformat()

        # 잔고 차감
        new_balance = account["balance"] - position_usdt
        await (
            self._accounts()
            .update({"balance": new_balance, "updated_at": now})
            .eq("id", account_id)
            .execute()
        )

        resp = await (
            self._trades()
            .insert({
                "account_id": account_id,
                "symbol": symbol,
                "direction": direction,
                "status": "OPEN",
                "entry_price": entry_price,
                "current_price": entry_price,
                "quantity": quantity,
                "position_usdt": position_usdt,
                "stop_loss": stop_loss,
                "take_profit_1": take_profit_1,
                "take_profit_2": take_profit_2,
                "take_profit_3": take_profit_3,
                "opened_at": now,
                "updated_at": now,
            })
            .execute()
        )
        return resp.data[0]

    # ─── 포지션 닫기 ────────────────────────────────────────

    async def close_trade(
        self, trade_id: int, close_price: float, close_reason: str
    ) -> dict:
        """포지션 청산. P&L 계산 후 잔고 반영."""
        trade = await self.get_trade_by_id(trade_id)
        if not trade or trade["status"] != "OPEN":
            raise RuntimeError("열린 포지션이 아닙니다")

        is_long = trade["direction"] == "LONG"
        entry = trade["entry_price"]
        qty = trade["quantity"]
        position_usdt = trade["position_usdt"]

        if is_long:
            realized_pnl = (close_price - entry) * qty
            realized_pnl_pct = ((close_price - entry) / entry) * 100
        else:
            realized_pnl = (entry - close_price) * qty
            realized_pnl_pct = ((entry - close_price) / entry) * 100

        now = datetime.now(timezone.utc).isoformat()

        # 거래 업데이트
        await (
            self._trades()
            .update({
                "status": "CLOSED",
                "close_price": close_price,
                "current_price": close_price,
                "realized_pnl": round(realized_pnl, 4),
                "realized_pnl_pct": round(realized_pnl_pct, 4),
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "close_reason": close_reason,
                "closed_at": now,
                "updated_at": now,
            })
            .eq("id", trade_id)
            .execute()
        )

        # 계좌 업데이트: 원금 + P&L 반환
        account = await self.get_account(trade["account_id"])
        return_amount = position_usdt + realized_pnl
        is_win = realized_pnl > 0

        await (
            self._accounts()
            .update({
                "balance": account["balance"] + return_amount,
                "total_pnl": account["total_pnl"] + realized_pnl,
                "total_trades": account["total_trades"] + 1,
                "winning_trades": account["winning_trades"] + (1 if is_win else 0),
                "losing_trades": account["losing_trades"] + (0 if is_win else 1),
                "updated_at": now,
            })
            .eq("id", trade["account_id"])
            .execute()
        )

        return await self.get_trade_by_id(trade_id)

    # ─── 조회 ───────────────────────────────────────────────

    async def get_trade_by_id(self, trade_id: int) -> dict | None:
        resp = await (
            self._trades()
            .select("*")
            .eq("id", trade_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    async def get_open_positions(self, account_id: int) -> list[dict]:
        resp = await (
            self._trades()
            .select("*")
            .eq("account_id", account_id)
            .eq("status", "OPEN")
            .order("opened_at", desc=True)
            .execute()
        )
        return resp.data

    async def get_all_open_positions(self) -> list[dict]:
        """전체 열린 포지션 (백그라운드 P&L 업데이트용)."""
        resp = await (
            self._trades()
            .select("*")
            .eq("status", "OPEN")
            .execute()
        )
        return resp.data

    async def get_trade_history(
        self, account_id: int, limit: int = 20, offset: int = 0
    ) -> list[dict]:
        resp = await (
            self._trades()
            .select("*")
            .eq("account_id", account_id)
            .eq("status", "CLOSED")
            .order("closed_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return resp.data

    async def get_trade_count(self, account_id: int) -> int:
        resp = await (
            self._trades()
            .select("id", count="exact")
            .eq("account_id", account_id)
            .eq("status", "CLOSED")
            .execute()
        )
        return resp.count or 0

    # ─── 실시간 업데이트 ────────────────────────────────────

    async def update_unrealized_pnl(
        self,
        trade_id: int,
        current_price: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await (
            self._trades()
            .update({
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "updated_at": now,
            })
            .eq("id", trade_id)
            .execute()
        )

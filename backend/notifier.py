"""
외부 알림 모듈 — Telegram Bot + Discord Webhook
시그널 확인/약화 시 외부 채널로 알림 전송
"""
import logging
import httpx
from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    DISCORD_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)

_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=10)
    return _http


def format_alert(alert: dict) -> str:
    """알림 딕셔너리를 마크다운 메시지로 포맷."""
    symbol = alert.get("symbol", "?")
    signal = alert.get("signal", "?")
    conf = alert.get("confidence", 0)
    price = alert.get("current_price", 0)
    summary = alert.get("summary", "")

    emoji = {"STRONG_LONG": "🟢🟢", "LONG": "🟢", "SHORT": "🔴",
             "STRONG_SHORT": "🔴🔴", "NEUTRAL": "⚪"}.get(signal, "⚪")

    tp = alert.get("trade_params") or {}
    sl = tp.get("stop_loss", "")
    tp1 = tp.get("take_profit_1", "")

    lines = [
        f"{emoji} *{symbol}* — {signal}",
        f"신뢰도: {conf:.0%} | 가격: {price:,.2f}",
    ]
    if sl and tp1:
        lines.append(f"SL: {float(sl):,.2f} | TP1: {float(tp1):,.2f}")
    if summary:
        lines.append(f"_{summary[:200]}_")
    return "\n".join(lines)


async def send_telegram(message: str) -> bool:
    """Telegram Bot API로 메시지 전송."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = await _get_http().post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        })
        if resp.status_code != 200:
            logger.warning("Telegram 전송 실패: %s", resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.warning("Telegram 전송 오류: %s", e)
        return False


async def send_discord(message: str) -> bool:
    """Discord Webhook으로 메시지 전송."""
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        # Discord는 Markdown 대신 content 필드 사용
        plain = message.replace("*", "**").replace("_", "*")
        resp = await _get_http().post(DISCORD_WEBHOOK_URL, json={"content": plain})
        if resp.status_code not in (200, 204):
            logger.warning("Discord 전송 실패: %s", resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.warning("Discord 전송 오류: %s", e)
        return False


async def notify_alert(alert: dict):
    """모든 채널로 알림 전송 (비동기 병렬)."""
    msg = format_alert(alert)
    import asyncio
    await asyncio.gather(
        send_telegram(msg),
        send_discord(msg),
        return_exceptions=True,
    )

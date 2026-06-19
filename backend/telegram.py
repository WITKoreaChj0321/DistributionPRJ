"""텔레그램 봇 발송 (@licencedistribute 채널)."""
import httpx

from .config import settings

_API = "https://api.telegram.org/bot{token}/{method}"
_TG_LIMIT = 4000  # 텔레그램 메시지 한도(4096) 안전선


def _chunks(text: str, size: int = _TG_LIMIT) -> list[str]:
    """긴 메시지를 줄 경계 기준으로 분할."""
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size:
            if cur:
                out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out or [""]


async def send_message(text: str, chat_id: str | None = None) -> dict:
    """채널/대화방에 텍스트 메시지 전송 (길면 자동 분할)."""
    token = settings.telegram_bot_token
    if not token:
        return {"ok": False, "error": "telegram_bot_token 미설정"}
    target = chat_id or settings.telegram_channel
    sent = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for part in _chunks(text):
            r = await client.post(
                _API.format(token=token, method="sendMessage"),
                json={
                    "chat_id": target,
                    "text": part,
                    "disable_web_page_preview": False,
                },
            )
            data = r.json()
            if not data.get("ok"):
                return {"ok": False, "error": data, "sent": sent}
            sent += 1
    return {"ok": True, "sent": sent}

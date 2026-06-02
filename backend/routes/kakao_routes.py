import secrets
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..kakao import KakaoClient
from ..config import settings

router = APIRouter()

# 개발용 인메모리 토큰 저장소 (프로덕션에서는 세션/Redis 사용)
token_store: dict[str, str] = {}

# CSRF 방지용 state 저장소
_state_store: set[str] = set()


def _get_kakao_client() -> KakaoClient:
    if not settings.kakao_rest_api_key:
        raise HTTPException(
            status_code=503,
            detail="KAKAO_REST_API_KEY가 설정되지 않았습니다.",
        )
    return KakaoClient(
        rest_api_key=settings.kakao_rest_api_key,
        redirect_uri=settings.kakao_redirect_uri,
    )


# ──────────────────────────────────────────────
# OAuth 인증 라우트  (prefix: /auth)
# ──────────────────────────────────────────────

@router.get("/auth/kakao")
async def kakao_login(request: Request) -> RedirectResponse:
    """카카오 OAuth 로그인 URL로 리다이렉트합니다."""
    state = secrets.token_urlsafe(16)
    _state_store.add(state)
    client = _get_kakao_client()
    auth_url = client.get_auth_url(state=state)
    return RedirectResponse(url=auth_url)


@router.get("/auth/kakao/callback")
async def kakao_callback(
    code: str,
    state: str = "",
    error: str = "",
    request: Request = None,
) -> RedirectResponse:
    """카카오 인증 코드를 받아 액세스 토큰을 발급하고 프론트엔드로 리다이렉트합니다."""
    if error:
        return RedirectResponse(url=f"/?error={error}")

    # state 검증 (있을 경우에만)
    if state:
        if state not in _state_store:
            raise HTTPException(status_code=400, detail="유효하지 않은 state 파라미터입니다.")
        _state_store.discard(state)

    client = _get_kakao_client()
    try:
        token_data = await client.get_access_token(code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"카카오 토큰 발급 실패: {exc}")

    access_token = token_data.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=502, detail="액세스 토큰을 받지 못했습니다.")

    # 토큰 저장 및 프론트엔드로 전달
    token_store[access_token] = access_token
    return RedirectResponse(url=f"/?token={access_token}")


# ──────────────────────────────────────────────
# 카카오 API 라우트  (prefix: /api)
# ──────────────────────────────────────────────

@router.get("/api/kakao/friends")
async def get_friends(token: str) -> dict:
    """카카오 친구 목록을 반환합니다."""
    if not token:
        raise HTTPException(status_code=401, detail="토큰이 필요합니다.")

    client = _get_kakao_client()
    try:
        friends = await client.get_friends(token)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"친구 목록 조회 실패: {exc}")

    return {
        "friends": [
            {
                "uuid": f["uuid"],
                "nickname": f["profile_nickname"],
                "thumbnail": f.get("profile_thumbnail_image", ""),
            }
            for f in friends
        ]
    }


class SendKakaoRequest(BaseModel):
    task_id: str
    friend_uuid: str  # "me" 이면 나에게 보내기
    token: str


@router.post("/api/send-kakao")
async def send_kakao(body: SendKakaoRequest) -> dict:
    """분석 결과를 카카오톡으로 전송합니다."""
    from .analyze import tasks

    task = tasks.get(body.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    if task["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail=f"분석이 완료되지 않았습니다. 현재 상태: {task['status']}",
        )

    wrong_questions = task.get("wrong_questions", [])
    similar_questions = task.get("similar_questions", [])

    client = _get_kakao_client()
    try:
        if body.friend_uuid == "me":
            success = await client.send_message_to_me(
                access_token=body.token,
                wrong_questions=wrong_questions,
                similar_questions=similar_questions,
            )
        else:
            success = await client.send_message_to_friend(
                access_token=body.token,
                receiver_uuid=body.friend_uuid,
                wrong_questions=wrong_questions,
                similar_questions=similar_questions,
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"카카오톡 전송 실패: {exc}")

    if not success:
        raise HTTPException(status_code=502, detail="메시지 전송에 실패했습니다.")

    return {"success": True, "message": "카카오톡으로 전송되었습니다."}

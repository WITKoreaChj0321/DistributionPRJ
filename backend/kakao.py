import json
import httpx
from urllib.parse import urlencode


class KakaoClient:
    BASE_URL = "https://kapi.kakao.com"
    AUTH_URL = "https://kauth.kakao.com"

    def __init__(self, rest_api_key: str, redirect_uri: str, client_secret: str = ""):
        self.rest_api_key  = rest_api_key
        self.redirect_uri  = redirect_uri
        self.client_secret = client_secret

    # ── OAuth ─────────────────────────────────────

    def get_auth_url(self, state: str = "") -> str:
        params: dict = {
            "client_id":     self.rest_api_key,
            "redirect_uri":  self.redirect_uri,
            "response_type": "code",
            # 동의항목에 활성화된 항목만 요청 (비활성 항목 포함 시 KOE205)
            # 콘솔 → 카카오 로그인 → 동의항목 에서 아래 항목 활성화 필요:
            #   - 카카오톡 친구 목록(friends)
            #   - 카카오톡 메시지 전송(talk_message)  ← 나에게/친구에게 보내기 필수
            "scope": "profile_nickname,profile_image,friends,talk_message",
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_URL}/oauth/authorize?{urlencode(params)}"

    async def get_access_token(self, code: str) -> dict:
        url  = f"{self.AUTH_URL}/oauth/token"
        data = {
            "grant_type":   "authorization_code",
            "client_id":    self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "code":         code,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        # 카카오 오류 응답 본문까지 포함해서 예외 발생
        if resp.status_code != 200:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            raise RuntimeError(
                f"카카오 토큰 발급 실패 [{resp.status_code}]: {err_body}"
            )

        return resp.json()

    async def get_user_info(self, access_token: str) -> dict:
        """프로필 정보(닉네임, 이미지) 조회."""
        url     = f"{self.BASE_URL}/v2/user/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            return {}

        data    = resp.json()
        profile = data.get("kakao_account", {}).get("profile", {})
        return {
            "nickname":      profile.get("nickname", "카카오 사용자"),
            "profile_image": profile.get("profile_image_url", ""),
        }

    # ── 친구 목록 ──────────────────────────────────

    async def get_friends(self, access_token: str) -> list[dict]:
        """
        friends 권한 필요 (카카오 특별심사).
        권한 없으면 빈 목록 반환.
        """
        url     = f"{self.BASE_URL}/v1/api/talk/friends"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            return []

        elements = resp.json().get("elements", [])
        return [
            {
                "uuid":                  el.get("uuid", ""),
                "profile_nickname":      el.get("profile_nickname", ""),
                "profile_thumbnail_image": el.get("profile_thumbnail_image", ""),
            }
            for el in elements
        ]

    # ── 메시지 전송 ────────────────────────────────

    async def send_message_to_me(
        self,
        access_token: str,
        wrong_questions: list[dict],
        similar_questions: list[dict],
    ) -> bool:
        url      = f"{self.BASE_URL}/v2/api/talk/memo/default/send"
        headers  = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/x-www-form-urlencoded",
        }
        template = self._build_message_template(wrong_questions, similar_questions)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url, headers=headers,
                data={"template_object": json.dumps(template, ensure_ascii=False)},
            )

        if resp.status_code != 200:
            try:
                err = resp.json()
            except Exception:
                err = resp.text
            raise RuntimeError(f"나에게 보내기 실패 [{resp.status_code}]: {err}")

        return resp.json().get("result_code", -1) == 0

    async def send_message_to_friend(
        self,
        access_token: str,
        receiver_uuid: str,
        wrong_questions: list[dict],
        similar_questions: list[dict],
    ) -> bool:
        url     = f"{self.BASE_URL}/v1/api/talk/friends/message/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/x-www-form-urlencoded",
        }
        template = self._build_message_template(wrong_questions, similar_questions)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url, headers=headers,
                data={
                    "receiver_uuids":  json.dumps([receiver_uuid]),
                    "template_object": json.dumps(template, ensure_ascii=False),
                },
            )

        if resp.status_code != 200:
            try:
                err = resp.json()
            except Exception:
                err = resp.text
            raise RuntimeError(f"친구에게 보내기 실패 [{resp.status_code}]: {err}")

        return resp.json().get("successful_receiver_uuids", []) != []

    # ── 메시지 템플릿 ──────────────────────────────

    _CIRCLE = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}

    def _ans_mark(self, ans) -> str:
        if isinstance(ans, int):
            return self._CIRCLE.get(ans, str(ans))
        return str(ans) if ans not in (None, "", "-") else "?"

    def _build_message_template(
        self, wrong_qs: list[dict], similar_qs: list[dict]
    ) -> dict:
        # 상세 텍스트 구성 (카카오 text 타입은 줄바꿈 지원, 약 200자 권장)
        lines: list[str] = []
        lines.append(f"❌ 틀린 문제 {len(wrong_qs)}개")
        for q in wrong_qs[:6]:
            num  = q.get("question_num", "?")
            subj = q.get("subject", "")
            ans  = self._ans_mark(q.get("correct_answer"))
            lines.append(f"· {num}번 [{subj}] 정답 {ans}")

        if similar_qs:
            lines.append("")
            lines.append(f"📖 추천 유사 기출 {len(similar_qs)}개")
            for s in similar_qs[:4]:
                yr   = s.get("year", "")
                subj = s.get("subject", "")
                num  = s.get("question_num", "")
                pct  = round(s.get("similarity", 0) * 100)
                lines.append(f"· {yr}년 {subj} {num}번 (유사 {pct}%)")

        text = "📚 유통관리사 오답 분석 결과\n\n" + "\n".join(lines)
        # 카카오 text 타입 최대 200자 → 초과 시 자르기
        if len(text) > 195:
            text = text[:192] + "..."

        return {
            "object_type": "text",
            "text": text,
            "link": {
                "web_url":        "https://witkoreachj0321.github.io/DistributionPRJ/",
                "mobile_web_url": "https://witkoreachj0321.github.io/DistributionPRJ/",
            },
            "button_title": "웹에서 전체 보기",
        }

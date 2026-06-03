import httpx
from urllib.parse import urlencode


class KakaoClient:
    BASE_URL = "https://kapi.kakao.com"
    AUTH_URL = "https://kauth.kakao.com"

    def __init__(self, rest_api_key: str, redirect_uri: str, client_secret: str = ""):
        self.rest_api_key = rest_api_key
        self.redirect_uri = redirect_uri
        self.client_secret = client_secret

    def get_auth_url(self, state: str = "") -> str:
        params = {
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "friends,talk_message",
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_URL}/oauth/authorize?{urlencode(params)}"

    async def get_access_token(self, code: str) -> dict:
        url = f"{self.AUTH_URL}/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_friends(self, access_token: str) -> list[dict]:
        url = f"{self.BASE_URL}/v1/api/talk/friends"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        elements = data.get("elements", [])
        return [
            {
                "uuid": el.get("uuid", ""),
                "profile_nickname": el.get("profile_nickname", ""),
                "profile_thumbnail_image": el.get("profile_thumbnail_image", ""),
            }
            for el in elements
        ]

    async def send_message_to_friend(
        self,
        access_token: str,
        receiver_uuid: str,
        wrong_questions: list[dict],
        similar_questions: list[dict],
    ) -> bool:
        url = f"{self.BASE_URL}/v1/api/talk/friends/message/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        template = self._build_message_template(wrong_questions, similar_questions)
        import json

        data = {
            "receiver_uuids": json.dumps([receiver_uuid]),
            "template_object": json.dumps(template),
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, data=data)
            resp.raise_for_status()
            result = resp.json()
        # 성공한 전송 수가 1 이상이면 True
        return result.get("successful_receiver_uuids", []) != []

    async def send_message_to_me(
        self,
        access_token: str,
        wrong_questions: list[dict],
        similar_questions: list[dict],
    ) -> bool:
        url = f"{self.BASE_URL}/v2/api/talk/memo/default/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        template = self._build_message_template(wrong_questions, similar_questions)
        import json

        data = {"template_object": json.dumps(template)}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, data=data)
            resp.raise_for_status()
            result = resp.json()
        return result.get("result_code", -1) == 0

    def _build_message_template(
        self, wrong_qs: list[dict], similar_qs: list[dict]
    ) -> dict:
        # 오답 번호 문자열
        wrong_nums = ", ".join(
            str(q.get("question_num", q.get("id", "?"))) for q in wrong_qs
        )
        if not wrong_nums:
            wrong_nums = "없음"

        description = (
            f"틀린 문제: {wrong_nums}번 | 유사 문제 {len(similar_qs)}개 찾음"
        )

        # 버튼: 유사 문제 최대 10개 (카카오 제한)
        buttons = []
        for i, q in enumerate(similar_qs[:10], start=1):
            subject = q.get("subject", "")
            text = q.get("question_text", "")
            short_text = text[:30] + "..." if len(text) > 30 else text
            label = f"Q.{i} [{subject}] {short_text}" if subject else f"Q.{i} {short_text}"
            buttons.append(
                {
                    "title": label,
                    "link": {
                        "web_url": "",
                        "mobile_web_url": "",
                    },
                }
            )

        template: dict = {
            "object_type": "feed",
            "content": {
                "title": "📚 유통관리사 오답 분석 결과",
                "description": description,
                "image_url": "https://developers.kakao.com/assets/img/about/logos/kakaolink/kakaolink_btn_medium.png",
                "link": {
                    "web_url": "",
                    "mobile_web_url": "",
                },
            },
        }
        if buttons:
            template["buttons"] = buttons

        return template

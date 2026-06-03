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

    async def _send_one_memo(self, access_token: str, text: str) -> bool:
        """나에게 보내기 — text 메시지 1건 전송."""
        url     = f"{self.BASE_URL}/v2/api/talk/memo/default/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/x-www-form-urlencoded",
        }
        template = self._text_template(text)
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

    async def send_message_to_me(
        self,
        access_token: str,
        wrong_questions: list[dict],
        similar_questions: list[dict],
        frequent_questions: list[dict] | None = None,
    ) -> bool:
        """문제별로 '문제 본문 + 정답'을 개별 메시지로 분할 전송."""
        messages = self._build_detail_messages(
            wrong_questions, similar_questions, frequent_questions or []
        )
        sent = 0
        for msg in messages:
            try:
                if await self._send_one_memo(access_token, msg):
                    sent += 1
            except RuntimeError:
                raise
        return sent > 0

    async def _send_one_friend(self, access_token: str, uuid: str, text: str) -> bool:
        url     = f"{self.BASE_URL}/v1/api/talk/friends/message/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/x-www-form-urlencoded",
        }
        template = self._text_template(text)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url, headers=headers,
                data={
                    "receiver_uuids":  json.dumps([uuid]),
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

    async def send_message_to_friend(
        self,
        access_token: str,
        receiver_uuid: str,
        wrong_questions: list[dict],
        similar_questions: list[dict],
        frequent_questions: list[dict] | None = None,
    ) -> bool:
        messages = self._build_detail_messages(
            wrong_questions, similar_questions, frequent_questions or []
        )
        sent = 0
        for msg in messages:
            if await self._send_one_friend(access_token, receiver_uuid, msg):
                sent += 1
        return sent > 0

    # ── 메시지 템플릿 ──────────────────────────────

    _CIRCLE = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}

    def _ans_mark(self, ans) -> str:
        if isinstance(ans, int):
            return self._CIRCLE.get(ans, str(ans))
        return str(ans) if ans not in (None, "", "-") else "?"

    def _text_template(self, text: str) -> dict:
        """카카오 text 타입 메시지 템플릿."""
        return {
            "object_type": "text",
            "text": text,
            "link": {
                "web_url":        "https://www.comcbt.com",
                "mobile_web_url": "https://www.comcbt.com",
            },
            "button_title": "기출문제 더 풀기",
        }

    def _question_detail(self, q: dict, header: str) -> str:
        """질문(보기 제외) + 정답만 하나의 메시지로 구성."""
        import re as _re
        num  = q.get("question_num", "?")
        subj = q.get("subject", "")
        body = (q.get("question_text") or "").strip()

        # question_text에 보기가 섞여 있으면 제거 → 질문만 남김
        # 1) 보기 원문자(①②③④⑤) 등장 지점 전까지
        body = _re.split(r'[①②③④⑤❶❷❸❹❺]', body)[0].strip()
        # 2) 그래도 보기 번호('1.' '2.' 연속)가 남으면 첫 물음표까지
        qm = body.find('?')
        if qm > 0:
            body = body[:qm + 1].strip()

        # 정답: wrong은 correct_answer, similar는 answer
        ans = q.get("correct_answer")
        if ans in (None, "", "-"):
            ans = q.get("answer")
        mark = self._ans_mark(ans)

        # 정답 보기 내용 (보기 1개만 — 전체 보기 나열 안 함)
        opts = q.get("options") or []
        ans_text = ""
        if isinstance(ans, int) and 1 <= ans <= len(opts):
            ans_text = _re.sub(r'^\s*\d+[.)]\s*', '', str(opts[ans - 1])).strip()

        # 연도·회차 (유사 기출문제에 존재)
        year   = q.get("year")
        round_ = q.get("round")
        when = ""
        if year:
            when = f"{year}년"
            if round_:
                when += f" {round_}회"
            when += " "

        ans_line = f"✅ 정답: {mark} {ans_text}".rstrip()

        # 본문이 길면 본문만 줄여서 정답 줄을 항상 보존
        head_line = f"{header}  {when}{num}번 [{subj}]"
        reserved = len(head_line) + len(ans_line) + 6  # 줄바꿈/여백
        max_body = max(0, 190 - reserved)
        if len(body) > max_body:
            body = body[:max(0, max_body - 3)].rstrip() + "..."

        parts = [head_line, ""]
        if body:
            parts.append(body)
            parts.append("")
        parts.append(ans_line)
        return "\n".join(parts)

    def _frequent_detail(self, item: dict) -> str:
        """최빈출 기출 1건 메시지 (본문 + 정답 내용)."""
        subj = item.get("subject", "")
        freq = item.get("frequency", 0)
        body = (item.get("question_text") or "").strip()
        ans  = item.get("answer_content", "")

        head = f"🔥 최빈출 [{subj}] {freq}개년 반복"
        ans_line = f"✅ 정답: {ans}"
        reserved = len(head) + len(ans_line) + 6
        max_body = max(0, 190 - reserved)
        if len(body) > max_body:
            body = body[:max(0, max_body - 3)].rstrip() + "..."
        return f"{head}\n\n{body}\n\n{ans_line}"

    def _build_detail_messages(
        self, wrong_qs: list[dict], similar_qs: list[dict],
        frequent_qs: list[dict] | None = None,
    ) -> list[str]:
        """문제별 '본문 + 정답' 메시지 리스트 생성."""
        frequent_qs = frequent_qs or []
        messages: list[str] = []

        # 1) 요약 헤더
        nums = ", ".join(str(q.get("question_num", "?")) for q in wrong_qs) or "없음"
        head = (
            f"📚 유통관리사 오답 분석 결과\n\n"
            f"틀린 문제: {nums}번 ({len(wrong_qs)}개)\n"
            f"유사 기출문제 {len(similar_qs)}개"
        )
        if frequent_qs:
            head += f"\n최빈출 기출 {len(frequent_qs)}개"
        head += "\n\n아래에 문제별 상세를 보내드립니다."
        messages.append(head)

        # 2) 틀린 문제 각각 (본문 + 정답)
        for q in wrong_qs[:8]:
            messages.append(self._question_detail(q, "❌ 틀린 문제"))

        # 3) 유사 기출 상위 3개
        for s in similar_qs[:3]:
            messages.append(self._question_detail(s, "📖 유사 기출"))

        # 4) 최빈출 기출 (본문 + 정답)
        for f in frequent_qs[:5]:
            messages.append(self._frequent_detail(f))

        return messages

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
                "web_url":        "https://www.comcbt.com",
                "mobile_web_url": "https://www.comcbt.com",
            },
            "button_title": "기출문제 더 풀기",
        }

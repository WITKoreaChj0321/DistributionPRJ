import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import os
import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedQuestion:
    num: int
    text: str
    selected_answer: int  # 사용자가 선택한 답 (0=미감지)
    is_marked_wrong: bool  # 오답 표시 감지 여부


@dataclass
class OCRResult:
    full_text: str
    parsed_questions: list[ParsedQuestion]
    wrong_question_nums: list[int]  # 틀린 것으로 감지된 문제 번호들
    confidence: float


class OCRProcessor:
    # 오답 표시: X류 + 사선(\, /)류 + 체크류
    WRONG_MARKS = {"X", "×", "✗", "x", "\\", "/", "＼", "／", "√", "∨"}
    QUESTION_PATTERN = re.compile(r'(\d+)[.\)]\s*(.+?)(?=\n\d+[.\)]|\Z)', re.DOTALL)
    ANSWER_CIRCLE_PATTERN = re.compile(r'[①②③④⑤]|[○◎]?\s*(\d)\s*[○◎]?')
    CIRCLE_NUMBERS = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}

    def __init__(self):
        self._vision_client = None
        self._tesseract_available = False
        self._init_backends()

    def _init_backends(self):
        try:
            from google.cloud import vision

            # .env(settings) 또는 환경변수에서 자격증명 경로 확보
            creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if not creds:
                try:
                    from backend.config import settings
                    creds = settings.google_application_credentials
                except Exception:
                    creds = ""

            if creds:
                cred_path = Path(creds)
                if not cred_path.is_absolute():
                    cred_path = Path(__file__).resolve().parent.parent / cred_path
                if cred_path.exists():
                    # google 라이브러리가 자동으로 읽도록 환경변수에 주입
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)
                    self._vision_client = vision.ImageAnnotatorClient()
                    print(f"[OCR] Google Vision API 사용 (creds: {cred_path.name})")
        except ImportError:
            pass
        except Exception as e:
            print(f"[OCR] Vision 초기화 실패, 폴백 사용: {e}")

        if self._vision_client is None:
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                self._tesseract_available = True
                print("[OCR] Tesseract 사용")
            except Exception:
                print("[OCR] OCR 엔진 없음 → Mock 결과 반환")

    async def process_image(self, image_bytes: bytes) -> OCRResult:
        if self._vision_client is not None:
            return await self._process_with_vision(image_bytes)
        if self._tesseract_available:
            return await self._process_with_tesseract(image_bytes)
        return self._mock_result()

    async def _process_with_vision(self, image_bytes: bytes) -> OCRResult:
        from google.cloud import vision
        # 지역 변수로 캡처: 클로저 안에서도 non-None 타입으로 좁혀짐
        client = self._vision_client
        assert client is not None
        loop = asyncio.get_running_loop()

        def _call():
            request = vision.AnnotateImageRequest(
                image=vision.Image(content=image_bytes),
                features=[vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION)],
            )
            response = client.annotate_image(request=request)
            if response.error.message:
                raise RuntimeError(f"Google Vision API error: {response.error.message}")
            return response

        response = await loop.run_in_executor(None, _call)

        texts = response.text_annotations
        full_text = (texts[0].description or "") if texts else ""
        wrong_nums = self._detect_wrong_marks(texts)
        parsed = self._parse_exam_structure(full_text)

        # 오답 표시 감지 결과를 파싱된 문제에 반영
        for q in parsed:
            if q.num in wrong_nums:
                q.is_marked_wrong = True

        confidence = 0.95 if full_text else 0.0
        return OCRResult(
            full_text=full_text,
            parsed_questions=parsed,
            wrong_question_nums=wrong_nums,
            confidence=confidence,
        )

    async def _process_with_tesseract(self, image_bytes: bytes) -> OCRResult:
        import pytesseract
        from PIL import Image
        import io

        loop = asyncio.get_running_loop()

        def _call():
            img = Image.open(io.BytesIO(image_bytes))
            data = pytesseract.image_to_data(img, lang="kor+eng", output_type=pytesseract.Output.DICT)
            full = pytesseract.image_to_string(img, lang="kor+eng")
            return full, data

        full_text, data = await loop.run_in_executor(None, _call)
        wrong_nums = self._detect_wrong_marks_from_dict(data, full_text)
        parsed = self._parse_exam_structure(full_text)

        for q in parsed:
            if q.num in wrong_nums:
                q.is_marked_wrong = True

        confidence = 0.75 if full_text.strip() else 0.0
        return OCRResult(
            full_text=full_text,
            parsed_questions=parsed,
            wrong_question_nums=wrong_nums,
            confidence=confidence,
        )

    def _parse_exam_structure(self, full_text: str) -> list[ParsedQuestion]:
        questions: list[ParsedQuestion] = []
        lines = full_text.split("\n")
        current_num: Optional[int] = None
        current_lines: list[str] = []

        num_re = re.compile(r'^(\d{1,3})[.\)]\s*(.*)')

        def flush():
            if current_num is None:
                return
            text = " ".join(current_lines).strip()
            selected = self._extract_selected_answer(text)
            questions.append(ParsedQuestion(
                num=current_num,
                text=text,
                selected_answer=selected,
                is_marked_wrong=False,
            ))

        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = num_re.match(line)
            if m:
                flush()
                current_num = int(m.group(1))
                current_lines = [m.group(2)] if m.group(2) else []
            else:
                if current_num is not None:
                    current_lines.append(line)

        flush()
        return questions

    def _extract_selected_answer(self, text: str) -> int:
        for ch, num in self.CIRCLE_NUMBERS.items():
            if ch in text:
                return num
        # 숫자 앞뒤 공백으로 감싸진 단독 숫자 (1~5)
        m = re.search(r'(?<!\d)([1-5])(?!\d)', text)
        if m:
            return int(m.group(1))
        return 0

    def _detect_wrong_marks(self, text_annotations) -> list[int]:
        """Google Vision API text_annotations 기반 X표 감지."""
        wrong_nums: list[int] = []
        if not text_annotations:
            return wrong_nums

        # 각 텍스트 블록의 위치와 내용 수집
        blocks = []
        for ann in text_annotations[1:]:  # 첫 번째는 전체 텍스트
            blocks.append({
                "text": ann.description,
                "bounding": ann.bounding_poly.vertices,
            })

        # X/사선 마크 위치 수집 (마크가 단독 블록이거나 짧은 텍스트에 포함된 경우)
        x_positions = []
        for blk in blocks:
            t = blk["text"].strip()
            is_mark = t in self.WRONG_MARKS or (
                len(t) <= 3 and any(m in t for m in self.WRONG_MARKS)
            )
            if is_mark and blk["bounding"]:
                cx = sum(v.x for v in blk["bounding"]) / 4
                cy = sum(v.y for v in blk["bounding"]) / 4
                x_positions.append((cx, cy))

        if not x_positions:
            return wrong_nums

        # 문제 번호 블록 수집 (점/괄호 없어도 1~80 범위 숫자면 인정)
        num_re = re.compile(r'^(\d{1,3})[.\)]?$')
        num_blocks = []
        for blk in blocks:
            m = num_re.match(blk["text"].strip())
            if m and blk["bounding"]:
                num = int(m.group(1))
                if not (1 <= num <= 80):
                    continue
                cx = sum(v.x for v in blk["bounding"]) / 4
                cy = sum(v.y for v in blk["bounding"]) / 4
                num_blocks.append({"num": num, "cx": cx, "cy": cy})

        # 각 X 위치에서 가장 가까운 문제 번호 연결
        for xc, yc in x_positions:
            nearest = None
            min_dist = float("inf")
            for nb in num_blocks:
                dist = ((nb["cx"] - xc) ** 2 + (nb["cy"] - yc) ** 2) ** 0.5
                if dist < min_dist and dist < 200:  # 픽셀 임계값
                    min_dist = dist
                    nearest = nb["num"]
            if nearest is not None and nearest not in wrong_nums:
                wrong_nums.append(nearest)

        return sorted(wrong_nums)

    def _detect_wrong_marks_from_dict(self, data: dict, full_text: str) -> list[int]:
        """pytesseract image_to_data 딕셔너리 기반 X표 감지."""
        wrong_nums: list[int] = []
        texts = data.get("text", [])
        lefts = data.get("left", [])
        tops = data.get("top", [])

        x_positions = []
        num_positions = []
        num_re = re.compile(r'^(\d{1,3})[.\)]$')

        for i, t in enumerate(texts):
            t_stripped = t.strip()
            if t_stripped in self.WRONG_MARKS:
                x_positions.append((lefts[i], tops[i]))
            m = num_re.match(t_stripped)
            if m:
                num_positions.append({"num": int(m.group(1)), "x": lefts[i], "y": tops[i]})

        for xpos, ypos in x_positions:
            nearest = None
            min_dist = float("inf")
            for nb in num_positions:
                dist = ((nb["x"] - xpos) ** 2 + (nb["y"] - ypos) ** 2) ** 0.5
                if dist < min_dist and dist < 300:
                    min_dist = dist
                    nearest = nb["num"]
            if nearest is not None and nearest not in wrong_nums:
                wrong_nums.append(nearest)

        # 텍스트 패턴 폴백: "1번 X", "X 1번" 등
        pattern = re.compile(r'(\d+)\s*[번문]?\s*[Xx×✗]|[Xx×✗]\s*(\d+)\s*[번문]?')
        for m in pattern.finditer(full_text):
            num = int(m.group(1) or m.group(2))
            if num not in wrong_nums:
                wrong_nums.append(num)

        return sorted(wrong_nums)

    def _mock_result(self) -> OCRResult:
        """API 없을 때 Mock 결과 반환."""
        mock_text = (
            "1. 유통의 개념에 대한 설명으로 옳지 않은 것은?\n"
            "① 생산과 소비의 격차를 조정한다\n"
            "② 장소적 격차를 해소한다\n"
            "③ 시간적 격차를 해소한다\n"
            "④ 품질 격차를 해소한다 ○\n"
            "⑤ 인적 격차를 해소한다\n"
            "2. 소매업의 특성으로 옳은 것은? X\n"
            "① 최종소비자에게 판매\n"
        )
        parsed = self._parse_exam_structure(mock_text)
        return OCRResult(
            full_text=mock_text,
            parsed_questions=parsed,
            wrong_question_nums=[2],
            confidence=0.0,
        )

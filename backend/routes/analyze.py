import re
import uuid
import traceback
from fastapi import APIRouter, UploadFile, BackgroundTasks, HTTPException, Form

router = APIRouter(prefix="/api")

# 인메모리 태스크 저장소 (프로덕션에서는 Redis 사용)
tasks: dict[str, dict] = {}


def _parse_num_list(s: str) -> list[int]:
    """'33, 35 41' 같은 입력을 [33, 35, 41]로 파싱."""
    if not s:
        return []
    nums = []
    for tok in re.split(r'[,\s]+', s.strip()):
        if tok.isdigit():
            n = int(tok)
            if 1 <= n <= 80:
                nums.append(n)
    return sorted(set(nums))


@router.post("/analyze")
async def analyze_image(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] | None = None,  # 다중 업로드 ('images' 필드)
    image: UploadFile | None = None,         # 단일 업로드 하위 호환 ('image' 필드)
    wrong_numbers: str = Form(""),           # 수동 입력 틀린 번호 "33,35"
    exam_year: int = Form(0),                # 수동 입력 연도 (0=자동)
    exam_round: int = Form(0),               # 수동 입력 회차 (0=자동)
) -> dict:
    """여러 이미지를 업로드하고 OCR + 오답 분석을 백그라운드로 실행합니다."""
    files: list[UploadFile] = []
    if images:
        files.extend(images)
    if image:
        files.append(image)
    if not files:
        raise HTTPException(status_code=400, detail="이미지를 1개 이상 업로드해주세요.")

    image_bytes_list: list[bytes] = []
    for f in files:
        if not f.content_type or not f.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")
        data = await f.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{f.filename}: 파일 크기는 20MB를 초과할 수 없습니다.")
        image_bytes_list.append(data)

    manual_wrong = _parse_num_list(wrong_numbers)

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "wrong_questions": [], "similar_questions": []}

    background_tasks.add_task(
        _run_analysis, task_id, image_bytes_list, manual_wrong, exam_year, exam_round
    )

    return {"task_id": task_id, "status": "processing", "image_count": len(image_bytes_list)}


@router.get("/result/{task_id}")
async def get_result(task_id: str) -> dict:
    """태스크 결과를 조회합니다."""
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")

    if task["status"] == "processing":
        return {"status": "processing"}

    if task["status"] == "error":
        return {"status": "error", "detail": task.get("detail", "분석 중 오류가 발생했습니다.")}

    return {
        "status": "done",
        "exam_year": task.get("exam_year", 0),
        "exam_round": task.get("exam_round", 0),
        "auto_detected": task.get("auto_detected", []),
        "wrong_questions": task["wrong_questions"],
        "similar_questions": task["similar_questions"],
    }


async def _run_analysis(
    task_id: str,
    image_bytes_list: list[bytes],
    manual_wrong: list[int],
    manual_year: int,
    manual_round: int,
):
    """이미지 OCR → 연도/오답 결정 → DB 정답 매칭 → 유사 문제 검색.

    오답 결정 우선순위: 수동 입력 > OpenCV 자동 감지
    정답 출처: DB(연도+회차+번호) 조회
    """
    try:
        from ..ocr import OCRProcessor, extract_year_round
        from ..analyzer import WrongQuestion, _infer_subject
        from ..search import SimilarQuestionSearcher
        from ..vectordb import VectorDBManager
        from ..marking import detect_marked_numbers, extract_number_positions
        from database.models import get_question

        ocr = OCRProcessor()

        merged_text_parts: list[str] = []
        parsed_map: dict[int, object] = {}
        auto_wrong: set[int] = set()

        # 각 이미지 OCR + (Vision일 때) OpenCV 마킹 자동 감지
        for img_bytes in image_bytes_list:
            r = await ocr.process_image(img_bytes)
            merged_text_parts.append(r.full_text)
            for pq in r.parsed_questions:
                parsed_map.setdefault(pq.num, pq)
            auto_wrong.update(r.wrong_question_nums)

            # OpenCV 마킹 자동 감지 (Vision 응답이 있을 때만)
            try:
                if ocr._vision_client is not None:
                    from google.cloud import vision
                    img_obj = vision.Image(content=img_bytes)
                    resp = ocr._vision_client.text_detection(image=img_obj)
                    positions = extract_number_positions(resp.text_annotations)
                    auto_wrong.update(detect_marked_numbers(img_bytes, positions))
            except Exception:
                pass

        full_text = "\n".join(merged_text_parts)

        # 연도/회차: 수동 우선, 없으면 OCR 자동
        year, round_ = extract_year_round(full_text)
        if manual_year:
            year = manual_year
        if manual_round:
            round_ = manual_round

        # 틀린 번호: 수동 입력 우선, 없으면 자동 감지
        wrong_nums = manual_wrong if manual_wrong else sorted(auto_wrong)

        # 각 틀린 번호 → DB(연도,회차,번호) 조회로 정답/과목/보기 확보
        wrong_questions: list[WrongQuestion] = []
        for num in wrong_nums:
            db_q = await get_question(year, round_, num)
            if db_q is not None:
                wrong_questions.append(WrongQuestion(
                    question_num=num,
                    question_text=db_q.question_text or "",
                    selected_answer=0,
                    correct_answer=db_q.answer,
                    subject=db_q.subject or _infer_subject(num),
                    options=[o for o in [
                        db_q.option_1, db_q.option_2, db_q.option_3,
                        db_q.option_4, db_q.option_5
                    ] if o],
                ))
            else:
                # DB에 없으면 OCR에서 파싱된 텍스트 사용
                pq = parsed_map.get(num)
                wrong_questions.append(WrongQuestion(
                    question_num=num,
                    question_text=getattr(pq, "text", "") if pq else "",
                    selected_answer=0,
                    correct_answer=None,
                    subject=_infer_subject(num),
                    options=[],
                ))

        # 유사 문제 검색
        vector_db = VectorDBManager()
        searcher = SimilarQuestionSearcher(vectordb=vector_db)
        similar_map = await searcher.find_similar_for_wrong(wrong_questions)

        wrong_list = [
            {
                "question_num": wq.question_num,
                "question_text": wq.question_text,
                "your_answer": wq.selected_answer or "-",
                "correct_answer": wq.correct_answer if wq.correct_answer else "-",
                "subject": wq.subject,
            }
            for wq in wrong_questions
        ]

        similar_list: list[dict] = []
        for sq in similar_map.values():
            similar_list.extend(sq)
        similar_list.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        tasks[task_id] = {
            "status": "done",
            "exam_year": year,
            "exam_round": round_,
            "auto_detected": sorted(auto_wrong),
            "wrong_questions": wrong_list,
            "similar_questions": similar_list,
        }

    except Exception as exc:
        tasks[task_id] = {
            "status": "error",
            "detail": str(exc),
            "traceback": traceback.format_exc(),
        }

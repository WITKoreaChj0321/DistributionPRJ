import uuid
import traceback
from fastapi import APIRouter, UploadFile, BackgroundTasks, HTTPException

router = APIRouter(prefix="/api")

# 인메모리 태스크 저장소 (프로덕션에서는 Redis 사용)
tasks: dict[str, dict] = {}


@router.post("/analyze")
async def analyze_image(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] | None = None,  # 다중 업로드 ('images' 필드)
    image: UploadFile | None = None,         # 단일 업로드 하위 호환 ('image' 필드)
) -> dict:
    """여러 이미지를 업로드하고 OCR + 오답 분석을 백그라운드로 실행합니다."""
    # 다중/단일 입력 통합
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

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "wrong_questions": [], "similar_questions": []}

    background_tasks.add_task(_run_analysis, task_id, image_bytes_list)

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
        "wrong_questions": task["wrong_questions"],
        "similar_questions": task["similar_questions"],
    }


async def _run_analysis(task_id: str, image_bytes_list: list[bytes]):
    """여러 이미지를 OCR → 병합 → 오답 분석 → 유사 문제 검색."""
    try:
        from ..ocr import OCRProcessor, OCRResult
        from ..analyzer import ExamAnalyzer
        from ..search import SimilarQuestionSearcher
        from ..vectordb import VectorDBManager

        # 1단계: 여러 이미지 OCR 후 결과 병합
        ocr = OCRProcessor()
        merged_parsed = []
        merged_wrong: list[int] = []
        merged_text_parts: list[str] = []
        seen_nums: set[int] = set()

        for img_bytes in image_bytes_list:
            r = await ocr.process_image(img_bytes)
            merged_text_parts.append(r.full_text)
            for pq in r.parsed_questions:
                if pq.num not in seen_nums:
                    seen_nums.add(pq.num)
                    merged_parsed.append(pq)
            merged_wrong.extend(r.wrong_question_nums)

        merged_parsed.sort(key=lambda q: q.num)
        ocr_result = OCRResult(
            full_text="\n".join(merged_text_parts),
            parsed_questions=merged_parsed,
            wrong_question_nums=sorted(set(merged_wrong)),
            confidence=0.9 if merged_parsed else 0.0,
        )

        # 2단계: 오답 분석 (동기 메서드, AnalysisResult 반환)
        analyzer = ExamAnalyzer()
        analysis = analyzer.analyze(ocr_result)

        # 3단계: 유사 문제 검색
        vector_db = VectorDBManager()
        searcher = SimilarQuestionSearcher(vectordb=vector_db)
        similar_map = await searcher.find_similar_for_wrong(analysis.wrong_questions)

        # WrongQuestion 데이터클래스 → JSON 직렬화 가능한 dict
        # 프론트엔드는 'your_answer' 필드를 기대함
        wrong_list = [
            {
                "question_num": wq.question_num,
                "question_text": wq.question_text,
                "your_answer": wq.selected_answer,
                "correct_answer": wq.correct_answer,
                "subject": wq.subject,
            }
            for wq in analysis.wrong_questions
        ]

        # similar_map: {question_num: [유사문제 dict 리스트]} → 유사도 내림차순 평탄화
        similar_list: list[dict] = []
        for similar_questions in similar_map.values():
            similar_list.extend(similar_questions)
        similar_list.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        tasks[task_id] = {
            "status": "done",
            "wrong_questions": wrong_list,
            "similar_questions": similar_list,
        }

    except Exception as exc:
        tasks[task_id] = {
            "status": "error",
            "detail": str(exc),
            "traceback": traceback.format_exc(),
        }

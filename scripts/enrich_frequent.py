"""
frequent.json 보강: 기존 빈출 순위를 유지하면서 DB(questions.db)에서
실제 보기(options) · 정답번호(answer) · 해설(explanation)을 매칭해 추가한다.

매칭은 정제된 question_text(공백 제거) 접두사 + 과목 일치로 수행.
매칭 실패 항목은 options 없이 남기며, 퀴즈에서 동일 과목 보기로 자동 생성한다.
"""
import sqlite3
import json
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "database" / "questions.db"
TARGETS = [ROOT / "docs" / "data" / "frequent.json",
           ROOT / "frontend" / "data" / "frequent.json"]


def _clean(t: str) -> str:
    t = re.split(r"[①②③④⑤❶❷❸❹❺]", t or "")[0]
    return re.sub(r"\s+", "", t)


def _strip_opt(o) -> str:
    if not o:
        return ""
    return re.sub(r"^\s*\d+[.)]\s*", "", str(o)).strip()


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.execute(
        "SELECT subject, question_text, option_1, option_2, option_3, "
        "option_4, option_5, answer, explanation FROM questions"
    )
    rows = cur.fetchall()

    src = json.load(open(TARGETS[0], encoding="utf-8"))
    questions = src["questions"]

    matched = 0
    for q in questions:
        key = _clean(q["question_text"])[:15]
        hit = None
        for row in rows:
            if row[0] == q["subject"] and key and _clean(row[1]).startswith(key):
                hit = row
                break
        if hit:
            opts = [_strip_opt(o) for o in hit[2:7] if o and str(o).strip()]
            ans = hit[7]
            q["options"] = opts
            q["answer"] = ans if isinstance(ans, int) and 1 <= ans <= len(opts) else 0
            q["explanation"] = (hit[8] or "").strip()
            matched += 1
        else:
            q["options"] = []
            q["answer"] = 0
            q["explanation"] = ""

    out = {"count": len(questions), "questions": questions}
    for path in TARGETS:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("wrote:", path.relative_to(ROOT), f"({matched}/{len(questions)} with options)")


if __name__ == "__main__":
    main()

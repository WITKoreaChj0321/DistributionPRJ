"""explanations.json을 docs/index.html의 QUIZ_DATA에 explanation 필드로 주입."""
import sys, io, re, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "docs" / "index.html"
EXPL = json.loads((ROOT / "scripts" / "explanations.json").read_text(encoding="utf-8"))


def norm(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return t


txt = HTML.read_text(encoding="utf-8")
marker = "const QUIZ_DATA = "
s = txt.find(marker) + len(marker)
e = txt.find("];", s) + 1
data = json.loads(txt[s:e])

injected = 0
for q in data:
    key = f"{q['year']}|{q['num']}"
    ex = EXPL.get(key)
    if ex:
        q["explanation"] = norm(ex)
        injected += 1
    else:
        q.pop("explanation", None)

new_arr = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
HTML.write_text(txt[:s] + new_arr + txt[e:], encoding="utf-8")
print(f"해설 주입: {injected} / {len(data)} 문제")
print("HTML 크기:", f"{(HTML.stat().st_size/1024):.0f} KB")
# 샘플
sample = next(q for q in data if q.get("explanation"))
print(f"\n[샘플] {sample['year']} {sample['num']}번")
print("  Q:", sample["q"][:50])
print("  해설:", sample["explanation"][:140])

"""QUIZ_DATA(유통관리사/index.html)에 box 이미지 경로(img) 주입."""
import sys, io, re, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "유통관리사" / "index.html"
bm = json.loads((ROOT / "scripts" / "box_map.json").read_text(encoding="utf-8"))

txt = HTML.read_text(encoding="utf-8")
marker = "const QUIZ_DATA = "
s = txt.find(marker) + len(marker)
e = txt.find("];", s) + 1           # index of ']'
arr = txt[s:e]
data = json.loads(arr)

injected = 0
for q in data:
    key = f"{q['year']}|{q['num']}"
    if key in bm:
        q["img"] = ["boxes/" + fn for fn in bm[key]]
        injected += 1
    else:
        q.pop("img", None)

new_arr = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
new_txt = txt[:s] + new_arr + txt[e:]
HTML.write_text(new_txt, encoding="utf-8")
print(f"injected img into {injected} questions / total {len(data)}")
print(f"HTML size: {len(new_txt):,} chars")
# sanity: count questions now having img
print("questions with img:", sum(1 for q in data if q.get("img")))

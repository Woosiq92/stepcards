# 확인하기 정확도 재기: 사진 폴더를 넣으면 카드마다 '맞게 한 사진을 됐어요로', '틀리게 한 사진을 됐어요가 아닌 것으로' 몇 번 맞혔는지 표로 낸다.
# 사진 이름: <카드 번호>_ok_<아무거나>.jpg (맞게 한 결과) / <카드 번호>_bad_<아무거나>.jpg (아직이거나 틀린 결과)
# 사용: .venv/bin/python verify_eval.py <카드 묶음 id> <사진 폴더> [--local]
import base64, io, json, re, sys, time
from pathlib import Path
from PIL import Image
import pipeline
import verify

run_id, folder = sys.argv[1], Path(sys.argv[2])
local = "--local" in sys.argv
d = Path(__file__).parent / "runs" / run_id
cards = {c["n"]: c for c in json.loads((d / "cards.json").read_text())["cards"]}


def photo_url(p):
    im = Image.open(p).convert("RGB"); im.thumbnail((640, 640))
    b = io.BytesIO(); im.save(b, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


rows, cost, secs = [], 0.0, []
by_pos = {i + 1: n for i, n in enumerate(cards)}
for p in sorted(folder.glob("*.jp*g")):
    m = re.match(r"(\d+)_(ok|bad)_", p.name)
    if not m or int(m.group(1)) not in by_pos:
        continue
    c = cards[by_pos[int(m.group(1))]]
    before, after = (pipeline.data_url(verify.reference(d, c, w)) for w in ("before", "after"))
    t0 = time.time()
    ans, cst = verify.ask(c, before, after, photo_url(p), local)
    secs.append(time.time() - t0); cost += cst
    r = verify.tidy(ans, c)
    right = (r["result"] == "done") == (m.group(2) == "ok")
    rows.append((p.name, m.group(2), r["result"], right))
    print(f"{p.name:28} 기대 {m.group(2):3}  판단 {r['result']:9} {'맞음' if right else '틀림'}  {r['hint_ko']}", flush=True)

ok = [x for x in rows if x[1] == "ok"]; bad = [x for x in rows if x[1] == "bad"]
unclear = sum(x[2] == "unclear" for x in rows)
print(f"\n맞게 한 사진 → 됐어요: {sum(x[3] for x in ok)}/{len(ok)}")
print(f"틀리게 한 사진 → 됐어요가 아님: {sum(x[3] for x in bad)}/{len(bad)}")
print(f"잘 안 보여요: {unclear}/{len(rows)} · 평균 {sum(secs) / max(1, len(secs)):.1f}초 · 비용 ${cost:.3f}")

# "더 가까이 보기" 도구를 켜고 끈 단계 나누기를 정답 경계와 비교한다(사진 고르기·SAM은 하지 않음)
# 사용: .venv/bin/python look_eval.py [반복 수=2]
import json, sys, time
import pipeline

GT = [24, 29, 34, 43, 45]  # 라테 영상 20~50초 구간, 사진을 보고 적은 단계 시작 시각(exp1)
reps = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
run = pipeline.Run("samples/latte_eval.mp4")
duration, frames = pipeline.extract(run)
MODES = [(True, 3)] if "--coarse" in sys.argv else [(False, 1), (True, 1)]
for look, every in MODES:
    for k in range(reps):
        run.events = []
        t0 = time.time()
        res = pipeline.split_steps(run, duration, frames, (), look, every)
        starts = [s["start"] for s in res["steps"]]
        errs = [min(abs(st - b) for st in starts) for b in GT]
        looks = [e for e in run.events if e["stage"] == "look"]
        cost = sum(e.get("cost", 0) for e in run.events)
        print(f"look={look} every={every}s #{k + 1}: 단계 {len(starts)}개 · 경계 오차 {errs} (평균 {sum(errs) / len(errs):.2f}s) · "
              f"다시 본 구간 {[(e['start'], e['end']) for e in looks]} · {time.time() - t0:.0f}s · ${cost:.3f} · 문제 {len(res['problems'])}")

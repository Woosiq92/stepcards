import json
from pathlib import Path
from check import check


def step(start, end, rep=None, ko="컵을 드세요.", en="Pick up the cup.", obj="cup"):
    return {"start": start, "end": end, "rep": start if rep is None else rep, "ko": ko, "en": en, "object": obj, "look": "clear glass"}


def test_clean_steps_pass():
    assert check([step(0, 5), step(6, 10)], 20) == ([], [])


def test_overlap_and_touching_boundary():
    p, _ = check([step(0, 5), step(5, 10)], 20)
    assert any("겹칩니다" in x for x in p)


def test_rep_outside_and_out_of_video():
    p, _ = check([step(0, 5, rep=7), step(6, 30)], 20)
    assert any("대표 시각" in x for x in p) and any("영상" in x for x in p)


def test_two_actions_and_length():
    p, _ = check([step(0, 5, ko="빨대를 꽂고 저어주세요."), step(6, 10, ko="가" * 26)], 20)
    assert any("동작이 둘" in x for x in p) and any("깁니다" in x for x in p)


def test_sentence_must_end_with_seyo():
    p, _ = check([step(0, 5, ko="빨대를 꽂는다."), step(6, 10)], 20)
    assert any("세요" in x for x in p)


def test_s_irregular_spelling():
    p, _ = check([step(0, 5, ko="우유를 붓으세요."), step(6, 10, ko="손을 씻으세요.")], 20)
    assert len(p) == 1 and "부으" in p[0]


def test_rieul_spelling():
    p, _ = check([step(0, 5, ko="브러시로 가루를 털으세요."), step(6, 10, ko="뚜껑을 여세요.")], 20)
    assert len(p) == 1 and "'털으' → '터'" in p[0]


def test_reordered_cards_are_not_overlap():
    p, _ = check([step(6, 10), step(0, 5)], 20)
    assert p == []


def test_gap_is_warning_not_problem():
    p, w = check([step(0, 5), step(30, 40)], 60)
    assert p == [] and len(w) == 1


def test_missing_keys():
    p, _ = check([{"start": 0}, step(6, 10)], 20)
    assert any("항목이 없습니다" in x for x in p)


def test_catches_real_overlap_from_exp4():
    raw = Path("runs/exp4/run1.json").read_text().strip().removeprefix("```json").removesuffix("```")
    p, _ = check([{**s, "look": "-"} for s in json.loads(raw)["steps"]], 193)
    assert any("14·15단계" in x and "겹칩니다" in x for x in p)


def test_retry_feeds_problems_back(tmp_path, monkeypatch):
    import types
    import pipeline
    bad = json.dumps({"steps": [step(0, 5), step(5, 10, ko="빨대를 꽂고 저어주세요.")]})
    good = json.dumps({"steps": [step(0, 5), step(6, 10)]})
    sent = []

    def create(**kw):
        sent.append(kw["input"][0]["content"][-1]["text"])
        text = bad if len(sent) == 1 else good
        return types.SimpleNamespace(output_text=text, output=[], usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))

    monkeypatch.setattr(pipeline, "client", types.SimpleNamespace(responses=types.SimpleNamespace(create=create)))
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    run = pipeline.Run(video)
    run.dir = tmp_path
    run.progress = tmp_path / "progress.json"
    result = pipeline.split_steps(run, 20, [])
    assert result["status"] == "ok" and len(sent) == 2
    assert "겹칩니다" in sent[1] and "동작이 둘" in sent[1]


def test_long_video_stays_under_api_image_limit(tmp_path, monkeypatch):
    # Meta API 는 한 요청에 사진 500장까지. 559초 영상(사진 559장)이 400장 안으로 들어가야 한다(11-01 실제 실패: 525·559·595장)
    import types
    import pipeline
    from PIL import Image
    good = json.dumps({"steps": [{"start": 0, "end": 500, "rep": 10, "ko": "닦으세요.", "en": "Wipe.", "object": "cloth", "look": "cloth"}]})
    counts = []

    def create(**kw):
        counts.append(sum(1 for m in kw["input"] for x in m.get("content", []) if isinstance(x, dict) and x.get("type") == "input_image"))
        return types.SimpleNamespace(output_text=good, output=[], usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))

    monkeypatch.setattr(pipeline, "client", types.SimpleNamespace(responses=types.SimpleNamespace(create=create)))
    frame = tmp_path / "f.jpg"
    Image.new("RGB", (8, 8)).save(frame)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    run = pipeline.Run(video)
    run.dir = tmp_path
    run.progress = tmp_path / "progress.json"
    pipeline.split_steps(run, 559, [frame] * 559)
    assert counts and max(counts) <= pipeline.API_MAX_FRAMES


def test_two_actions_skips_holding_form():
    # "누르고 계세요"는 한 동작을 이어 하는 꼴이라 '동작 둘'이 아니다(11-01 검수). "꽂고 저으세요"는 여전히 잡는다
    from check import TWO_ACTIONS
    assert not TWO_ACTIONS.search("버튼을 3초 동안 누르고 계세요.")
    assert not TWO_ACTIONS.search("손잡이를 잡고 있으세요.")
    assert TWO_ACTIONS.search("빨대를 꽂고 저으세요.")

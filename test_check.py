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


def test_two_actions_english():
    bad = ["Pick up the napkin and fold it.", "Fold it, then press.", "Fold the edge then press down."]
    ok = ["Mix water and soap in bucket.", "Take the cash and card.", "Fold the left and right corners.", "Dive both arms forward down then up."]
    for e in bad:
        p, _ = check([step(0, 5, en=e), step(6, 10)], 20)
        assert any("영어 문장에 동작이 둘" in x for x in p), e
    for e in ok:
        assert check([step(0, 5, en=e), step(6, 10)], 20) == ([], []), e


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


# 11-03 검토: '고'로 끝나는 명사·인용, 물건 나열 뒤 방향어, "press and hold" 는 동작 둘이 아니다
def test_two_actions_false_positives():
    for ko in ["냉장고 문을 여세요.", "창고 안에 두세요.", "최고 온도로 맞추세요.", "'끝'이라고 말하세요."]:
        assert check([step(0, 5, ko=ko), step(6, 10)], 20) == ([], []), ko
    for en in ["Press and hold the button.", "Put the knife and fork away.", "Take the lid and cap off."]:
        assert check([step(0, 5, en=en), step(6, 10)], 20) == ([], []), en
    for ko in ["영상을 보고 따라 하세요.", "신발을 신고 나가세요."]:  # 보고·신고는 동사로 쓰인 때 잡는다
        assert any("동작이 둘" in x for x in check([step(0, 5, ko=ko), step(6, 10)], 20)[0]), ko


def test_footage_drawn_only_when_model_says_so():
    from pipeline import footage
    assert footage('{"steps":[],"footage":"drawn"}') == "drawn"
    assert footage('```json\n{"steps":[],"footage":"drawn"}\n```') == "drawn"
    assert footage('{"steps":[],"footage":"real"}') == "real"
    assert footage('{"steps":[]}') == "real"  # 없으면 카메라 판단을 끄지 않는다
    assert footage("not json") == "real"

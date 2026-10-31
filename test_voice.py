# 선생님 목소리: 카드 시간 안으로 자르기, 녹음 올리기·지우기, 카드에 목소리 종류 표시
import io, json, subprocess
import test_app as T
from test_app import A, client, make_run, VIDEO, video, no_network
import voice

SPEECH = [{"start": 0.0, "end": 30.0, "text": "길게 이어진 말"}, {"start": 40.0, "end": 41.0, "text": "짧은 말"}]


def test_span_clamps_to_card():
    a, b = voice.span({"start": 10, "end": 14}, SPEECH)
    assert 9 <= a and b <= 15.5            # 30초짜리 말 덩어리라도 카드 시간 근처만
    assert voice.span({"start": 50, "end": 55}, SPEECH) is None


def test_record_and_kinds(tmp_path):
    rid, d = make_run()
    data = json.loads((d / "cards.json").read_text())
    assert all(c["voice"] is None for c in client.get(f"/api/runs/{rid}/cards").json()["cards"])
    r = client.post(f"/api/runs/{rid}/cards/1/voice", files={"file": ("v.webm", b"x" * 1000, "audio/webm")})
    assert r.status_code == 200 and client.get(f"/api/runs/{rid}/cards").json()["cards"][0]["voice"] == "rec"
    assert client.get(f"/api/runs/{rid}/voice/1").status_code == 200
    assert client.post(f"/api/runs/{rid}/cards/1/voice", files={"file": ("v.txt", b"x", "text/plain")}).status_code == 400
    assert client.delete(f"/api/runs/{rid}/cards/1/voice").json()["voice"] is None
    assert client.get(f"/api/runs/{rid}/voice/1").status_code == 404


def test_auto_voice_from_video(video):
    rid, d = make_run()
    sound = d / "with_audio.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x90:rate=10", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-shortest", "-pix_fmt", "yuv420p", "-c:a", "aac", str(sound)], check=True)
    p = json.loads((d / "progress.json").read_text()); p["video_path"] = str(sound); (d / "progress.json").write_text(json.dumps(p))
    (d / "speech.json").write_text(json.dumps([{"start": 0.0, "end": 2.5, "text": "컵을 놓으세요"}]))
    assert client.get(f"/api/runs/{rid}/cards").json()["cards"][0]["voice"] == "auto"
    r = client.get(f"/api/runs/{rid}/voice/1")
    assert r.status_code == 200 and (d / "voice" / "01_auto.m4a").exists()

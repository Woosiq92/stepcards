# 선생님 목소리: 카드마다 사람 목소리로 읽어 준다(기계 음성보다 익숙하게).
# ① 교사가 고치기 화면에서 직접 녹음한 것 ② 시범 영상 속 그 단계의 말소리(Muse Voice Transcribe 가 준 시각으로 자름) 순서로 쓰고,
# 둘 다 없으면 화면이 기기 음성으로 읽는다. 학생 목소리는 받지 않는다(녹음은 교사 화면에서만).
import json, subprocess
from pathlib import Path

MAX_SEC = 12        # 영상에서 자를 때 최대 길이
PAD = 0.3
REC_MAX_BYTES = 2_000_000
REC_TYPES = {"audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/mpeg": "mp3"}


def turns(d):
    f = d / "speech.json"
    try:
        return json.loads(f.read_text()) if f.exists() else []
    except ValueError:
        return []


def span(card, speech):
    """카드 구간 안에서 말소리가 있는 부분(시작, 끝). 받아쓰기 구간이 길어(수십 초) 카드 시간 밖의 말은 잘라 낸다. 없으면 None"""
    lo, hi = card["start"] - 1, card["end"] + 1.5
    hit = [t for t in speech if t["end"] > lo and t["start"] < hi]
    if not hit:
        return None
    a = max(lo, min(t["start"] for t in hit) - PAD, 0.0)
    b = min(hi, max(t["end"] for t in hit) + PAD, a + MAX_SEC)
    return (a, b) if b - a >= 1 else None


def recorded(d, n):
    return next(iter(sorted((d / "voice").glob(f"{n:02d}_rec.*"))), None) if (d / "voice").exists() else None


def video_path(d):
    try:
        v = Path(json.loads((d / "progress.json").read_text()).get("video_path") or "")
    except (OSError, ValueError):
        return None
    return v if v.is_file() else None


def has_audio(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True).stdout.strip()
    return bool(out)


def kinds(d, cards):
    """카드마다 쓸 수 있는 사람 목소리(화면에 알려 줌). 영상 소리 확인은 한 번만"""
    speech, video = turns(d), video_path(d)
    aud = bool(video and speech and has_audio(video))
    out = {}
    for c in cards:
        if recorded(d, c["n"]):
            out[c["n"]] = "rec"
        elif (d / "voice" / f"{c['n']:02d}_auto.m4a").exists() or (aud and span(c, speech)):
            out[c["n"]] = "auto"
        else:
            out[c["n"]] = None
    return out


def cut(d, card):
    """영상 속 그 단계의 말소리를 잘라 둔다(한 번만). 파일 경로 또는 None"""
    out = d / "voice" / f"{card['n']:02d}_auto.m4a"
    video, sp = video_path(d), span(card, turns(d))
    mark = out.with_suffix(".span")  # 어느 구간에서 잘랐는지: 카드 시간을 고치면 다시 자른다(옛 구간 소리가 나오지 않게)
    if out.exists() and (not video or (sp and mark.exists() and mark.read_text() == f"{sp[0]:.2f},{sp[1]:.2f}")):
        return out  # 영상이 이미 보관돼 없으면 남겨 둔 소리를 쓴다
    if not (video and sp and has_audio(video)):
        out.unlink(missing_ok=True)
        return None
    out.parent.mkdir(exist_ok=True)
    tmp = out.with_name("." + out.name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{sp[0]:.2f}", "-t", f"{sp[1] - sp[0]:.2f}", "-i", str(video), "-vn", "-ac", "1",
                    "-c:a", "aac", "-b:a", "48k", "-af", "loudnorm=I=-16:TP=-1.5", str(tmp)], check=True)
    tmp.replace(out)
    mark.write_text(f"{sp[0]:.2f},{sp[1]:.2f}")
    return out


def cut_all(d):
    """보관 전에: 영상이 지워져도 카드별 목소리는 남게"""
    data = json.loads((d / "cards.json").read_text())
    for c in data["cards"]:
        if not recorded(d, c["n"]):
            cut(d, c)

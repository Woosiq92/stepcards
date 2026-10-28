# 단계 JSON 검사기: 모델 없이 코드 규칙으로만 판정한다
import re

KEYS = ("start", "end", "rep", "ko", "en", "object", "look")
KO_MAX, EN_MAX = 25, 60
GAP_WARN = 15
TWO_ACTIONS = re.compile(r"[가-힣]+(고|며|면서)\s")  # "꽂고 저어주세요"처럼 동작이 이어지는 문장
# ㅅ 불규칙 동사는 '으' 앞에서 ㅅ이 빠진다(붓다→부으세요). 씻다·벗다는 규칙 동사라 받침 모양으로는 못 가려서 동사를 적어 둔다
S_IRREGULAR = {"붓": "부", "젓": "저", "긋": "그", "잇": "이", "짓": "지", "낫": "나"}
S_IRREGULAR_RE = re.compile("(" + "|".join(S_IRREGULAR) + ")으")
# ㄹ 받침 동사는 '으세요' 앞에서 ㄹ이 빠진다(털다→터세요, 만들다→만드세요). 받침 모양만으로 판정 가능
RIEUL_EU = re.compile("([가-힣])으세요")


def drop_rieul(ch):
    """'털' → '터'. ㄹ 받침이 아니면 None."""
    code = ord(ch) - 0xAC00
    return chr(ord(ch) - 8) if code % 28 == 8 else None


def check(steps, duration):
    """(고쳐야 할 문제 목록, 참고 경고 목록). 시각은 초 단위, 구간 끝 포함."""
    problems, warnings = [], []
    if not isinstance(steps, list) or len(steps) < 2:
        return ["단계가 2개 미만입니다."], warnings
    timed = []  # 시각이 숫자인 (번호, 단계)
    for i, s in enumerate(steps, 1):
        missing = [k for k in KEYS if k not in s]
        if missing:
            problems.append(f"{i}단계: {', '.join(missing)} 항목이 없습니다.")
            continue
        if not all(isinstance(s[k], (int, float)) for k in ("start", "end", "rep")):
            problems.append(f"{i}단계: start·end·rep는 숫자여야 합니다.")
            continue
        start, end, rep = s["start"], s["end"], s["rep"]
        if not (0 <= start < end <= duration):
            problems.append(f"{i}단계: 구간 {start}~{end}초가 영상(0~{duration}초) 밖이거나 끝이 시작보다 빠릅니다.")
        if not (start <= rep <= end):
            problems.append(f"{i}단계: 대표 시각 {rep}초가 구간 {start}~{end}초 밖입니다.")
        timed.append((i, s))
        ko = str(s["ko"]).strip()
        if not ko:
            problems.append(f"{i}단계: 한국어 문장이 비어 있습니다.")
        elif len(ko.replace(" ", "")) > KO_MAX:
            problems.append(f"{i}단계: 한국어 문장이 깁니다({len(ko.replace(' ', ''))}자, {KO_MAX}자 이하): {ko}")
        elif not ko.rstrip(".").endswith("세요"):
            problems.append(f"{i}단계: 한국어 문장은 '~세요'로 끝나야 합니다: {ko}")
        elif m := S_IRREGULAR_RE.search(ko):
            problems.append(f"{i}단계: 맞춤법이 틀렸습니다('{m.group(0)}' → '{S_IRREGULAR[m.group(1)]}으'): {ko}")
        elif (m := RIEUL_EU.search(ko)) and drop_rieul(m.group(1)):
            problems.append(f"{i}단계: 맞춤법이 틀렸습니다('{m.group(1)}으' → '{drop_rieul(m.group(1))}'): {ko}")
        elif TWO_ACTIONS.search(ko + " "):
            problems.append(f"{i}단계: 한 문장에 동작이 둘 이상입니다. 두 단계로 나누세요: {ko}")
        if len(str(s["en"])) > EN_MAX:
            problems.append(f"{i}단계: 영어 문장이 깁니다({EN_MAX}자 이하): {s['en']}")
    # 겹침·빈 구간은 시간순으로 본다. 사람이 카드 순서를 바꿔도 영상 속 시간은 그대로이기 때문
    timed.sort(key=lambda x: x[1]["start"])
    for (a, p), (b, s) in zip(timed, timed[1:]):
        if s["start"] <= p["end"]:
            problems.append(f"{a}·{b}단계: 구간이 겹칩니다({p['start']}~{p['end']}초와 {s['start']}~{s['end']}초). 다음 단계는 앞 단계 끝 다음 초부터 시작해야 합니다.")
        elif s["start"] - p["end"] > GAP_WARN:
            warnings.append(f"{a}·{b}단계 사이 {p['end']}~{s['start']}초가 비어 있습니다.")
    return problems, warnings

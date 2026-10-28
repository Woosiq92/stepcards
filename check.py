# 단계 JSON 검사기: 모델 없이 코드 규칙으로만 판정한다
import re

KEYS = ("start", "end", "rep", "ko", "en", "object", "look")
KO_MAX, EN_MAX = 25, 60
GAP_WARN = 15
TWO_ACTIONS = re.compile(r"[가-힣]+(고|며|면서)\s")  # "꽂고 저어주세요"처럼 동작이 이어지는 문장


def check(steps, duration):
    """(고쳐야 할 문제 목록, 참고 경고 목록). 시각은 초 단위, 구간 끝 포함."""
    problems, warnings = [], []
    if not isinstance(steps, list) or len(steps) < 2:
        return ["단계가 2개 미만입니다."], warnings
    prev = None
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
        if prev:
            if start <= prev["end"]:
                problems.append(f"{i - 1}·{i}단계: 구간이 겹칩니다({prev['start']}~{prev['end']}초와 {start}~{end}초). 다음 단계는 앞 단계 끝 다음 초부터 시작해야 합니다.")
            elif start - prev["end"] > GAP_WARN:
                warnings.append(f"{i - 1}·{i}단계 사이 {prev['end']}~{start}초가 비어 있습니다.")
        ko = str(s["ko"]).strip()
        if not ko:
            problems.append(f"{i}단계: 한국어 문장이 비어 있습니다.")
        elif len(ko.replace(" ", "")) > KO_MAX:
            problems.append(f"{i}단계: 한국어 문장이 깁니다({len(ko.replace(' ', ''))}자, {KO_MAX}자 이하): {ko}")
        elif not ko.rstrip(".").endswith("세요"):
            problems.append(f"{i}단계: 한국어 문장은 '~세요'로 끝나야 합니다: {ko}")
        elif TWO_ACTIONS.search(ko + " "):
            problems.append(f"{i}단계: 한 문장에 동작이 둘 이상입니다. 두 단계로 나누세요: {ko}")
        if len(str(s["en"])) > EN_MAX:
            problems.append(f"{i}단계: 영어 문장이 깁니다({EN_MAX}자 이하): {s['en']}")
        prev = s
    return problems, warnings

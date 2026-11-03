# 11-03: 문자열 안 큰따옴표 하나로 index.html 스크립트 전체가 죽은 채 푸시됐다. 페이지 스크립트가 문법상 열리는지 node 로 본다.
import re, shutil, subprocess
from pathlib import Path
import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_inline_script_parses():
    html = (Path(__file__).parent / "static" / "index.html").read_text()
    for body in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html):
        code = re.sub(r"^\s*import .*$", "", body, flags=re.M)
        r = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0, 'utf8'))"], input=code, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-400:]

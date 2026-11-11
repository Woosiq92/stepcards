# 자립노트 통합(11-11): 프록시 비밀값을 믿는 길과 앞 경로(/cards) 화면 주소 바꾸기
import os, tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="stepcards_test_"))
os.environ["MAINTENANCE"] = "0"
from fastapi.testclient import TestClient
import app as A

client = TestClient(A.app, raise_server_exceptions=False)
H = {"x-stepcards-proxy": "s3cret", "x-stepcards-user": "staff-abc"}


def test_proxy_secret_makes_teacher(monkeypatch):
    monkeypatch.setattr(A, "APP_KEY", "admin-key"); monkeypatch.setattr(A, "PROXY_SECRET", "s3cret")
    assert client.get("/api/me").json()["role"] is None
    assert client.get("/api/me", headers=H).json()["role"] == "teacher"
    assert client.get("/api/me", headers={**H, "x-stepcards-proxy": "wrong"}).json()["role"] is None
    assert client.get("/api/me", headers={**H, "x-stepcards-user": "a b<"}).json()["role"] is None  # 이름 꼴이 아니면 믿지 않는다
    assert client.post("/api/upload", files={"file": ("a.mp4", b"x")}).status_code == 401


def test_no_secret_configured_never_trusts(monkeypatch):
    monkeypatch.setattr(A, "APP_KEY", "admin-key"); monkeypatch.setattr(A, "PROXY_SECRET", "")
    assert client.get("/api/me", headers={**H, "x-stepcards-proxy": ""}).json()["role"] is None


def test_base_path_rewrites_page_urls(monkeypatch):
    monkeypatch.setattr(A, "BASE_PATH", "")
    plain = client.get("/").text
    assert 'window.SC_BASE=""' in plain and '"/api/me"' in plain
    html = client.get("/", headers={"x-stepcards-base": "/cards"}).text
    assert 'window.SC_BASE="/cards"' in html
    assert '"/cards/api/me"' in html and '"/api/me"' not in html and "`/cards/api/runs/" in html and '"/cards/static/fold3d.js"' in html
    assert "/school.html" in html  # 자립노트 쪽 주소는 그대로
    bad = client.get("/", headers={"x-stepcards-base": '/x"><script>'}).text  # 꼴이 아닌 값은 버린다
    assert 'window.SC_BASE=""' in bad
    g = client.get("/glasses", headers={"x-stepcards-base": "/cards"}).text
    assert "`/cards/api/runs/" in g and "`/api/runs/" not in g

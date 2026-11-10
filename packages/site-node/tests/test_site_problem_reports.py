"""问题单(日志设计 第 6 条,用户 11-10):App 上谁都能传日志,工程师按编号直接取整包,不经过管理员。"""

from __future__ import annotations

import gzip
import io
import tarfile
import urllib.error
import urllib.request

import pytest
from test_site_api import _等, 站

from nexwar_site.health import HealthDesk
from nexwar_site.problem_reports import CODE, PER_HOUR, ProblemReports, ReportRefused

LOG = gzip.compress("2026-11-10T08:00:00.000+08:00 E app 登录失败 token=abc\n".encode())


def _站(tmp_path):
    s = 站(tmp_path)
    s.api.health = HealthDesk(s.db, home=tmp_path, now_ms=s.api._now)
    s.api.problem_reports = ProblemReports(tmp_path / "problem-reports", now_ms=s.api._now)
    return s


def _传(s, *, token=None, q="note=%E7%99%BB%E4%B8%8D%E4%B8%8A&robot=A", data=LOG):
    r = urllib.request.Request(s.api.url + "/api/problem-reports?" + q, data=data, method="POST")
    r.add_header("Content-Type", "application/gzip")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            import json
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _取(s, path, token=None, headers=None):
    r = urllib.request.Request(s.api.url + path)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def test_不登录也能传_没有下载凭证_工程师按编号取整包里有App日志和说明(tmp_path):
    s = _站(tmp_path)
    try:
        code, d = _传(s)
        assert code == 200 and CODE.match(d["code"]) and "token" not in d, "不登录的不给凭证"
        tok = s.login()                                   # alice 是管理员,有 maintain
        code, lst = s.req("GET", "/api/problem-reports", token=tok)
        assert code == 200 and lst["reports"][0]["code"] == d["code"]
        assert lst["reports"][0]["note"] == "登不上" and "token_hash" not in lst["reports"][0]
        code, blob = _取(s, f"/api/problem-reports/{d['code']}/bundle", token=tok)
        assert code == 200
        with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
            names = tf.getnames()
            readme = tf.extractfile("nexwar_support/README.md").read().decode()
        assert f"nexwar_support/clients/app-{d['code']}.log.gz" in names
        assert d["code"] in readme and "登不上" in readme
        r = _等(lambda: next((r for r in s.api.audit.list() if r["target"] == d["code"]
                              and r["action"] == "POST /api/problem-reports"), None))
        assert r["actor"].startswith("anonymous@")
    finally:
        s.close()


def test_登录着传的拿凭证_凭证只管这一张_没权限的看不到列表(tmp_path):
    s = _站(tmp_path)
    try:
        tok = s.login()
        _, d = _传(s, token=tok)
        assert d["token"]
        assert _取(s, f"/api/problem-reports/{d['code']}/bundle?t={d['token']}")[0] == 200
        assert _取(s, f"/api/problem-reports/{d['code']}/bundle?t=wrong")[0] == 401
        _, d2 = _传(s, token=tok)
        assert _取(s, f"/api/problem-reports/{d2['code']}/bundle?t={d['token']}")[0] == 401
        assert _取(s, "/api/problem-reports")[0] == 401
    finally:
        s.close()


def test_不是gzip_太大_一小时传太多_都拒(tmp_path):
    p = ProblemReports(tmp_path, now_ms=lambda: 10**12)
    with pytest.raises(ReportRefused, match="gzip"):
        p.submit(data=b"plain", by="x", remote="1", signed_in=False)
    for _ in range(PER_HOUR):
        p.submit(data=LOG, by="x", remote="1", signed_in=False)
    with pytest.raises(ReportRefused) as e:
        p.submit(data=LOG, by="x", remote="1", signed_in=False)
    assert e.value.status == 429
    p.submit(data=LOG, by="x", remote="2", signed_in=False)   # 别的手机不受影响


def test_留90天(tmp_path):
    now = [10**12]
    p = ProblemReports(tmp_path, now_ms=lambda: now[0])
    p.submit(data=LOG, by="x", remote="1", signed_in=False)
    now[0] += 91 * 86_400_000
    assert p.prune() == 1 and p.list() == []


def test_值守令牌看不到问题单(tmp_path):
    s = _站(tmp_path)
    try:
        tok = s.login()
        code, w = s.req("POST", "/api/watch/token", {}, token=tok)
        assert code == 200
        assert s.req("GET", "/api/problem-reports", token=w["token"])[0] == 403
    finally:
        s.close()


def test_外审POC_I8_凭证放请求头取整包_日志里不出现凭证(tmp_path, caplog):
    """codex POC r1 I8:凭证放在 ``?t=`` 里,访问日志、诊断包里明文留着。新 App 放请求头;
    老 App 照旧 ``?t=``,但日志里打码。"""
    import logging
    s = _站(tmp_path)
    try:
        tok = s.login()
        _, d = _传(s, token=tok)
        path = f"/api/problem-reports/{d['code']}/bundle"
        with caplog.at_level(logging.INFO):
            assert _取(s, path, headers={"X-Problem-Token": d["token"]})[0] == 200
            assert _取(s, path, headers={"X-Problem-Token": "wrong"})[0] == 401
            assert _取(s, f"{path}?t={d['token']}")[0] == 200          # 老 App
        logged = "\n".join(r.getMessage() for r in caplog.records)
        assert d["code"] in logged, "访问照旧记"
        assert d["token"] not in logged
    finally:
        s.close()

"""1.1-4 远程喊话:保安按住说话 → 站点存下 → 发喇叭命令 ``talk:<编号>`` → 机器人拉下来放;
听回话:站点发 ``mic`` → 机器人录一段传回来 → 保安点开听。真 HTTP、真代理、仿真狗(带上装)。

- 说、听回话要 ``dispatch``(保安);管理员 403;没登录 401。
- 格式不认、太大的不收;老代理(能力里没 ``talk``)回 409,不发命令。
- 机器人只拉得到发给自己的;回话只收在等的那条。
- 录音只留一天,到点连文件带记录删;说了、听了都进审计。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from test_site_api import PW, _等, 站

from nexwar_site import talk as talk_mod
from nexwar_site.talk import TalkDesk


class 假链路:
    """代理这头的 :class:`~nexwar_agent.talk.TalkLink`,直接读站点的目录(不走 TLS、不转码)。"""

    def __init__(self, desk: TalkDesk, work: Path) -> None:
        self.desk, self.work = desk, work

    async def fetch(self, clip: str) -> Path:
        tid = clip.split(":", 1)[1]
        src = self.desk.for_robot("A", tid)
        assert src is not None, "站点不给"
        self.work.mkdir(parents=True, exist_ok=True)
        out = self.work / f"talk-{tid}.wav"
        out.write_bytes(src.read_bytes())
        return out

    async def upload(self, clip: str, data: bytes) -> None:
        assert self.desk.save_reply("A", clip.split(":", 1)[1], data)


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path, payload=True)
    s.accounts.add("gina", PW, role="guard")
    s.accounts.add("olga", PW, role="owner")
    s.talk = TalkDesk(s.db, tmp_path / "talk", now_ms=lambda: s.clock_ms)
    s.clock_ms = 1_000_000
    s.api.talk = s.talk
    s.agent.deter.talk = 假链路(s.talk, tmp_path / "agent-talk")
    yield s
    s.close()


def _登(s, name):
    code, d = s.req("POST", "/api/login", {"name": name, "password": PW})
    assert code == 200, d
    return d["token"]


def _说(s, tok, data=b"\0" * 2000, mime="audio/mp4"):
    r = urllib.request.Request(s.api.url + "/api/robots/A/talk", data=data, method="POST")
    r.add_header("Content-Type", mime)
    if tok:
        r.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def _听(s, tok, tid):
    r = urllib.request.Request(s.api.url + f"/api/talk/{tid}")
    r.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, None, b""


def _能喊(s, tok):
    def ok():
        tasks = (s.req("GET", "/api/robots/A", token=tok)[1].get("capabilities") or {}) \
            .get("tasks") or {}
        d = tasks.get("deter") or {}
        return s.req("GET", "/api/robots/A", token=tok)[1].get("fresh") and d.get("talk") \
            and "mic" in d.get("outputs", [])
    _等(ok)


def _发能力(s):
    async def go():
        await s.agent._publish_caps()
    s.loop.call(go)


def test_按住说话_站点存下_机器人拉下来放_进审计_自己能回放(站点):
    s = 站点
    _发能力(s)
    gina = _登(s, "gina")
    _能喊(s, gina)
    code, d = _说(s, gina, b"m4a-bytes" * 100)
    assert code == 200 and d["ack"]["result"] == "accepted", d
    tid = d["talk"]["id"]
    assert d["talk"]["direction"] == "out" and d["talk"]["account"] == "gina"
    _等(lambda: s.dog.deter_clip.startswith("talk:"))
    played = Path(s.dog.deter_clip[len("talk:"):])
    assert played.name == f"talk-{tid}.wav" and played.read_bytes() == b"m4a-bytes" * 100
    assert s.talk.get(tid)["state"] in ("sent", "fetched")
    code, mime, body = _听(s, gina, tid)
    assert code == 200 and mime == "audio/mp4" and body == b"m4a-bytes" * 100
    acts = [r["action"] for r in s.api.audit.list() if r["actor"] == "gina"]
    assert "POST /api/robots/A/talk" in acts
    row = [r for r in s.api.audit.list() if r["action"] == "POST /api/robots/A/talk"][-1]
    assert row["detail"]["talk"] == tid, "审计里记编号,不记声音"


def test_听回话_机器人录一段传回来_保安点开听(站点):
    s = 站点
    _发能力(s)
    gina = _登(s, "gina")
    _能喊(s, gina)
    code, d = s.req("POST", "/api/robots/A/listen", {"seconds": 5}, token=gina)
    assert code == 200 and d["ack"]["result"] == "accepted", d
    tid = d["talk"]["id"]
    _等(lambda: s.talk.get(tid)["state"] == "recorded")
    assert s.dog.recorded_s == 5.0
    code, mime, body = _听(s, gina, tid)
    assert code == 200 and mime == "audio/wav" and body[:4] == b"RIFF"
    code, d = s.req("GET", "/api/robots/A/talks", token=gina)
    assert code == 200 and [t["id"] for t in d["talks"]][0] == tid
    assert s.req("POST", "/api/robots/A/listen", {"seconds": 60}, token=gina)[0] == 400


def test_权限_格式_大小(站点):
    s = 站点
    _发能力(s)
    olga, gina = _登(s, "olga"), _登(s, "gina")
    _能喊(s, gina)
    assert _说(s, olga)[0] == 403
    assert _说(s, None)[0] == 401
    assert _说(s, gina, mime="text/plain")[0] == 400
    assert _说(s, gina, data=b"\0" * (talk_mod.MAX_BYTES + 1))[0] == 413
    assert s.req("POST", "/api/robots/A/listen", {}, token=olga)[0] == 403
    assert not s.dog.deter_on("speaker")


def test_老代理放不了录音_回409_记一条拒了(站点):
    s = 站点
    s.agent.deter.talk = None
    _发能力(s)
    gina = _登(s, "gina")
    _等(lambda: s.req("GET", "/api/robots/A", token=gina)[1].get("fresh"))
    _等(lambda: ((s.req("GET", "/api/robots/A", token=gina)[1].get("capabilities") or {})
                 .get("tasks", {}).get("deter") or {}).get("talk") is False)
    code, d = _说(s, gina)
    assert code == 409, d
    [row] = s.talk.list("A")
    assert row["state"] == "refused"


def test_机器人只拉得到发给自己的_回话只收在等的那条_一天后删(tmp_path):
    from nexwar_site.db import SiteDB
    now = [1_000_000]
    desk = TalkDesk(SiteDB(tmp_path / "s.db"), tmp_path / "talk", now_ms=lambda: now[0])
    out = desk.save_out("A", "gina", b"x" * 10, "audio/webm;codecs=opus")
    assert out["ext"] == "webm"
    assert desk.for_robot("B", out["id"]) is None, "别的机器人拉不到"
    assert desk.for_robot("A", out["id"]) is not None
    assert desk.for_robot("A", "0" * 16) is None
    want = desk.want_reply("A", "gina")
    assert not desk.save_reply("B", want["id"], b"RIFF"), "别的机器人传不进来"
    assert not desk.save_reply("A", out["id"], b"RIFF"), "说出去的那条不收回话"
    assert desk.save_reply("A", want["id"], b"RIFF....")
    assert not desk.save_reply("A", want["id"], b"RIFF"), "收过了不再收"
    with pytest.raises(talk_mod.TalkError):
        desk.save_out("A", "gina", b"", "audio/mp4")
    now[0] += talk_mod.KEEP_MS + 1
    assert desk.prune() == 2
    assert desk.list("A") == [] and list((tmp_path / "talk").iterdir()) == []


def test_外审1_1_第5条_文件删不掉_记录留着下次再删(tmp_path, monkeypatch):
    from pathlib import Path

    from nexwar_site.db import SiteDB
    now = [1_000_000]
    desk = TalkDesk(SiteDB(tmp_path / "s.db"), tmp_path / "talk", now_ms=lambda: now[0])
    out = desk.save_out("A", "gina", b"x" * 10, "audio/webm")
    now[0] += talk_mod.KEEP_MS + 1
    real = Path.unlink

    def no(self, missing_ok=False):
        raise PermissionError("只读")
    monkeypatch.setattr(Path, "unlink", no)
    assert desk.prune() == 0 and desk.get(out["id"])
    monkeypatch.setattr(Path, "unlink", real)
    assert desk.prune() == 1 and list((tmp_path / "talk").iterdir()) == []


def test_外审1_1_第11条_听回话没成标失败_等太久也标失败(tmp_path):
    from nexwar_contract.messages import Event
    from nexwar_site.db import SiteDB
    now = [1_000_000]
    desk = TalkDesk(SiteDB(tmp_path / "s.db"), tmp_path / "talk", now_ms=lambda: now[0])
    a, b = desk.want_reply("A", "gina"), desk.want_reply("A", "gina")

    def ev(clip, robot_ok=True):
        return Event(event_id=f"e-{clip}", seq=1, boot_id="b", stamp=1, kind="deter",
                     data={"output": "mic", "on": False, "ended": "failed",
                           "reason": "麦克风忙", "clip": f"talk:{clip}"})
    desk.on_event("B", ev(a["id"]))
    assert desk.get(a["id"])["state"] == "waiting", "别的机器人的事件不算"
    desk.on_event("A", ev(a["id"]))
    assert (desk.get(a["id"])["state"], desk.get(a["id"])["error"]) == ("failed", "麦克风忙")
    now[0] += talk_mod.REPLY_TIMEOUT_MS + 1
    [_, x] = sorted(desk.list("A"), key=lambda r: r["id"] != a["id"])
    assert x["id"] == b["id"] and x["state"] == "failed" and "超时" in x["error"]

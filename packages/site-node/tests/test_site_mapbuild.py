"""W75 方案 1:站点主机打包。机器人边走边传关键帧,站点收齐 ``kf.json`` 核对后在后台出图、登记。"""

from __future__ import annotations

import hashlib
import json
import sys
import textwrap

import pytest

from nexwar_site.db import SiteDB
from nexwar_site.evidence import PathRefused
from nexwar_site.mapbuild import KF_MANIFEST, STAGES, SiteMapBuilder, progress_pct
from nexwar_site.maps import MapCatalog


def _fake_builder(tmp_path, *, fail=False):
    """假的出图程序:跟 ``nexwar_loc build --from-keyframes`` 一样的参数、一样的进度行。"""
    f = tmp_path / "fake_build.py"
    f.write_text(textwrap.dedent(f"""
        import sys, pathlib
        a = sys.argv[1:]
        kd = pathlib.Path(a[a.index("--from-keyframes") + 1])
        out = pathlib.Path(a[a.index("--out") + 1])
        assert a[0] == "build" and "--work" in a
        assert (kd / "kf" / "00000.bin").read_bytes() == b"kf0"
        for s in ("关键帧", "回环", "点云"):
            print("@@进度", s, flush=True)
        if {fail!r}:
            print("回环工具炸了", flush=True)
            sys.exit(1)
        out.mkdir(parents=True)
        (out / "floor.pgm").write_bytes(b"P5")
        (out / "build.json").write_text("{{}}")
        print("@@进度 完成", flush=True)
    """))
    return [sys.executable, str(f)]


@pytest.fixture
def site(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    cat = MapCatalog(tmp_path, db, now_ms=lambda: 1000)
    with db.tx() as c:
        c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                  "issued_at, priority) VALUES ('c1','t1','A','mapping',?, 'alice', 1, 0)",
                  (json.dumps({"action": "start", "name": "y", "map_id": "yard",
                               "version": "3"}),))
    return tmp_path, cat


def _send(b, rel, data, robot="A", run="yard/3"):
    return b.put_chunk(robot, run, rel, offset=0, data=data, total=len(data))


def _manifest(files):
    return json.dumps({"map_id": "yard", "version": "3", "files": [
        {"name": n, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
        for n, d in files.items()]}).encode()


FILES = {"kf/00000.bin": b"kf0", "kf/index.txt": b"1 2 3\n", "live.json": b"{}",
         "lio.tum": b"x", "traj.tum": b"y"}


def _upload_all(b, files=FILES):
    for n, d in files.items():
        _send(b, n, d)
    _send(b, KF_MANIFEST, _manifest(files))


def test_收齐关键帧_核对清单_后台出图_登记成这一版_来源记机器人(site):
    home, cat = site
    done = []
    b = SiteMapBuilder(home, cat, runner=_fake_builder(home), on_done=done.append,
                       start_thread=False)
    _upload_all(b)
    assert b.status("yard", "3")["state"] == "queued"
    b.run_pending()
    ref = cat.get("yard", "3")
    assert {f.name for f in ref.files} == {"floor.pgm", "build.json"}
    row = cat.db.query("SELECT source, note FROM maps WHERE map_id='yard'")[0]
    assert row["source"] == "A" and "站点打包" in row["note"]
    st = b.status("yard", "3")
    assert st["state"] == "done" and st["pct"] == 100
    assert done == [{"robot_id": "A", "map_id": "yard", "version": "3", "ok": True,
                     "reason": ""}]


def test_没让它建的不收_路径不对的不收_清单对不上永远不收(site):
    home, cat = site
    b = SiteMapBuilder(home, cat, runner=_fake_builder(home), start_thread=False)
    with pytest.raises(PathRefused):
        _send(b, "kf/00000.bin", b"kf0", robot="B")
    for bad in ("../x", "kf/a/b", "kf/../../x", ".hidden", "kf/.x"):
        with pytest.raises(PathRefused):
            _send(b, bad, b"x")
    _send(b, "kf/00000.bin", b"kf0")
    with pytest.raises(PathRefused, match="不匹配"):
        _send(b, KF_MANIFEST, _manifest({"kf/00000.bin": b"kf1"}))      # 一样长、内容不同


def test_清单先到_文件还没传齐_等齐了再出图(site):
    home, cat = site
    b = SiteMapBuilder(home, cat, runner=_fake_builder(home), start_thread=False)
    _send(b, KF_MANIFEST, _manifest(FILES))
    assert b.status("yard", "3")["state"] == "uploading"
    for n, d in FILES.items():
        _send(b, n, d)
    assert b.status("yard", "3")["state"] == "queued"


def test_出图失败_说原因带日志尾巴_回调告诉站点_关键帧留着能重试(site):
    home, cat = site
    done = []
    b = SiteMapBuilder(home, cat, runner=_fake_builder(home, fail=True), on_done=done.append,
                       start_thread=False)
    _upload_all(b)
    b.run_pending()
    st = b.status("yard", "3")
    assert st["state"] == "failed" and "回环工具炸了" in st["reason"]
    assert done[0]["ok"] is False and "回环工具炸了" in done[0]["reason"]
    assert (home / "mapkf-in" / "A" / "yard" / "3" / "kf" / "00000.bin").is_file()
    b2 = SiteMapBuilder(home, cat, runner=_fake_builder(home), start_thread=False)
    assert b2.status("yard", "3")["state"] == "failed", "站点重启后不自己再跑一遍失败的"
    b2.retry("yard", "3")
    b2.run_pending()
    assert b2.status("yard", "3")["state"] == "done"


def test_站点重启_收齐了还没出的接着出(site):
    home, cat = site
    b = SiteMapBuilder(home, cat, runner=_fake_builder(home), start_thread=False)
    _upload_all(b)
    b2 = SiteMapBuilder(home, cat, runner=_fake_builder(home), start_thread=False)
    assert b2.status("yard", "3")["state"] == "queued"
    b2.run_pending()
    assert cat.get("yard", "3")


def test_进度_按阶段算百分比_阶段里按时间往前挪_不超过下一段的起点():
    assert [s for s, _ in STAGES][:2] == ["关键帧", "回环"]
    a = progress_pct("关键帧", 0.0)
    b = progress_pct("回环", 0.0)
    c = progress_pct("回环", 50.0)
    d = progress_pct("回环", 1e6)
    e = progress_pct("点云", 0.0)
    assert 0 <= a < b < c < d < e < progress_pct("完成", 0.0) == 100


class _台:
    def __init__(self):
        self.got, self.resolved = [], []

    def raise_alert(self, **kw):
        self.got.append(kw)

    def resolve_all(self, robot, kind, *, who):
        self.resolved.append((robot, kind))


def test_出完了告诉人_成了记一条建好了推给管理员工程师_没成报建图失败():
    from nexwar_site.alerts import LEVEL_OF, Level
    from nexwar_site.mapbuild import notify
    from nexwar_site.push import PUSH_ROUTES
    d = _台()
    notify(d, {"robot_id": "A", "map_id": "yard", "version": "3", "ok": True, "reason": ""})
    a = d.got[-1]
    assert a["kind"] == "map_ready" and a["robot"] == "A" and "yard" in a["title"]
    assert a["merge"] is False, "每一版都要推一次"
    assert LEVEL_OF["map_ready"] == Level.P3
    assert PUSH_ROUTES["map_ready"][0] == ("admin", "engineer")
    assert ("A", "map_failed") in d.resolved
    notify(d, {"robot_id": "A", "map_id": "yard", "version": "4", "ok": False,
               "reason": "回环工具炸了"})
    a = d.got[-1]
    assert a["kind"] == "map_failed" and "yard:4" in a["title"] and "回环工具炸了" in a["detail"]
    assert PUSH_ROUTES["map_failed"][0] == ("admin", "engineer")


def test_出图命令_配置里给了用配置的_没给看装没装出图组件(tmp_path):
    from nexwar_site.mapbuild import runner_from
    assert runner_from({"mapbuild": {"runner": ["/x/py", "-m", "y"]}}, default=tmp_path / "n") \
        == ["/x/py", "-m", "y"]
    assert runner_from({}, default=tmp_path / "n") is None
    (tmp_path / "n").write_text("#!/bin/sh\n")
    assert runner_from({}, default=tmp_path / "n") == [str(tmp_path / "n")]
    assert runner_from({"mapbuild": {"enabled": False}}, default=tmp_path / "n") is None


def test_阶段代号_每个阶段都有():
    from nexwar_site.mapbuild import STAGE_CODES
    assert {s for s, _ in STAGES} | {"完成"} == set(STAGE_CODES)

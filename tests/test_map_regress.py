"""建图回归台(tools/map_regress.py)的指标和比较。"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

_P = Path(__file__).resolve().parents[1] / "tools" / "map_regress.py"
_spec = importlib.util.spec_from_file_location("map_regress", _P)
mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mr)


def _loop(dz_back: float) -> tuple[np.ndarray, np.ndarray]:
    """直线去 20 m 再原路回来,回程高 ``dz_back``;每秒 1 m。"""
    x = np.r_[np.arange(0, 20, 0.5), np.arange(20, 0, -0.5)]
    z = np.r_[np.zeros(40), np.full(40, dz_back)]
    t = np.arange(len(x)) * 0.5
    return t, np.c_[x, np.zeros_like(x), z]


def test_同处高度差_去程回程差多少就报多少():
    t, xyz = _loop(0.1)
    d = mr.same_place_dz(t, xyz)
    assert d["n"] > 0 and abs(d["p50"] - 0.1) < 1e-9 and abs(d["max"] - 0.1) < 1e-9


def test_同处高度差_挨着的时刻不算_只走一趟就是零():
    t = np.arange(40) * 0.5
    xyz = np.c_[np.arange(40) * 0.5, np.zeros(40), np.linspace(0, 1, 40)]
    assert mr.same_place_dz(t, xyz) == {"n": 0, "p50": 0.0, "p95": 0.0, "max": 0.0}


def test_地面倾角_斜1度的地面报1度_墙和远处的台子不算():
    rng = np.random.default_rng(0)
    xy = rng.uniform(0, 9.9, (3000, 2))
    z = np.tan(math.radians(1.0)) * xy[:, 0]
    wall = np.c_[np.full(800, 5.0), rng.uniform(0, 9.9, 800), rng.uniform(0.5, 3, 800)]
    step = np.c_[rng.uniform(0, 9.9, 800), np.full(800, 9.5), rng.uniform(-0.3, -0.1, 800)]
    traj = np.c_[np.linspace(0, 9.9, 50), np.full(50, 5.0),
                 np.tan(math.radians(1.0)) * np.linspace(0, 9.9, 50) + 0.5]
    tl = mr.tile_tilts(np.r_[np.c_[xy, z], wall, step], traj, tile=10.0)
    assert len(tl) == 1 and abs(tl[0] - 1.0) < 0.1, tl


def test_平面图格子数_空地障碍未知路沿(tmp_path: Path):
    floor = np.array([[254, 0, 205], [254, 254, 0]], np.uint8)
    p = tmp_path / "floor.pgm"
    p.write_bytes(b"P5\n# c\n3 2\n255\n" + floor.tobytes())
    curb = tmp_path / "curb.pbm"
    curb.write_bytes(b"P4\n3 2\n" + bytes([0b10100000, 0b00000000]))
    g = mr.grid_counts(mr.read_pgm(p), mr.read_pgm(curb))
    assert g == {"free": 3, "occupied": 2, "unknown": 1, "curb": 2}


def test_pcd_binary_读出xyz(tmp_path: Path):
    pts = np.array([[1, 2, 3, 9], [4, 5, 6, 9]], np.float32)
    head = ("VERSION .7\nFIELDS x y z intensity\nSIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\n"
            "WIDTH 2\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS 2\nDATA binary\n")
    p = tmp_path / "m.pcd"
    p.write_bytes(head.encode() + pts.tobytes())
    assert np.allclose(mr.read_pcd_xyz(p), pts[:, :3])


def test_比较_超过容差才算变差_变好不算_缺的不判():
    base = {"mall3": {"traj": {"same_place_dz": {"p50": 0.047, "max": 0.062}}, "replay": {
        "trusted": 0.99}}}
    new = {"mall3": {"traj": {"same_place_dz": {"p50": 0.081, "max": 0.063}}, "replay": {
        "trusted": 1.0}}}
    rows = {r["metric"]: r for r in mr.compare(base, new) if r["bag"] == "mall3"}
    assert rows["traj.same_place_dz.p50"]["worse"]
    assert not rows["traj.same_place_dz.max"]["worse"]      # 0.001 在容差里
    assert not rows["replay.trusted"]["worse"]               # 变好
    assert not rows["traj.start_end_m"]["worse"]             # 两边都没有


def test_回放算不过来_定位结果作废_比较时不算变差(tmp_path: Path):
    m, w, r = tmp_path / "map", tmp_path / "map.work", tmp_path / "replay"
    for d in (m, w, r):
        d.mkdir()
    (m / "build.json").write_text('{"mola": {"quality": {"path_m": 10}, "level": {}}}')
    (w / "traj.tum").write_text("0 0 0 0 0 0 0 1\n1 1 0 0 0 0 0 1\n")
    (m / "floor.pgm").write_bytes(b"P5\n2 1\n255\n" + bytes([254, 0]))
    import json
    (r / "metrics.json").write_text(json.dumps({"frames": 755, "rate_hz": 3.65,
                                                "agent_trusted_share": 0.0, "jumps": 707}))
    got = mr.bag_metrics(m, w, r)
    assert "invalid" in got["replay"] and "trusted" not in got["replay"]
    base = {"office1": {"replay": {"trusted": 1.0, "jumps": 0}}}
    rows = mr.compare(base, {"office1": got})
    assert not any(x["worse"] for x in rows if x["metric"].startswith("replay."))
    assert "作废" in mr.report_md({"office1": got})


def test_站点那条路_先出关键帧再从关键帧打包_不带后雷达(tmp_path: Path):
    spec = {"name": "tg", "bag": "/b/tg", "rear_lidars": "/b/lidars.json"}
    live, pack = mr.site_cmds(spec, tmp_path, "/usr/bin/python3", Path("/r/tg/map.work/lio_bag"))
    assert live[3:] == ["live-from-bag", "--bag", "/b/tg", "--lio", "/r/tg/map.work/lio_bag",
                        "--out", str(tmp_path / "live")]
    assert pack[3:6] == ["build", "--from-keyframes", str(tmp_path / "live")]
    assert "--rear-lidars" not in pack and "--replay" not in pack


def test_比较_站点打包跟录包建图不能混着比(tmp_path: Path):
    import json

    import pytest
    for name, site in (("a", False), ("b", True)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "results.json").write_text(json.dumps({"site": site, "bags": {}}))
    with pytest.raises(SystemExit, match="同一条路"):
        mr.main(["compare", str(tmp_path / "a"), str(tmp_path / "b")])

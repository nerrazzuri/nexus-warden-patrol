"""W44 第四期:地图编辑(橡皮擦、画障碍,另存新版本)、显示设置(摆正、底图、区域命名、特殊地面)、
网页上换图要再输密码。"""

from __future__ import annotations

import json
import urllib.request

import pytest
from test_site_api import MAP, PW, 站
from test_site_intercept_reach import _屋子
from test_site_maps import _files

from nexwar_site import map_edit as me
from nexwar_site import map_preview as mp
from nexwar_site.areas import AreaBook
from nexwar_site.map_display import DisplayError, check

# 屋子:8 m × 4 m,分辨率 0.1,x=4 m 处一道墙(门 1.6 m 宽),外圈一圈墙
META = {"resolution": 0.1, "origin": [0.0, 0.0, 0.0], "negate": 0, "occupied_thresh": 0.65,
        "free_thresh": 0.196}


def _图(tmp_path):
    src = _files(tmp_path / "m")
    _屋子(src, 1.6)
    return (src / "floor.pgm").read_bytes()


def _值(pgm, x, y):
    w, h, body = mp.parse_pgm(pgm)
    c, r = int(x / 0.1), h - 1 - int(y / 0.1)
    return body[r * w + c]


def test_橡皮擦改成空地(tmp_path):
    pgm = _图(tmp_path)
    assert _值(pgm, 4.0, 0.5) == 0                      # 墙
    ops = me.check_ops([{"op": "erase", "shape": "stroke", "points": [[4.0, 0.3], [4.0, 1.0]],
                         "width_m": 0.4}])
    new, st = me.apply_ops(pgm, META, ops)
    assert _值(new, 4.0, 0.5) == 254 and st["erased_m2"] > 0 and st["obstacle_m2"] == 0


def _块(pgm):
    """屋里 (1.5–2.0, 1.5–2.0) 画一块障碍(当作要擦掉的杂物)。"""
    ops = me.check_ops([{"op": "obstacle", "shape": "rect", "points": [[1.5, 1.5], [2.0, 2.0]]}])
    return me.apply_ops(pgm, META, ops)[0]


LOOP = [[1.0, 1.0], [2.6, 1.0], [2.6, 2.6], [1.0, 2.6], [1.1, 1.05]]


def test_W61_画笔圈一圈_圈里面整块擦掉(tmp_path):
    """用户 2026-11-01:用画笔把杂物圈起来,擦的只是笔划那一圈,圈里面的没动。
    首尾接上就是圈:里面一起擦。"""
    pgm = _块(_图(tmp_path))
    assert _值(pgm, 1.75, 1.75) == 0
    ops = me.check_ops([{"op": "erase", "shape": "stroke", "points": LOOP, "width_m": 0.1}])
    new, st = me.apply_ops(pgm, META, ops)
    assert _值(new, 1.75, 1.75) == 254
    assert 0.2 <= st["erased_m2"] <= 0.4                 # 实际改了的那块(0.5 × 0.5),不是整圈面积


def test_W61_没首尾接上的画笔_照旧只擦笔划(tmp_path):
    pgm = _块(_图(tmp_path))
    ops = me.check_ops([{"op": "erase", "shape": "stroke", "points": LOOP[:-1], "width_m": 0.1}])
    new, _ = me.apply_ops(pgm, META, ops)
    assert _值(new, 1.75, 1.75) == 0


def test_W61_只擦本来就是空地的_统计是0_不虚报(tmp_path):
    pgm = _图(tmp_path)
    ops = me.check_ops([{"op": "erase", "shape": "stroke", "points": [[1.0, 1.0], [2.0, 1.0]],
                         "width_m": 0.4}])
    _, st = me.apply_ops(pgm, META, ops)
    assert st["erased_m2"] == 0


def test_W61_圈出来画障碍_里面整块变占用(tmp_path):
    pgm = _图(tmp_path)
    ops = me.check_ops([{"op": "obstacle", "shape": "stroke", "points": LOOP, "width_m": 0.1}])
    new, st = me.apply_ops(pgm, META, ops)
    assert _值(new, 1.75, 1.75) == 0 and st["obstacle_m2"] > 2.0


def test_画障碍改成占用_直线和方框(tmp_path):
    pgm = _图(tmp_path)
    ops = me.check_ops([{"op": "obstacle", "shape": "line", "points": [[1.0, 1.0], [2.0, 1.0]],
                         "width_m": 0.1},
                        {"op": "obstacle", "shape": "rect", "points": [[5.0, 3.0], [5.5, 3.5]]}])
    new, st = me.apply_ops(pgm, META, ops)
    assert _值(new, 1.5, 1.0) == 0 and _值(new, 5.25, 3.25) == 0
    assert _值(new, 1.5, 2.0) == 254
    assert st["obstacle_m2"] > 0.25


@pytest.mark.parametrize("bad", [[], [{"op": "paint", "shape": "stroke", "points": [[0, 0]]}],
                                 [{"op": "erase", "shape": "rect", "points": [[0, 0]]}],
                                 [{"op": "erase", "shape": "stroke", "points": [[0, 0]],
                                   "width_m": 5}],
                                 [{"op": "erase", "shape": "stroke", "points": [[0, 0]]}] * 501])
def test_操作不合规矩(bad):
    with pytest.raises(me.EditError):
        me.check_ops(bad)


# ------------------------------------------------------------ 接口


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path, alerts=True, maps={})
    s.accounts.add("gina", PW, role="guard")
    src = _files(tmp_path / "mapsrc")
    _屋子(src, 1.6)
    s.maps.import_dir(src, map_id=MAP[0], version=MAP[1])
    s.api.areas = AreaBook(s.db, now_ms=lambda: 1)
    s.api.home = tmp_path / "home"
    s.api.home.mkdir()
    yield s
    s.close()


def _登(s, name="alice"):
    return s.req("POST", "/api/login", {"name": name, "password": PW})[1]["token"]


ADM = f"/api/admin/maps/{MAP[0]}/{MAP[1]}"
ERASE = [{"op": "erase", "shape": "stroke", "points": [[4.0, 0.3], [4.0, 1.0]], "width_m": 0.4}]


def test_只另存新版本_原版不动(站点):
    s = 站点
    tok = _登(s)
    dg = s.req("GET", f"{ADM}/noise", token=tok)[1]["digest"]
    before = (s.maps.root / MAP[0] / MAP[1] / "floor.pgm").read_bytes()
    code, d = s.req("POST", f"{ADM}/edit", {"digest": dg, "ops": ERASE}, token=tok)
    assert code == 200, d
    assert d["version"] != MAP[1] and d["erased_m2"] > 0
    assert (s.maps.root / MAP[0] / MAP[1] / "floor.pgm").read_bytes() == before
    new = (s.maps.root / MAP[0] / d["version"] / "floor.pgm").read_bytes()
    assert _值(new, 4.0, 0.5) == 254


def test_栅格换了不让存(站点):
    s = 站点
    code, d = s.req("POST", f"{ADM}/edit", {"digest": "0" * 16, "ops": ERASE}, token=_登(s))
    assert code == 409


def test_权限(站点):
    s = 站点
    gina = _登(s, "gina")
    assert s.req("POST", f"{ADM}/edit", {"digest": "x", "ops": ERASE}, token=gina)[0] == 403
    assert s.req("POST", f"{ADM}/display", {}, token=gina)[0] == 403


def test_存显示设置读回来_预览带上(站点):
    s = 站点
    tok = _登(s)
    body = {"rotate_deg": 12.5, "regions": [{"name": "A区", "polygon": [[0, 0], [2, 0], [2, 2]]}]}
    code, d = s.req("POST", f"{ADM}/display", body, token=tok)
    assert code == 200, d
    assert s.req("GET", f"{ADM}/display", token=tok)[1]["regions"][0]["name"] == "A区"
    pv = s.req("GET", f"/api/maps/{MAP[0]}/{MAP[1]}/preview", token=_登(s, "gina"))[1]
    assert pv["rotation_deg"] == 12.5 and pv["display"]["regions"][0]["name"] == "A区"


@pytest.mark.parametrize("bad", [{"rotate_deg": 200}, {"regions": [{"name": "", "polygon": []}]},
                                 {"terrain": [{"id": "a", "kind": "lava", "polygon": []}]},
                                 {"basemap": {"file": "../x.png"}}])
def test_显示设置不合规矩(bad):
    with pytest.raises(DisplayError):
        check(bad)


def test_楼梯默认放慢_生成限速区_草地不放慢_删了只删它生成的(站点):
    s = 站点
    tok = _登(s)
    zp = f"/api/maps/{MAP[0]}/{MAP[1]}/zones"
    hand = {"id": "lawn", "kind": "slow", "max_speed_mps": 0.5,
            "polygon": [[6, 3], [7, 3], [7, 3.8]]}
    s.req("POST", zp, {"zones": [hand], "base_revision": 0}, token=tok)
    sq = [[1, 1], [2, 1], [2, 2], [1, 2]]
    code, d = s.req("POST", f"{ADM}/display", {"terrain": [
        {"id": "s1", "kind": "stairs", "polygon": sq},
        {"id": "g1", "kind": "grass", "polygon": sq}]},
        token=tok)
    assert code == 200, d
    assert d["terrain"][0]["slow_mps"] == 0.3 and d["terrain"][1]["slow_mps"] is None
    zs = s.req("GET", zp, token=tok)[1]["zones"]
    assert {z["id"] for z in zs} == {"lawn", "t-s1"}
    assert next(z for z in zs if z["id"] == "t-s1")["max_speed_mps"] == 0.3
    s.req("POST", f"{ADM}/display", {"terrain": []}, token=tok)
    assert [z["id"] for z in s.req("GET", zp, token=tok)[1]["zones"]] == ["lawn"]


def _传(s, tok, data, ctype):
    r = urllib.request.Request(s.api.url + f"{ADM}/basemap", data=data, method="POST")
    r.add_header("Content-Type", ctype)
    r.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def test_底图上传和大小限制(站点):
    s = 站点
    tok = _登(s)
    code, d = _传(s, tok, b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")
    assert code == 200 and d["file"] == "basemap.png"
    assert (s.api.home / "map-display" / MAP[0] / MAP[1] / "basemap.png").is_file()
    assert _传(s, tok, b"GIF89a", "image/gif")[0] == 400
    assert _传(s, tok, b"not png", "image/png")[0] == 400


def test_区域命名_报警写在A区_没命名用防区名(站点):
    from nexwar_site.alert_sources import SiteAlertSources
    from nexwar_site.map_display import MapDisplay
    s = 站点
    disp = MapDisplay(s.db, now_ms=lambda: 1)
    disp.put(MAP[0], MAP[1], {"regions": [{"name": "A区", "polygon": [[0, 0], [2, 0], [2, 2],
                                                                       [0, 2]]}]}, by="a")
    s.api.areas.set(MAP[0], MAP[1], "西区", [[5, 0], [8, 0], [8, 4], [5, 4]], by="a")
    assert disp.region_at(MAP[0], MAP[1], 1, 1) == "A区"
    assert disp.region_at(MAP[0], MAP[1], 6, 1) is None
    src = SiteAlertSources(s.desk, now_ms=lambda: 1)
    src.where_of = lambda p: (disp.region_at(p["map_id"], p["map_version"], p["x"], p["y"])
                              or s.api.areas.zone_at(p["map_id"], p["map_version"], p["x"], p["y"]))
    src._mem["A"] = type("M", (), {"pose": {"map_id": MAP[0], "map_version": MAP[1], "x": 6.0,
                                            "y": 1.0}, "pose_ms": 1, "running": False,
                                   "started": None})()
    assert src.here("A")["where"] == "西区"


# ---- 外审 R4:按地图自己的编码写空地 / 障碍(negate=1 的图 0 是空地) ----

def _三乘三(negate, fill):
    meta = {"resolution": 1.0, "origin": [0, 0, 0], "negate": negate,
            "occupied_thresh": 0.65, "free_thresh": 0.196}
    return b"P5\n3 3\n255\n" + bytes([fill] * 9), meta


@pytest.mark.parametrize("negate,free", [(0, 254), (1, 0)])
def test_外审R4_画障碍按编码写成占用_规划读出来是墙(negate, free):
    pgm, meta = _三乘三(negate, free)
    ops = me.check_ops([{"op": "obstacle", "shape": "rect", "points": [[1, 1], [2, 2]]}])
    out, stats = me.apply_ops(pgm, meta, ops)
    r = mp.grid_ranks(out, meta)
    assert stats["obstacle_m2"] == 1.0
    assert r[1, 1] == 0                                  # 占用
    assert r[0, 0] == 1 and r[2, 2] == 1                 # 别处还是空地


@pytest.mark.parametrize("negate,occ", [(0, 0), (1, 255)])
def test_外审R4_擦掉按编码写成空地(negate, occ):
    pgm, meta = _三乘三(negate, occ)
    ops = me.check_ops([{"op": "erase", "shape": "rect", "points": [[1, 1], [2, 2]]}])
    out, _ = me.apply_ops(pgm, meta, ops)
    r = mp.grid_ranks(out, meta)
    assert r[1, 1] == 1 and r[0, 0] == 0


@pytest.mark.parametrize("negate", [0, 1])
def test_外审R4_图上一格空地都没有_擦掉照样是空地(negate):
    pgm, meta = _三乘三(negate, 205 if negate == 0 else 50)   # 全是未知
    assert set(mp.grid_ranks(pgm, meta).ravel()) == {2}
    ops = me.check_ops([{"op": "erase", "shape": "rect", "points": [[1, 1], [2, 2]]}])
    out, _ = me.apply_ops(pgm, meta, ops)
    assert mp.grid_ranks(out, meta)[1, 1] == 1


def test_外审R4_阈值让某一种写不出来_明确拒绝():
    pgm, meta = _三乘三(0, 254)
    meta["occupied_thresh"] = 1.0                        # 没有哪个灰度算占用
    ops = me.check_ops([{"op": "obstacle", "shape": "rect", "points": [[1, 1], [2, 2]]}])
    with pytest.raises(me.EditError):
        me.apply_ops(pgm, meta, ops)


def test_外审R4_写不出来接口回400不是500(站点, monkeypatch):
    s = 站点
    tok = _登(s)
    dg = s.req("GET", f"{ADM}/noise", token=tok)[1]["digest"]

    def 写不出(*a, **k):
        raise me.EditError("这张图的 floor.yaml 阈值下没有哪个灰度算障碍,改不了")
    monkeypatch.setattr(me, "apply_ops", 写不出)
    code, d = s.req("POST", f"{ADM}/edit", {"digest": dg, "ops": ERASE}, token=tok)
    assert code == 400 and "改不了" in d["error"]


def test_网页P0_13_另存新版本_区域_特殊地面_底图都跟过去(站点):
    """网页易用性第 1 轮 P0-13:另存新版本以后,命名区域、特殊地面、底图都没了(显示设置只存在原版本
    上,底图文件也在原版本目录里)。站点另存时一起复制过去;清噪点出来的版本也一样。"""
    s = 站点
    tok = _登(s)
    assert _传(s, tok, b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")[0] == 200
    body = {"rotate_deg": 5, "basemap": {"file": "basemap.png", "x": 0, "y": 0, "scale": 0.05,
                                        "rotate_deg": 0, "opacity": 0.5},
            "regions": [{"name": "A区", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]}],
            "terrain": [{"id": "t-1", "kind": "grass",
                         "polygon": [[5, 0], [7, 0], [7, 2], [5, 2]]}]}
    code, d = s.req("POST", f"{ADM}/display", body, token=tok)
    assert code == 200, d
    want = s.req("GET", f"{ADM}/display", token=tok)[1]
    dg = s.req("GET", f"{ADM}/noise", token=tok)[1]["digest"]
    code, d = s.req("POST", f"{ADM}/edit", {"digest": dg, "ops": ERASE}, token=tok)
    assert code == 200, d
    nv = f"/api/admin/maps/{MAP[0]}/{d['version']}"
    got = s.req("GET", f"{nv}/display", token=tok)[1]
    assert got == want
    assert (s.api.home / "map-display" / MAP[0] / d["version"] / "basemap.png").is_file()


def test_第2轮_底图上传后同一条连接上的下一个请求照常(站点):
    """网页易用性第 2 轮(P0-13 残留 / P1-54):底图用 rfile.read 读体、没记账,收尾的 _drain
    以为体还没读又去读,把同一条 keep-alive 连接上的下一个请求吞了 —— 上传底图后另存,区域、
    特殊地面、底图全丢,页面停在旧版本也不报错。"""
    import http.client

    s = 站点
    tok = _登(s)
    host, port = s.api.httpd.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=5)
    body = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    conn.request("POST", f"{ADM}/basemap", body=body,
                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/png"})
    r1 = conn.getresponse()
    assert r1.status == 200 and json.loads(r1.read())["file"] == "basemap.png"
    conn.request("GET", "/api/robots", headers={"Authorization": f"Bearer {tok}"})
    r2 = conn.getresponse()
    assert r2.status == 200, r2.read()
    assert "robots" in json.loads(r2.read())
    conn.close()


def test_第2轮_N4_另存新版本_防区_出口线_藏匿点_防区路线_路网都复制过去_原版不动(站点):
    """网页易用性第 2 轮 N4(P0-14 残留):编辑、清噪点另存的新版本跟原版同一个坐标系,原来只带了
    显示设置 —— 防区、出口线、藏匿点、路网、人挪过的防区查看点 / 值守位在新版本上全是空的。
    另存时复制过去(原版照旧,还在原版上的机器人不受影响)。"""
    from nexwar_site.api import map_marks, zone_posts

    s = 站点
    tok = _登(s)
    a = s.api
    sq = [[0.5, 0.5], [3.0, 0.5], [3.0, 1.5], [0.5, 1.5]]
    a.areas.set(MAP[0], MAP[1], "东区", sq, by="t")
    marks = map_marks(a)
    marks.set(MAP[0], MAP[1], {"kind": "exit", "name": "东门", "points": [[1, 0.6], [2, 0.6]]},
              by="t")
    marks.set(MAP[0], MAP[1], {"kind": "hide", "name": "柱后", "points": [[2.5, 1.0]]}, by="t")
    posts = zone_posts(a)
    auto = next(p for p in posts.view(MAP[0], MAP[1]) if p["zone"] == "东区")
    if auto["view"] and auto["watch"]:
        posts.set(MAP[0], MAP[1], "东区", view=auto["view"], watch=auto["watch"], by="t")
    nets = a.route_nets
    if nets is not None:
        nets.put(MAP[0], MAP[1], {"base_revision": 0,
                                  "nodes": [{"id": "n1", "x": 1.0, "y": 1.0},
                                            {"id": "n2", "x": 2.0, "y": 1.0}],
                                  "edges": [["n1", "n2"]]}, by="t")
    dg = s.req("GET", f"{ADM}/noise", token=tok)[1]["digest"]
    code, d = s.req("POST", f"{ADM}/edit", {"digest": dg, "ops": ERASE}, token=tok)
    assert code == 200, d
    nv = d["version"]
    assert [x["zone"] for x in a.areas.list(MAP[0], nv)] == ["东区"]
    got = marks.list(MAP[0], nv)
    assert sorted((m["kind"], m["name"]) for m in got) == [("exit", "东门"), ("hide", "柱后")]
    assert {m["id"] for m in got}.isdisjoint({m["id"] for m in marks.list(MAP[0], MAP[1])})
    if auto["view"] and auto["watch"]:
        assert next(p for p in posts.view(MAP[0], nv) if p["zone"] == "东区")["auto"] is False
    if nets is not None:
        assert len(nets.get(MAP[0], nv).nodes) == 2
    # 原版不动
    assert [x["zone"] for x in a.areas.list(MAP[0], MAP[1])] == ["东区"]
    assert len(marks.list(MAP[0], MAP[1])) == 2
    assert d["layout_copied"] == {"areas": 1, "marks": 2, "posts": 1, "net_nodes": 2, "nogo": 0}


def test_第3轮_N1_另存新版本_禁行区从来源版本照抄_没确认_有待核建议时不许确认空集(站点):
    """第 3 轮 maps N1(P0):禁行区原来只当「待核建议」带过去(而且取的是登记时刻上的前一版,不是来源),
    网页看不到也采纳不了,确认就确认了一个空集 → 发布后禁区全丢。现在另存直接从来源版本照抄
    (没确认,发布前照样要确认);有待核的禁行区建议时,确认空集要拒绝。"""
    s = 站点
    tok = _登(s)
    z = s.api.zones
    pool = {"id": "pool", "kind": "nogo", "label": "泳池",
            "polygon": [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5]]}
    z.put(MAP[0], MAP[1], [pool], base_revision=z.current(MAP[0], MAP[1]).revision, by="t")
    dg = s.req("GET", f"{ADM}/noise", token=tok)[1]["digest"]
    code, d = s.req("POST", f"{ADM}/edit", {"digest": dg, "ops": ERASE}, token=tok)
    assert code == 200, d
    nv = d["version"]
    assert d["layout_copied"]["nogo"] == 1
    v = s.req("GET", f"/api/maps/{MAP[0]}/{nv}/zones", token=tok)[1]
    assert [x["id"] for x in v["zones"]] == ["pool"]
    assert not (v.get("confirmed") or {}).get("current")              # 抄过来的没确认
    assert not (v.get("proposal") or {}).get("zones")                 # 禁行区不再是建议
    # 有待核禁行区建议、当前一个都没有:确认空集拒绝(带 empty_ok 也不行)
    z.put(MAP[0], nv, [], base_revision=v["revision"], by="t")
    with s.api.dispatcher.db.tx() as tx:
        tx.execute("INSERT OR REPLACE INTO nav_zone_proposals(map_id, map_version, from_version, "
                   "body, created_ms, state) VALUES (?,?,?,?,?,'open')",
                   (MAP[0], nv, MAP[1], json.dumps({"zones": [pool], "standby": [],
                                                    "intercepts": []}), 1))
    rev = s.req("GET", f"/api/maps/{MAP[0]}/{nv}/zones", token=tok)[1]["revision"]
    code, d = s.req("POST", f"/api/maps/{MAP[0]}/{nv}/zones/confirm",
                    {"revision": rev, "confirm": True, "empty_ok": True}, token=tok)
    assert code == 409 and d.get("reason") == "proposal_open", d


def test_第2轮_N4_布置计数_发布弹窗拿来比(站点):
    from nexwar_site.api import map_marks

    s = 站点
    tok = _登(s)
    s.api.areas.set(MAP[0], MAP[1], "东区", [[0.5, 0.5], [3.0, 0.5], [3.0, 1.5], [0.5, 1.5]],
                    by="t")
    map_marks(s.api).set(MAP[0], MAP[1], {"kind": "hide", "name": "柱后",
                                          "points": [[2.5, 1.0]]}, by="t")
    code, d = s.req("GET", f"{ADM}/layout", token=tok)
    assert code == 200, d
    assert d["areas"] == 1 and d["hides"] == 1 and d["exits"] == 0
    assert set(d) >= {"posts", "net_nodes", "nogo", "cameras", "standby", "proposal"}
    # 第 4 轮 maps N4:按名字比、区域分种类、待核的是哪几个
    assert d["names"]["areas"] == ["东区"]
    assert set(d["names"]) == {"areas", "nogo", "standby"}
    assert set(d["proposed"]) == {"nogo", "standby"}
    assert isinstance(d["kinds"], dict)
    assert s.req("GET", f"{ADM}/layout", token=_登(s, "gina"))[0] == 403
    # 第 3 轮 r2-setup-N4:放在图上的摄像头也算
    before = d["cameras"]
    with s.api.dispatcher.db.tx() as tx:
        tx.execute("INSERT INTO cameras(name, onvif_url, zone, added_ms, map_id, map_version, "
                   "x, y, yaw) VALUES ('gate', 'http://1.2.3.4', '东区', 1, ?, ?, 1.0, 1.0, 0)",
                   MAP)
    assert s.req("GET", f"{ADM}/layout", token=tok)[1]["cameras"] == before + 1


def test_11_10_没发布过的编辑草稿再编辑_用新版替换它_发布前只有一个新版本(站点):
    """用户 11-10:「之前一直都是单独保存的所以才有那么多版本」。从编辑另存出来、没有机器人换上过、
    没挂巡逻路线的草稿,再编辑另存:新版本替换掉草稿(草稿删掉,区域照抄过来);原版、换上过的版本永远不动。"""
    s = 站点
    tok = _登(s)
    z = s.api.zones

    def edit(v):
        dg = s.req("GET", f"/api/admin/maps/{MAP[0]}/{v}/noise", token=tok)[1]["digest"]
        code, d = s.req("POST", f"/api/admin/maps/{MAP[0]}/{v}/edit", {"digest": dg, "ops": ERASE},
                        token=tok)
        assert code == 200, d
        return d

    def versions():
        return sorted(m["version"] for m in s.maps.list() if m["map_id"] == MAP[0])

    d1 = edit(MAP[1])                                       # 原版 → 草稿:原版不动,不替换
    v1 = d1["version"]
    assert "replaced" not in d1 and versions() == sorted([MAP[1], v1])
    pool = {"id": "pool", "kind": "nogo", "label": "泳池",
            "polygon": [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5]]}
    z.put(MAP[0], v1, [pool], base_revision=z.current(MAP[0], v1).revision, by="t")
    z.confirm(MAP[0], v1, revision=z.current(MAP[0], v1).revision, by="alice")
    d2 = edit(v1)                                           # 草稿再编辑:替换
    v2 = d2["version"]
    assert d2["replaced"] == v1 and versions() == sorted([MAP[1], v2]), versions()
    assert [x.id for x in z.current(MAP[0], v2).zones] == ["pool"], "草稿上画的禁行区跟过来"
    assert z.confirmed_current(MAP[0], v2), "草稿上确认过的,新版本照样算确认过"
    note = next(m for m in s.maps.list() if m["map_id"] == MAP[0] and m["version"] == v2)["note"]
    assert f"从 {MAP[1]} 编辑" in note, note
    # 换上过(下发过换图)的草稿:不替换
    with s.api.dispatcher.db.tx() as tx:
        tx.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                   "issued_at, ack_result) VALUES ('c1','t1','A','map_activate',?,'alice',1,"
                   "'accepted')", (json.dumps({"map_id": MAP[0], "version": v2}),))
    d3 = edit(v2)
    assert "replaced" not in d3 and v2 in versions()
    # 挂了巡逻路线的草稿:不替换(路线不跟着走)
    v3 = d3["version"]
    with s.api.dispatcher.db.tx() as tx:
        tx.execute("INSERT INTO routes(route_id, map_id, map_version, definition, revision, "
                   "updated_ms) VALUES ('r1', ?, ?, '{}', 1, 1)", (MAP[0], v3))
    d4 = edit(v3)
    assert "replaced" not in d4 and v3 in versions()

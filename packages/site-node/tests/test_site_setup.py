"""W53:开站清单(站点按数据判断每一项)、上手向导的记录(按账号存)。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_site_api import PW, _等, 站

from nexwar_site.db import SiteDB
from nexwar_site.setup import GuideError, read_guide, setup_view, write_guide


class 假派遣器:
    def __init__(self, robots: dict[str, tuple[str, str] | None]) -> None:
        self.registry = SimpleNamespace(list=lambda: [SimpleNamespace(robot_id=r, revoked=False)
                                                      for r in robots])
        self.clients = {r: SimpleNamespace(m=m) for r, m in robots.items()}
        self.zones = SimpleNamespace(confirmed_current=lambda m, v: (m, v) in self.ok)
        self.ok: set[tuple[str, str]] = set()

    @staticmethod
    def _loaded(c):
        return c.m if c is not None else None


def _项(v):
    return {i["id"]: i for i in v["items"]}


def test_空站点什么都没做_做一样亮一样(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    v = setup_view(db, 假派遣器({}))
    assert v["done"] == 0 and v["total"] == 10
    assert [i["id"] for i in v["items"]][:4] == ["robots", "map", "home", "zones"]
    d = 假派遣器({"A": ("m1", "3"), "B": ("m1", "3")})
    items = _项(setup_view(db, d))
    assert items["robots"]["done"] and items["robots"]["count"] == 2
    assert items["map"]["done"] and not items["zones"]["done"]
    assert items["zones"]["maps"] == ["m1:3"]
    assert items["standby"]["robots"] == ["A", "B"]
    d.ok.add(("m1", "3"))
    with db.tx() as c:
        c.execute("INSERT INTO standby_points(robot_id, name, map_id, map_version, x, y, yaw, "
                  "is_default) VALUES ('A','s','m1','3',0,0,0,1)")
    items = _项(setup_view(db, d))
    assert items["zones"]["done"] and items["standby"]["robots"] == ["B"]
    db.close()


def test_标成不用了的项不算没做(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    v = setup_view(db, 假派遣器({}), skip={"arming", "push"})
    it = _项(v)
    assert it["arming"]["skipped"] and it["push"]["skipped"] and v["done"] == 2
    db.close()


def test_向导记录_按账号_合并写_不认的键拒(tmp_path):
    from nexwar_site.accounts import Accounts
    db = SiteDB(tmp_path / "s.db")
    acc = Accounts(db, now_ms=lambda: 0)
    acc.add("g", "pass-word-123", role="guard")
    assert read_guide(acc, "g") == {"tour": 0, "web_tour": 0, "setup_hidden": False, "skip": [],
                                    "map_later": False}
    write_guide(acc, "g", {"tour": 1})
    assert write_guide(acc, "g", {"skip": ["arming"], "web_tour": 1}) == {
        "tour": 1, "web_tour": 1, "setup_hidden": False, "skip": ["arming"], "map_later": False}
    for bad in ({}, {"x": 1}, {"tour": "1"}, {"tour": True}, {"skip": ["nope"]},
                {"tour": -1}, {"setup_hidden": 1}):
        with pytest.raises(GuideError):
            write_guide(acc, "g", bad)
    db.close()


def test_接口_我的向导记录谁都能写_清单只给管理员(tmp_path):
    s = 站(tmp_path)
    try:
        s.accounts.add("vic", PW, role="viewer")
        vic = s.req("POST", "/api/login", {"name": "vic", "password": PW})[1]["token"]
        assert s.req("GET", "/api/me", token=vic)[1]["guide"]["tour"] == 0
        assert s.req("POST", "/api/me/guide", {"tour": 2}, token=vic)[0] == 200
        assert s.req("GET", "/api/me", token=vic)[1]["guide"]["tour"] == 2
        assert s.req("POST", "/api/me/guide", {"bad": 1}, token=vic)[0] == 400
        # 第 4 轮 admin P1-66:翻帮助只是个人界面状态,不进活动记录
        assert s.db.query("SELECT * FROM audit WHERE action LIKE '%/api/me/guide'") == []
        # 审计本身是开着的
        assert s.db.query("SELECT * FROM audit WHERE action LIKE '%/api/login'")
        assert s.req("GET", "/api/setup", token=vic)[0] == 403
        alice = s.login()
        _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
        code, d = s.req("GET", "/api/setup", token=alice)
        assert code == 200 and _项(d)["robots"]["done"] and _项(d)["accounts"]["done"]
    finally:
        s.close()


def test_网页P1_87_登记了图但文件丢了_地图那一项不算做完(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    with db.tx() as c:
        c.execute("INSERT INTO maps(map_id, version, source, created_ms, files) "
                  "VALUES ('m','1','import',0,'[]')")
    d = 假派遣器({})
    assert _项(setup_view(db, d))["map"]["done"]              # 没接地图库(老调用方):照旧按登记算
    d.maps = SimpleNamespace(usable=lambda: False)
    assert not _项(setup_view(db, d))["map"]["done"]
    db.close()


def test_11_11_W6_01_开站清单按机器人现在用的那版图查_原点和路线(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    d = 假派遣器({"A": ("m1", "7"), "B": ("m1", "7")})
    with db.tx() as c:
        c.execute("INSERT INTO homes(robot_id, map_id, map_version, name, x, y, yaw) "
                  "VALUES ('A','m1','11','h',0,0,0)")
        c.execute("INSERT INTO routes(route_id, map_id, map_version, definition, revision, "
                  "updated_ms) VALUES ('r1','m1','11','{}',1,0)")
    it = _项(setup_view(db, d))
    assert [i for i in it][:3] == ["robots", "map", "home"]
    assert not it["home"]["done"] and it["home"]["robots"] == ["A", "B"], "v11 的原点不算 v7 的"
    assert not it["routes"]["done"], "路线画在 v11 上,机器人用的是 v7"
    with db.tx() as c:
        c.execute("INSERT INTO homes(robot_id, map_id, map_version, name, x, y, yaw) "
                  "VALUES ('A','m1','7','h',0,0,0), ('B','m1','7','h',0,0,0)")
        c.execute("INSERT INTO routes(route_id, map_id, map_version, definition, revision, "
                  "updated_ms) VALUES ('r2','m1','','{}',1,0)")
    it = _项(setup_view(db, d))
    assert it["home"]["done"] and it["routes"]["done"], "不分版本的路线(空版本)算"
    db.close()


def test_第8轮_W8_08_路线画在别的版本上_清单说在哪一版_日程的路线跑不了不打勾(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    d = 假派遣器({"A": ("m1", "7")})
    with db.tx() as c:
        c.execute("INSERT INTO routes(route_id, map_id, map_version, definition, revision, "
                  "updated_ms) VALUES ('demo-loop','m1','11','{}',1,0)")
        c.execute("INSERT INTO route_schedules(entry_id, definition, revision, active_from_ms, "
                  "updated_ms, updated_by, source) VALUES ('demo-night', "
                  "'{\"mission\": \"demo-loop\", \"at\": \"22:00\"}', 1, 0, 0, 'a', 'editor')")
    it = _项(setup_view(db, d))
    assert not it["routes"]["done"]
    assert it["routes"]["elsewhere"] == [{"route": "demo-loop", "map": "m1", "version": "11"}]
    assert it["routes"]["using"] == [{"map": "m1", "version": "7"}]
    assert not it["schedule"]["done"], "日程的路线画在 v11 上,机器人用 v7,跑不了"
    assert it["schedule"]["blocked"] == ["demo-night"]
    with db.tx() as c:
        c.execute("UPDATE routes SET map_version='7' WHERE route_id='demo-loop'")
    it = _项(setup_view(db, d))
    assert it["routes"]["done"] and it["schedule"]["done"] and it["schedule"]["blocked"] == []
    db.close()


def test_minor21_待命点只有标原点时自动加的那个_打勾但写明就是原点(tmp_path):
    """liang-d5 W7:标完原点,开站清单「待命点」自动打勾(自动生成了 home-estate-1),人以为自己做过。
    照样算有(机器人有地方回),但写明是哪几台的待命点就在原点上。"""
    db = SiteDB(tmp_path / "s.db")
    d = 假派遣器({"A": ("m1", "3"), "B": ("m1", "3")})
    with db.tx() as c:
        for rid, x in (("A", 0.0), ("B", 0.0)):
            c.execute("INSERT INTO homes(robot_id, map_id, map_version, name, x, y, yaw) "
                      "VALUES (?,'m1','3','home-m1',?,0,0)", (rid, x))
        c.execute("INSERT INTO standby_points(robot_id, name, map_id, map_version, x, y, yaw, "
                  "is_default) VALUES ('A','home-m1','m1','3',0,0,0,1)")
        c.execute("INSERT INTO standby_points(robot_id, name, map_id, map_version, x, y, yaw, "
                  "is_default) VALUES ('B','dock','m1','3',5,5,0,1)")
    it = _项(setup_view(db, d))["standby"]
    assert it["done"] and it["at_home"] == ["A"], it
    db.close()


def test_minor40_没报在用哪张图的机器人_原点待命点不打勾_写明是哪几台(tmp_path):
    """W53 minor #40:B 登记了还没报载着哪张图,清单只看 A:A 标好了就打勾,B 漏了。"""
    db = SiteDB(tmp_path / "s.db")
    d = 假派遣器({"A": ("m1", "3"), "B": None})
    with db.tx() as c:
        c.execute("INSERT INTO homes(robot_id, map_id, map_version, name, x, y, yaw) "
                  "VALUES ('A','m1','3','h',0,0,0)")
        c.execute("INSERT INTO standby_points(robot_id, name, map_id, map_version, x, y, yaw, "
                  "is_default) VALUES ('A','dock','m1','3',5,5,0,1)")
    it = _项(setup_view(db, d))
    for k in ("home", "standby"):
        assert not it[k]["done"] and it[k]["no_map"] == ["B"], (k, it[k])
        assert it[k]["robots"] == [], "A 的做好了"
    d.clients["B"] = SimpleNamespace(m=("m1", "3"))
    with db.tx() as c:
        c.execute("INSERT INTO homes(robot_id, map_id, map_version, name, x, y, yaw) "
                  "VALUES ('B','m1','3','h',0,0,0)")
        c.execute("INSERT INTO standby_points(robot_id, name, map_id, map_version, x, y, yaw, "
                  "is_default) VALUES ('B','dock','m1','3',6,5,0,1)")
    it = _项(setup_view(db, d))
    assert it["home"]["done"] and it["standby"]["done"] and it["home"]["no_map"] == []
    db.close()


def test_第9轮_W8_08尾巴_有一条日程跑不了就不打勾_写日程显示名(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    d = 假派遣器({"A": ("m1", "7")})
    with db.tx() as c:
        c.execute("INSERT INTO routes(route_id, map_id, map_version, definition, revision, "
                  "updated_ms) VALUES ('demo-loop','m1','11','{}',1,0), ('r7','m1','7','{}',1,0)")
        for eid, title, mission in (("demo-night", "夜巡", "demo-loop"), ("ok-1", "", "r7")):
            c.execute("INSERT INTO route_schedules(entry_id, title, definition, revision, "
                      "active_from_ms, updated_ms, updated_by, source) "
                      "VALUES (?, ?, ?, 1, 0, 0, 'a', 'editor')",
                      (eid, title, json.dumps({"mission": mission, "at": "22:00"})))
    it = _项(setup_view(db, d))
    assert not it["schedule"]["done"], "两条里一条跑不了,也不打勾(以前打着勾又写跑不了)"
    assert it["schedule"]["blocked"] == ["夜巡"]
    db.close()

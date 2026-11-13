"""开站清单与上手向导的记录(W53 §8,用户 2026-10-31:只买设备没买交付服务的客户要能自己学会)。

**开站清单**:站点按现在的数据判断每一项做完没有(不靠人勾);App、网页给每一项配「去做」。项的说明
文字在 App、网页里(跟着语言走),这里只出 ``id``、做完没有、细节(哪几台没设待命点之类)。人可以把
某一项标成「不用了」(比如不排布防时间、一直手动切),记在自己账号的 ``guide.skip`` 里。

**上手向导**:每个账号看过哪一版导览(``guide.tour`` 是 App 的、``guide.web_tour`` 是网页的)、
开站清单收没收起来(``guide.setup_hidden``)、没图时的「开始建图」点没点过稍后(``guide.map_later``,W54),
记在账号表 ``accounts.guide``(JSON)。换手机不用再看一遍。
"""

from __future__ import annotations

import json
from typing import Any

#: 清单的项,顺序就是给人看的顺序。
ITEMS = ("robots", "map", "home", "zones", "standby", "routes", "schedule", "arming", "accounts",
         "push")
#: ``guide`` 里认的键。
_GUIDE_KEYS = {"tour": int, "web_tour": int, "setup_hidden": bool, "skip": list,
               "map_later": bool}


class GuideError(ValueError):
    pass


def _count(db: Any, sql: str, args: tuple = ()) -> int:
    return int(db.query(sql, args)[0][0])


def setup_view(db: Any, dispatcher: Any, *, skip: set[str] | None = None) -> dict[str, Any]:
    """在事件循环线程上调(要读派遣器里各台机器人报的已加载地图)。"""
    skip = skip or set()
    robots = [r.robot_id for r in dispatcher.registry.list() if not r.revoked]
    loaded: dict[str, tuple[str, str]] = {}
    for rid in robots:
        got = dispatcher._loaded(dispatcher.clients.get(rid))
        if got is not None:
            loaded[rid] = got
    # minor #40:登记了、还没报在用哪张图的 —— 原点、待命点查不了,不算做完,写明是哪几台
    no_map = [rid for rid in robots if rid not in loaded]
    zones = getattr(dispatcher, "zones", None)
    unconfirmed = sorted({f"{m}:{v}" for m, v in loaded.values()
                          if zones is not None and not zones.confirmed_current(m, v)})
    no_standby = [rid for rid, (m, v) in loaded.items()
                  if not _count(db, "SELECT COUNT(*) FROM standby_points WHERE robot_id=? AND "
                                "map_id=? AND map_version=? AND is_default=1", (rid, m, v))]
    # minor #21(liang-d5 W7):标原点时站点顺手建了个待命点(就在原点上),清单自动打勾 —— 照样算有,
    # 但写明哪几台的默认待命点就在原点上(想停到别处去布置页加)
    at_home = [rid for rid, (m, v) in loaded.items() if rid not in no_standby and _count(
        db, "SELECT COUNT(*) FROM standby_points s JOIN homes h ON h.robot_id=s.robot_id AND "
            "h.map_id=s.map_id AND h.map_version=s.map_version WHERE s.robot_id=? AND "
            "s.map_id=? AND s.map_version=? AND s.is_default=1 AND abs(s.x-h.x)<0.3 AND "
            "abs(s.y-h.y)<0.3", (rid, m, v))]
    # 易用性第 6 轮 W6-01:原点、路线按机器人**现在用的那版图**查(别的版本上有不算:出不了发)
    no_home = [rid for rid, (m, v) in loaded.items()
               if not _count(db, "SELECT COUNT(*) FROM homes WHERE robot_id=? AND map_id=? AND "
                             "map_version=?", (rid, m, v))]
    using = set(loaded.values())

    def runnable(m: str, v: str) -> bool:
        return not using or any(m == um and v in ("", uv) for um, uv in using)

    all_routes = {r["route_id"]: (str(r["map_id"]), str(r["map_version"] or ""))
                  for r in db.query("SELECT route_id, map_id, map_version FROM routes")}
    routes_ok = any(runnable(m, v) for m, v in all_routes.values())
    # 第 8 轮 W8-08:路线都画在别的版本上 → 说画在哪一版、机器人用哪一版(客户以为路线丢了)
    routes_detail: dict[str, Any] = {}
    if not routes_ok and all_routes and using:
        routes_detail = {
            "elsewhere": [{"route": rid, "map": m, "version": v}
                          for rid, (m, v) in sorted(all_routes.items())],
            "using": [{"map": m, "version": v} for m, v in sorted(using)]}
    # 日程要跑的路线跑不了(不存在、画在别的版本上)的不算排好了
    sched = [(str(r["entry_id"]), _parse(r["definition"]).get("mission"))
             for r in db.query("SELECT entry_id, definition FROM route_schedules")]
    blocked = sorted(eid for eid, mission in sched
                     if mission not in all_routes or not runnable(*all_routes[str(mission)]))
    # P1-87:登记了但文件丢了的不算有地图(跟地图页一致)
    store = getattr(dispatcher, "maps", None)
    has_map = bool(loaded) or (store.usable() if store is not None
                               else _count(db, "SELECT COUNT(*) FROM maps") > 0)
    people = _count(db, "SELECT COUNT(*) FROM accounts WHERE disabled=0 AND role != 'engineer'")
    facts: dict[str, tuple[bool, dict[str, Any]]] = {
        "robots": (bool(robots), {"count": len(robots)}),
        "map": (has_map, {}),
        "home": (bool(loaded) and not no_home and not no_map,
                 {"robots": no_home, "no_map": no_map}),
        "zones": (has_map and not unconfirmed, {"maps": unconfirmed}),
        "standby": (bool(loaded) and not no_standby and not no_map,
                    {"robots": no_standby, "at_home": at_home, "no_map": no_map}),
        "routes": (routes_ok, routes_detail),
        "schedule": (bool(sched) and len(blocked) < len(sched), {"blocked": blocked}),
        "arming": (_count(db, "SELECT COUNT(*) FROM arming_slots") > 0, {}),
        "accounts": (people >= 2, {"count": people}),
        "push": (_count(db, "SELECT COUNT(*) FROM push_devices") > 0, {}),
    }
    items = [{"id": k, "done": facts[k][0], "skipped": k in skip and not facts[k][0],
              **facts[k][1]} for k in ITEMS]
    left = [i for i in items if not i["done"] and not i["skipped"]]
    return {"items": items, "done": len(items) - len(left), "total": len(items)}


def _parse(raw: str) -> dict[str, Any]:
    try:
        g = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        g = {}
    return g if isinstance(g, dict) else {}


def read_guide(accounts: Any, name: str) -> dict[str, Any]:
    """``accounts`` 是 ``accounts.Accounts``(账号表只由它写)。"""
    g = _parse(accounts.guide(name))
    return {"tour": int(g.get("tour") or 0), "web_tour": int(g.get("web_tour") or 0),
            "setup_hidden": bool(g.get("setup_hidden")),
            # W54:站点没图时管理员点过「稍后」,登录不再每次弹「开始建图」
            "map_later": bool(g.get("map_later")),
            "skip": [s for s in g.get("skip") or [] if s in ITEMS]}


def write_guide(accounts: Any, name: str, patch: Any) -> dict[str, Any]:
    """合进去(只认 ``_GUIDE_KEYS`` 里的)。"""
    if not isinstance(patch, dict) or not patch or set(patch) - set(_GUIDE_KEYS):
        raise GuideError(f"只认 {'、'.join(_GUIDE_KEYS)}")
    for k, typ in _GUIDE_KEYS.items():
        if k in patch and (not isinstance(patch[k], typ) or isinstance(patch[k], bool)
                           and typ is int):
            raise GuideError(f"{k} 类型错误")
    for k in ("tour", "web_tour"):
        if k in patch and not 0 <= patch[k] <= 1000:
            raise GuideError(f"{k} 是 0–1000 的版本号")
    if "skip" in patch and (len(patch["skip"]) > len(ITEMS)
                            or any(s not in ITEMS for s in patch["skip"])):
        raise GuideError(f"skip 只能是 {'、'.join(ITEMS)}")
    def merge(raw: str) -> str:
        g = _parse(raw)
        g.update(patch)
        return json.dumps(g, ensure_ascii=False)
    if not accounts.set_guide(name, merge):
        raise GuideError("没有此账号")
    return read_guide(accounts, name)

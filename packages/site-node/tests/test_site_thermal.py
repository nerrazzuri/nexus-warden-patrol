"""1.1-6 热像测温 → 站点告警:起火线 P1、高温线 P2(都是保安的「起火、过热」);温度降回去不自己关,
现场记一笔;量不了温度给管理员 P2,量到了自己解决。"""

from __future__ import annotations

T0 = 1_793_000_000_000


def _src(tmp_path):
    from nexwar_site.alert_sources import SiteAlertSources
    from nexwar_site.alert_store import AlertDesk
    from nexwar_site.db import SiteDB
    desk = AlertDesk(SiteDB(tmp_path / "s.db"), now_ms=lambda: T0)
    return desk, SiteAlertSources(desk, now_ms=lambda: T0)


def _ev(kind, data, n=1):
    from nexwar_contract.messages import Event
    return Event(event_id=f"{kind}-{n}", kind=kind, stamp=T0, data=data, boot_id="b", seq=n)


def _开着(desk, kind):
    return [a for a in desk.book.open() if a.kind == kind]


def test_高温P2_起火P1_都给保安_降回去不自己关_记一笔(tmp_path):
    from nexwar_site.alert_audience import audience
    desk, src = _src(tmp_path)
    src.on_event("A", _ev("thermal_hot", {"level": "hot", "max_c": 82.0, "hot_c": 70,
                                          "fire_c": 150}))
    [h] = _开着(desk, "thermal_overheat")
    assert h.level.name == "P2" and "82.0 °C" in h.title and audience(h.kind) == "fire"
    src.on_event("A", _ev("thermal_hot", {"level": "fire", "max_c": 233.5, "hot_c": 70,
                                          "fire_c": 150}, 2))
    [f] = _开着(desk, "thermal_fire")
    assert f.level.name == "P1" and "疑似起火" in f.title and audience(f.kind) == "fire"
    assert "消防" in f.detail
    src.on_event("A", _ev("thermal_normal", {"max_c": 40.0, "peak_c": 233.5, "was": "fire"}, 3))
    [f] = _开着(desk, "thermal_fire")
    assert f.context["cooled_c"] == 40.0 and f.context["peak_c"] == 233.5
    assert _开着(desk, "thermal_overheat"), "人看过再关"


def test_量不了温度给管理员_量到了自己解决(tmp_path):
    from nexwar_site.alert_audience import audience
    desk, src = _src(tmp_path)
    src.on_event("A", _ev("thermometry_failed", {"reason": "热像不给温度(HTTP 401)", "times": 6}))
    [a] = _开着(desk, "thermometry_failed")
    assert a.level.name == "P2" and audience(a.kind) == "owner" and "HTTP 401" in a.detail
    src.on_event("A", _ev("thermometry_ok", {"max_c": 30.0}, 2))
    assert not _开着(desk, "thermometry_failed")

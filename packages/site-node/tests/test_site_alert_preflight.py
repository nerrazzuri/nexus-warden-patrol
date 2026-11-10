"""网页易用性第 1 轮 P0-01:出发前检查没过,别报成「电量不足」。

现场(11-07 测试站点):地图没标原点,狗上起飞前检查的理由是
「起飞前检查未通过: home(地图 'x' 未标原点,…);
battery(电量 98.0%,但算不出出发线:此地图的原点不可用…)」,
站点看到「电量」二字报了 P1「电量不足,回程中途停止」—— 保安照着低电量去处理。
"""

from __future__ import annotations

import pytest

from nexwar_contract.messages import Event
from nexwar_site.alert_sources import SiteAlertSources
from nexwar_site.alert_store import AlertDesk
from nexwar_site.db import SiteDB

NO_HOME = ("起飞前检查未通过: home(地图 'mall' 未标原点,先去标一个换电位); "
           "battery(电量 98.0%,但算不出出发线:此地图的原点不可用(见 home 项))")


@pytest.fixture
def 台(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    desk = AlertDesk(db, now_ms=lambda: 1_800_000_000_000)
    yield desk, SiteAlertSources(desk, now_ms=lambda: 1_800_000_000_000, is_stale=lambda r: False)
    db.close()


_n = iter(range(1, 1000))


def _failed(reason: str, tid: str = "adhoc-1") -> Event:
    n = next(_n)
    return Event(event_id=f"e{n}", seq=n, boot_id="b1", stamp=1, kind="task_failed",
                 data={"task_id": tid, "reason": reason})


def _only(desk):
    return [a for a in desk.book.all() if a.kind not in ("run_start", "run_done")]


def test_没标原点_报出发前检查未通过_不是电量不足(台):
    desk, src = 台
    src.on_event("A", _failed(NO_HOME))
    [a] = _only(desk)
    assert a.kind == "preflight_refused", a.kind
    assert a.level.value == "P2", "没出发,不是半路出事"
    assert "未标原点" in a.title and "电量" not in a.title, a.title
    assert "在这儿标原点" in a.detail, a.detail


def test_回待命点那趟没标原点_也一样(台):
    desk, src = 台
    src.on_event("A", _failed(NO_HOME, tid="standby-A-1"))
    [a] = _only(desk)
    assert a.kind == "preflight_refused" and "回程" not in a.title


def test_出发前电量确实不够_才说电量(台):
    desk, src = 台
    src.on_event("A", _failed("起飞前检查未通过: battery(电量 31.0%,"
                              "不到出发线 40.0%(回撤线下限 30% + 路上 10%))"))
    [a] = _only(desk)
    assert a.kind == "preflight_refused" and "电量不够出发" in a.title, a.title


def test_出发前定位没稳_写定位(台):
    desk, src = 台
    src.on_event("A", _failed("起飞前检查未通过: localized(定位当前是 Lost,不是 ContinuousLoc)"))
    [a] = _only(desk)
    assert "定位" in a.title, a.title


def test_半路没电_照旧报电量不足P1(台):
    desk, src = 台
    src.on_event("A", _failed("电量 22% 低于中止线 25%", tid="patrol-1"))
    [a] = _only(desk)
    assert a.kind == "battery_abort" and a.level.value == "P1"


def test_带上哪一项没过_网页按这一项翻译(台):
    desk, src = 台
    src.on_event("A", _failed(NO_HOME))
    [a] = _only(desk)
    # 日志设计 第 4 条:另带错误码
    assert a.context == {"check": "home", "err": "0x0214"}

"""用户 11-27:该恢复的告警,条件恢复了站点自己关(``resolved_by`` = ``site:…``,时间线记
「alert auto-resolved」);站点重启后库里挂着的,条件恢复照样关。"""
from __future__ import annotations

import pytest

from nexwar_contract.messages import Event, Ready, Status, TaskState, TaskSummary, Telemetry
from nexwar_contract.storage import StorageFacts
from nexwar_site.alert_sources import BACKLOG_ALARM_S, SiteAlertSources
from nexwar_site.alert_store import AlertDesk
from nexwar_site.db import SiteDB


class 钟:
    def __init__(self) -> None:
        self.ms = 1_800_000_000_000

    def __call__(self) -> int:
        return self.ms


@pytest.fixture
def 台(tmp_path):
    c = 钟()
    db = SiteDB(tmp_path / "site.db")
    desk = AlertDesk(db, now_ms=c)
    src = SiteAlertSources(desk, now_ms=c, is_stale=lambda rid: False)
    yield c, db, desk, src
    db.close()


def _status(*, task=None, loc_ok=True) -> Status:
    return Status(online=True, boot_id="b1", control_epoch=1, last_seen=1, task=task,
                  ready=Ready(control=True, motion=True, estop_clear=True, loc_ok=loc_ok))


def _running(tid: str) -> TaskSummary:
    return TaskSummary(task_id=tid, kind="patrol", state=TaskState.RUNNING)


_seq = iter(range(1, 10_000))


def _ev(kind: str, **data) -> Event:
    n = next(_seq)
    return Event(event_id=f"e{n}", seq=n, boot_id="b1", stamp=1, kind=kind, data=data)


def _of(desk, kind: str):
    return [a for a in desk.book.all() if a.kind == kind]


def _auto(db, key: str) -> bool:
    """时间线(站点审计)里有这一条的「自动解除」。"""
    return bool(db.query("SELECT 1 FROM audit WHERE action='alert auto-resolved' AND target=?",
                         (key,)))


def _healed(desk, db, kind: str, who: str) -> None:
    [a] = _of(desk, kind)
    assert a.resolved_ms is not None, f"{kind} 还挂着"
    assert a.resolved_by == who
    assert _auto(db, a.key), "时间线写「自动解除」"


# ------------------------------------------------------------ 1. 空闲时定位不可信


def test_空闲时定位不可信_站点重启后第一份状态就好了_自己关(台, tmp_path):
    c, db, desk, _ = 台
    desk.raise_alert(kind="loc_lost_idle", robot="A", title="空闲的机器人定位不可信")
    src = SiteAlertSources(AlertDesk(db, now_ms=c), now_ms=c, is_stale=lambda rid: False)  # 重启
    src.on_status("A", _status())                        # 没读回状态做种,头一份就是好的
    [a] = _of(src.desk, "loc_lost_idle")
    assert a.resolved_by == "site:loc_ok"


def test_空闲时定位不可信_重启时读回的状态是好的_也关(台):
    c, db, desk, _ = 台
    desk.raise_alert(kind="loc_lost_idle", robot="A", title="空闲的机器人定位不可信")
    src = SiteAlertSources(AlertDesk(db, now_ms=c), now_ms=c, is_stale=lambda rid: False)
    src.seed("A", _status())
    src.on_status("A", _status())
    _healed(src.desk, db, "loc_lost_idle", "site:loc_ok")


def test_空闲时定位不可信_重启后还不好_不关(台):
    c, db, desk, _ = 台
    desk.raise_alert(kind="loc_lost_idle", robot="A", title="空闲的机器人定位不可信")
    src = SiteAlertSources(AlertDesk(db, now_ms=c), now_ms=c, is_stale=lambda rid: False)
    src.on_status("A", _status(loc_ok=False))
    [a] = _of(src.desk, "loc_lost_idle")
    assert a.resolved_ms is None
    src.on_status("A", _status())
    assert _of(src.desk, "loc_lost_idle")[0].resolved_by == "site:loc_ok"


# ------------------------------------------------------------ 2. 证据积压


def _tele(c, oldest_s):
    c.ms += 1000
    return Telemetry(stamp=c.ms, pose=None, battery_pct=80, task_state=None, loc_quality=1.0,
                     storage=StorageFacts(disk_used_ratio=0.1, outbox_bytes=0,
                                          outbox_cap_bytes=10**9, backlog_files=3,
                                          backlog_bytes=4096, oldest_backlog_s=oldest_s))


def test_证据积压_传上来了_自己关_重启后也关(台):
    c, db, desk, src = 台
    src.on_telemetry("A", _tele(c, BACKLOG_ALARM_S + 60))
    assert len(_of(desk, "upload_backlog")) == 1
    src.on_telemetry("A", _tele(c, None))
    _healed(desk, db, "upload_backlog", "site:upload_caught_up")
    src.on_telemetry("A", _tele(c, BACKLOG_ALARM_S + 60))     # 又积压
    src2 = SiteAlertSources(AlertDesk(db, now_ms=c), now_ms=c, is_stale=lambda rid: False)
    src2.on_telemetry("A", _tele(c, None))
    assert all(a.resolved_ms is not None for a in _of(src2.desk, "upload_backlog"))


# ------------------------------------------------------------ 4. RTK


def test_RTK对不上在重定位_定位好了自己关_基站挪了的不关(台):
    c, db, desk, src = 台
    src.on_status("A", _status())
    src.on_event("A", _ev("rtk_disagree", gap_m=3.2, map_id="m", map_version="1"))
    src.on_status("A", _status(loc_ok=False))            # RTK 对不上:机器人报定位不可信
    [a] = _of(desk, "rtk")
    assert a.resolved_ms is None
    src.on_status("A", _status())                        # 重定位成了、对上了
    _healed(desk, db, "rtk", "site:rtk_agree")
    src.on_event("A", _ev("rtk_base_moved", moved_m=1.5, map_id="m", map_version="1"))
    src.on_status("A", _status())
    moved = [x for x in _of(desk, "rtk") if x.resolved_ms is None]
    assert len(moved) == 1 and "基站" in moved[0].title, "基站挪了要人改配置:不随定位关"


def test_RTK_站点重启后库里挂着的_定位好了也关(台):
    c, db, desk, src = 台
    src.on_event("A", _ev("rtk_gave_up", relocs=2, map_id="m", map_version="1"))
    src2 = SiteAlertSources(AlertDesk(db, now_ms=c), now_ms=c, is_stale=lambda rid: False)
    src2.on_status("A", _status())
    assert _of(src2.desk, "rtk")[0].resolved_by == "site:rtk_agree"


# ------------------------------------------------------------ 5. 出发前检查未通过


def test_出发前检查未通过_下一趟正常出发了_自己关(台):
    c, db, desk, src = 台
    src.on_status("A", _status())
    src.on_event("A", _ev("task_failed", task_id="t1",
                          reason="起飞前检查未通过:battery(电量 18% 低于出发线 30%)"))
    assert len(_of(desk, "preflight_refused")) == 1
    src.on_status("A", _status(task=_running("t2")))
    _healed(desk, db, "preflight_refused", "site:departed")


def test_出发前检查未通过_遥控不算出发(台):
    c, db, desk, src = 台
    src.on_status("A", _status())
    src.on_event("A", _ev("task_failed", task_id="t1",
                          reason="起飞前检查未通过:battery(电量 18% 低于出发线 30%)"))
    src.on_status("A", _status(task=_running("teleop-1")))
    assert _of(desk, "preflight_refused")[0].resolved_ms is None


# ------------------------------------------------------------ 6. 未返回待命点


def test_未返回待命点_后来回到了_自己关(台):
    c, db, desk, src = 台
    src.on_feed({"kind": "standby_failed", "robot_id": "A", "after": "sched-1",
                 "reason": "导航拒了"})
    assert len(_of(desk, "standby_failed")) == 1
    src.on_event("A", _ev("task_done", task_id="sched-2"))
    assert _of(desk, "standby_failed")[0].resolved_ms is None, "别的任务完成不算回到"
    src.on_event("A", _ev("task_done", task_id="standby-abc"))
    _healed(desk, db, "standby_failed", "site:standby_reached")


def test_未返回待命点_撤防回原点到了也关(台):
    c, db, desk, src = 台
    src.on_feed({"kind": "standby_failed", "robot_id": "A", "after": "", "reason": "x"})
    src.on_event("A", _ev("task_done", task_id="standby-home-1"))
    assert _of(desk, "standby_failed")[0].resolved_by == "site:standby_reached"


def test_第十六轮_撤防回原点被拒_报P2回原点失败_不是P1回待命点失败(台):
    c, db, desk, src = 台
    src.on_status("A", _status())
    src.on_event("A", _ev("task_failed", task_id="standby-home-abc123",
                          reason="导航拒了:goal_blocked 终点在障碍、禁行区里或贴得太近"))
    assert _of(desk, "run_abort") == [], "不报 P1"
    [a] = _of(desk, "standby_failed")
    assert a.level.value == "P2" and a.title == "回原点失败"
    assert "离墙、障碍或禁行区太近" in a.detail and "先点「回待命点」" in a.detail
    assert "重新标原点" in a.detail
    src.on_event("A", _ev("task_done", task_id="standby-home-def"))      # 挪了原点、回成了
    assert _of(desk, "standby_failed")[0].resolved_by == "site:standby_reached"


def test_第十六轮_回待命点停在半路_照旧P1(台):
    c, db, desk, src = 台
    src.on_status("A", _status())
    src.on_event("A", _ev("task_failed", task_id="standby-abc", reason="导航中止"))
    [a] = _of(desk, "run_abort")
    assert a.title == "回待命点失败,停在半路"


# ------------------------------------------------------------ 9. 装 / 切版本失败


def test_装版本失败_后来装好切好了_自己关(台):
    c, db, desk, src = 台
    src.on_event("A", _ev("release_install_failed", name="v38", reason="校验不对"))
    assert len(_of(desk, "release_failed")) == 1
    src.on_event("A", _ev("release_committed", name="v38"))
    _healed(desk, db, "release_failed", "site:release_committed")


# ------------------------------------------------------------ 10. 请求支援(P3)


def test_请求支援_原报警关单了_跟着关(台):
    c, db, desk, _ = 台
    a = desk.raise_alert(kind="dog_sees_person", robot="A", title="看见人")
    desk.backup(a.key, who="gina")
    [b] = _of(desk, "backup_requested")
    assert b.resolved_ms is None
    desk.arrive(a.key, who="gina")
    desk.resolve(a.key, who="gina", verdict="handled")
    [b] = _of(desk, "backup_requested")
    assert b.resolved_by == "site:incident_closed" and _auto(db, b.key)


def test_请求支援_原报警站点自己关的也跟着关(台):
    c, db, desk, _ = 台
    a = desk.raise_alert(kind="loc_lost_idle", robot="A", title="定位不可信")
    desk.backup(a.key, who="gina")
    desk.resolve_all("A", "loc_lost_idle", who="site:loc_ok")
    assert _of(desk, "backup_requested")[0].resolved_by == "site:incident_closed"


def test_请求支援_重启前原报警就关了_对账时关(台):
    c, db, desk, _ = 台
    a = desk.raise_alert(kind="dog_sees_person", robot="A", title="看见人")
    desk.backup(a.key, who="gina")
    desk.book.resolve(a.key, who="gina", now_ms=c())     # 老站点:只关了原报警
    assert _of(desk, "backup_requested")[0].resolved_ms is None
    d2 = AlertDesk(db, now_ms=c)                          # 站点重启
    d2.escalate()
    assert _of(d2, "backup_requested")[0].resolved_by == "site:incident_closed"


# ------------------------------------------------------------ 3. 备份已过期


def test_备份过期_下一次备份成功_自己关_重启后也关(台, tmp_path):
    from nexwar_site.backup import STALE_MS, SiteBackup
    from nexwar_site.evidence import EvidenceStore
    c, db, desk, _ = 台
    store = EvidenceStore(tmp_path / "evidence", db, now_ms=c)
    bad = tmp_path / "bak-is-a-file"
    bad.write_text("x")
    b = SiteBackup(db, store.root, bad, now_ms=c, alerts=desk)
    b.step()
    c.ms += STALE_MS + 1
    b.step()
    assert len(_of(desk, "backup_stale")) == 1
    good = SiteBackup(db, store.root, tmp_path / "bak", now_ms=c, alerts=desk)   # 改好目的地、重启
    good.step()
    _healed(desk, db, "backup_stale", "site:backup_ok")

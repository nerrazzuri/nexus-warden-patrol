"""外审 11-14:栅格的时刻按**采集时刻**算,而且要管时钟域。

雷达帧头的 ``stamp_ns`` 是感知那边的钟(ROS 时间,可能是雷达自己的钟),代理用本机单调钟,两个钟
不能直接相减。做法:只用「收到时刻 − 帧头时刻」的**变化** —— 见过的最小的当「一路最快」(参考值),
这一帧比它多出来的就是这一帧多等的(积压、卡顿);采集时刻 = 收到时刻 − 多等的 − 固定延迟
(``latency_s``,真机量)。里程位姿按采集时刻插值。参考值往下随时跟,往上每秒最多涨
:data:`CLOCK_DRIFT` 秒(吸收两边钟的漂移;持续卡着不会过几秒就被当成正常)。

- 重复的帧(同 seq)、乱序的帧(seq 倒退)丢掉;seq 从头来(感知重启)→ 时钟重新估。
- seq 往前、帧头时刻往回跳:积压不会这样(帧按采集先后编号),是对方换了钟 → 重新估,先标不可信。
- 积压超过 :data:`LOST_S` 的帧丢掉(里程早就配不上了)。
- 没有帧头时刻(``stamp_ns`` = 0,老感知):按收到时刻 − 固定延迟,标「帧龄不可信」。
"""
from __future__ import annotations

import dataclasses

import pytest
from test_obstacle_avoid import _grid

from nexwar_agent.obstacles import CLOCK_DRIFT, CLOCK_MIN_FRAMES, FRESH_S, LOST_S, ObstacleView

LAT = 0.15
OFF = 1.7e9                                   # 感知那边的钟比代理单调钟早这么多(随便一个数)


def _v():
    t = [100.0]
    v = ObstacleView(monotonic=lambda: t[0], latency_s=LAT)
    return v, t


def _feed(v, t, seq, acq, rx):
    """采集于代理钟 ``acq``(帧头按感知钟写)、``rx`` 时刻收到。时钟只往前走。"""
    assert rx >= t[0] - 1e-9
    t[0] = rx
    v.on_grid(dataclasses.replace(_grid(seq=seq), stamp_ns=int(round((acq + OFF) * 1e9))))


def _go(v, t, until, speed):
    """时钟走到 ``until``,每 0.05 s 一拍里程(机器人按 ``speed`` 沿 x 走)。"""
    while t[0] + 0.05 <= until + 1e-9:
        t[0] += 0.05
        v.note_odom(speed * t[0], 0.0, 0.0)


def _steady(v, t, n=20, *, speed=0.0):
    """10 Hz、一路 0.15 s 延迟,先把钟估出来。返回最后一帧的采集时刻。"""
    t0 = t[0]
    v.note_odom(speed * t0, 0.0, 0.0)
    for i in range(n):
        acq = t0 + 0.1 * i
        _go(v, t, acq + LAT, speed)
        _feed(v, t, i + 1, acq, acq + LAT)
    return t0 + 0.1 * (n - 1)


def test_正常_帧的时刻是采集时刻_位姿按采集时刻插值():
    v, t = _v()
    last = _steady(v, t, speed=1.0)
    f = v.frames[0]
    assert f.at == pytest.approx(last)
    assert f.pose[0] == pytest.approx(last, abs=1e-6), "1 m/s 往前走:配的是采集那一刻的位姿"
    assert v.state() == "ok" and v.stamp_trusted


def test_积压_多等了半秒的帧按半秒前算_配半秒前的位姿_不算新鲜():
    v, t = _v()
    last = _steady(v, t, speed=1.0)
    acq = last + 0.1
    _go(v, t, acq + LAT + 0.5, 1.0)                # 0.5 s 里里程照来,帧没来
    _feed(v, t, 21, acq, acq + LAT + 0.5)
    f = v.frames[0]
    tol = CLOCK_DRIFT * 1.0                                # 参考值这 0.6 s 里最多往上涨这么多
    assert f.at == pytest.approx(acq, abs=tol)
    assert f.pose[0] == pytest.approx(acq, abs=tol)
    assert v.delay_s == pytest.approx(LAT + 0.5, abs=tol)
    assert v.state() != "ok", "采集于 0.65 s 以前:不新鲜"


def test_重复帧_乱序帧丢掉():
    v, t = _v()
    last = _steady(v, t)
    n = len(v.frames)
    _feed(v, t, 20, last, last + LAT + 0.05)               # 同 seq 又来一遍
    _feed(v, t, 15, last - 0.5, last + LAT + 0.06)         # 早的 seq 晚到
    assert len(v.frames) == n and v.frames[0].at == pytest.approx(last)


def test_感知重启_seq从头来_换了钟_重新估():
    v, t = _v()
    last = _steady(v, t)
    acq = last + 3.0
    _go(v, t, acq + LAT, 0.0)
    g = dataclasses.replace(_grid(seq=1), stamp_ns=int(round((acq + 5000.0) * 1e9)))  # 钟也换了
    v.on_grid(g)
    assert v.frames[0].at == pytest.approx(acq), "重启:窗口清空,按固定延迟算"
    assert not v.stamp_trusted, "刚重启,钟还没估稳"


def test_seq往前_帧头时刻往回跳_是换了钟_重新估_先标不可信():
    v, t = _v()
    last = _steady(v, t)
    seq = 21
    for i in range(1, CLOCK_MIN_FRAMES + 2):
        acq = last + 0.1 * i
        _go(v, t, acq + LAT, 0.0)
        _feed(v, t, seq, acq - 3.0, acq + LAT)              # 对方的钟往回拨了 3 s
        seq += 1
        assert v.frames[0].at == pytest.approx(acq), "当场重新估:不当 3 s 前的旧帧,也不卡住"
        assert v.state() == "ok"
        if i == 1:
            assert not v.stamp_trusted
    assert v.stamp_trusted, f"攒够 {CLOCK_MIN_FRAMES} 帧又可信"


def test_一直多等半秒_不会过几秒就当正常_照样不新鲜():
    """持续卡顿(CPU 满、队列堆着):每一帧都是 0.65 s 前采的。参考值往上涨得很慢,
    一分钟以后照样不新鲜。"""
    v, t = _v()
    last = _steady(v, t)
    seq = 21
    for i in range(1, 601):
        acq = last + 0.1 * i
        _go(v, t, acq + LAT + 0.5, 0.0)
        _feed(v, t, seq, acq, acq + LAT + 0.5)
        seq += 1
    assert v.state() != "ok"
    assert v.delay_s >= LAT + 0.5 - CLOCK_DRIFT * 61


def test_积压超过掉线时长的帧丢掉():
    v, t = _v()
    last = _steady(v, t)
    n = len(v.frames)
    _feed(v, t, 21, last + 0.1, last + 0.1 + LAT + LOST_S + 0.5)
    assert len(v.frames) == n


def test_没有帧头时刻_按收到时刻减固定延迟_标不可信():
    v, t = _v()
    t[0] = 50.0
    v.note_odom(0.0, 0.0, 0.0)
    v.on_grid(_grid(seq=1))
    assert v.frames[0].at == pytest.approx(50.0 - LAT)
    assert not v.stamp_trusted
    assert v.state() == "ok", "跟原来一样能走"


def test_新鲜度门槛不变_收到后照样有FRESH_S的余量():
    v, t = _v()
    last = _steady(v, t)
    t[0] = last + LAT + FRESH_S - 0.01
    assert v.state() == "ok"
    t[0] = last + LAT + FRESH_S + 0.01
    assert v.state() == "stale"


def test_积压的帧_日志告警_限频(caplog):
    import logging
    v, t = _v()
    last = _steady(v, t)
    seq = 21
    with caplog.at_level(logging.WARNING, logger="nexwar_agent.obstacles"):
        for i in range(1, 51):                               # 5 s 一直多等 0.5 s
            acq = last + 0.1 * i
            _go(v, t, acq + LAT + 0.5, 0.0)
            _feed(v, t, seq, acq, acq + LAT + 0.5)
            seq += 1
    warns = [r for r in caplog.records if "多等" in r.getMessage()]
    assert 1 <= len(warns) <= 2, [r.getMessage() for r in warns]

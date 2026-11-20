"""真机 11-20:没有视野表就先关遮挡限速,机器人走起来自己学。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nexwar_agent import fovmask

N, RES = 80, 0.1


def _cc():
    cc = (np.arange(N) - N / 2 + 0.5) * RES
    return np.meshgrid(cc, cc, indexing="ij")


def _cone():
    XX, YY = _cc()
    return (XX > 0.6) & (np.abs(YY) <= 0.3 + 0.5 * (XX - 0.6))


def _frame(wall_y=None):
    """视野锥里看得见;``wall_y``:左边这么远有一堵墙(墙本身看得见、墙外看不见)。"""
    XX, YY = _cc()
    known = _cone().copy()
    occ = np.zeros((N, N), dtype=bool)
    if wall_y is not None:
        w = known & (np.abs(YY - wall_y) < RES / 2 + 1e-9)
        occ |= w
        known &= YY <= wall_y + RES / 2 + 1e-9
    return occ, known


def _feed(lr, frames, step=0.1):
    got = None
    for i, (occ, known) in enumerate(frames):
        got = lr.feed(occ=occ.astype(np.uint8).ravel(), known=known.astype(np.uint8).ravel(),
                      size=N, res=RES, pose=(i * step, 0.0, 0.0))
        if got is not None:
            return got, i
    return got, None


def test_一直贴着墙走_墙外被挡住的不算数_学出来不窄(monkeypatch):
    monkeypatch.setattr(fovmask, "AUTO_FRAMES", 200)
    monkeypatch.setattr(fovmask, "AUTO_MIN_CELLS", 50)
    lr = fovmask.Learner()
    # 七成的帧左边 1.0 m 有墙(一直贴墙走),三成空旷
    frames = [_frame(wall_y=1.0 if i % 10 < 7 else None) for i in range(300)]
    got, at = _feed(lr, frames)
    assert got is not None and at == 199
    mask, res, n = got
    assert res == RES and n == 200
    cone = _cone()
    XX, YY = _cc()
    beyond = cone & (YY > 1.0 + RES)
    assert beyond.any()
    assert (mask[beyond]).mean() > 0.9, "墙外那些格子被挡住的帧不算,照样学进来"
    assert not (mask & ~cone).any(), "视野外的学不进来"


def test_被挡住但没墙的_看不见就是看不见_不学进来(monkeypatch):
    """不是被挡住、就是一直看不见的格子(比如抛光地砖回点少):不在视野里。"""
    monkeypatch.setattr(fovmask, "AUTO_FRAMES", 200)
    monkeypatch.setattr(fovmask, "AUTO_MIN_CELLS", 50)
    XX, YY = _cc()
    dark = _cone() & (XX > 2.0) & (YY > 0.5)
    frames = []
    for _ in range(200):
        occ, known = _frame()
        frames.append((occ, known & ~dark))
    got, _ = _feed(fovmask.Learner(), frames)
    assert got is not None and not got[0][dark].any()


def test_站着不动不收帧_学出来太小不认_从头再学(monkeypatch):
    monkeypatch.setattr(fovmask, "AUTO_FRAMES", 50)
    lr = fovmask.Learner()
    still = [_frame()] * 200
    got, _ = _feed(lr, still, step=0.0)
    assert got is None and lr.frames == 1, "站着不动只收第一帧"
    monkeypatch.setattr(fovmask, "AUTO_MIN_CELLS", int(_cone().sum()) + 1)
    got, _ = _feed(lr, [_frame()] * 60)
    assert got is None and lr.frames < 50, "格子太少:不认、从头学"


def test_原地转也收帧():
    lr = fovmask.Learner()
    occ, known = _frame()
    for k in range(5):
        lr.feed(occ=occ.ravel(), known=known.ravel(), size=N, res=RES,
                pose=(0.0, 0.0, k * 0.1))
    assert lr.frames == 5


def test_自己学的存下来_下次开机读得回_etc那份优先(tmp_path, monkeypatch):
    monkeypatch.delenv(fovmask.FOV_ENV, raising=False)
    monkeypatch.setattr(fovmask, "FOV_DEFAULT", tmp_path / "etc" / "fov.json")
    learned = tmp_path / "agent" / fovmask.LEARNED_NAME
    assert fovmask.load(learned=learned) is None
    m = _cone()
    fovmask.save(learned, m, res=RES, frames=600, source="auto")
    got, res = fovmask.load(learned=learned)
    assert res == pytest.approx(RES) and (got == m).all()
    etc = np.zeros((N, N), dtype=bool)
    etc[50:60, 35:45] = True
    fovmask.save(fovmask.FOV_DEFAULT, etc, res=RES, frames=600, source="bag")
    assert (fovmask.load(learned=learned)[0] == etc).all(), "装了的那份优先"


def test_挡住判断_同一方向更近处有挡():
    lr = fovmask.Learner()
    lr._reset(N, RES)
    occ = np.zeros((N, N), dtype=bool)
    XX, YY = _cc()
    i, j = np.unravel_index(np.argmin(np.hypot(XX - 1.05, YY - 0.05)), (N, N))
    occ[i, j] = True
    sh = lr.shadow(occ)
    far = np.unravel_index(np.argmin(np.hypot(XX - 2.05, YY - 0.1)), (N, N))
    near = np.unravel_index(np.argmin(np.hypot(XX - 0.55, YY - 0.05)), (N, N))
    side = np.unravel_index(np.argmin(np.hypot(XX - 1.05, YY - 1.5)), (N, N))
    assert sh[far] and not sh[near] and not sh[side] and not sh[i, j]
    assert math.isfinite(float(lr._r.max()))

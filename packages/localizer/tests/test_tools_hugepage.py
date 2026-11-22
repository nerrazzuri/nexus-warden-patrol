"""出图别向内核要大页(台式机 11-22:内存碎了以后卡在整理大页上,被 systemd-oomd 杀掉)。"""

from __future__ import annotations

import numpy as np
from nexwar_localizer import tools


def test_出图入口关掉numpy的大页():
    try:
        from numpy._core import multiarray as m
    except ImportError:                                  # numpy 1.x
        from numpy.core import multiarray as m
    old = m._set_madvise_hugepage(True)                  # 回的是原来的值
    try:
        assert tools.no_hugepage() is True
        assert m._set_madvise_hugepage(False) is False    # 已经是关着的
        assert np.zeros(1 << 22).sum() == 0               # 照常分配
    finally:
        m._set_madvise_hugepage(old)

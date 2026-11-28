"""1.1-1 认出保安 第 1 步:人脸登记(设计 ``docs/1.1-1-认出保安-设计.md``)。

- **本人登记、本人同意**:只有登录了的那个人自己能登记自己的脸(App 用手机前置相机拍),请求里要带
  ``consent: true``(App 上本人勾的那一下);管理员看得到名单、能删谁的资料,**不能替别人登记**。
- **只存特征值**:每张照片在站点上算出一串数(SFace,128 个)就把照片丢掉,不落盘。特征值整串加密存
  (站点的 ``secrets.key``,:mod:`nexwar_site.sealbox`);站点没配密钥就不收。
- 一个人最多 :data:`MAX_PHOTOS` 张;撤销同意 = 当场删掉这个人的全部特征值。
- 谁登记、谁删都进审计(接口那头记)。
- :meth:`FaceBook.match`:第 2 步机器人发来脸的特征值时用 —— 跟每个人的每张比,最像的过门槛才算认出。

算特征值的 :class:`FaceEngine` 要 OpenCV(``opencv-python-headless``)和两份模型(YuNet、SFace,
OpenCV Zoo,MIT / Apache-2.0);没装就是 ``None``,登记回「此站点没装人脸模块」。
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from nexwar_site.db import SiteDB

log = logging.getLogger(__name__)

MAX_PHOTOS = 5
#: 登记照里的脸至少这么宽(像素):小了特征值不稳。
MIN_FACE_PX = 80
#: 检测分数低于这个的不当脸。
MIN_SCORE = 0.85
#: SFace 余弦相似度门槛(OpenCV Zoo 给的 0.363);第 2 步按实测再调。
MATCH_COSINE = 0.363
MODEL_DIR = Path("/opt/nexwar/models/faces")
YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"


class FaceError(ValueError):
    """登记不成(接口回 400,原因是给人看的)。"""


class FaceEngine(Protocol):
    def features(self, jpeg: bytes) -> list[float]:
        """照片里正好一张够大、够清楚的脸 → 它的特征值;不然 :class:`FaceError` 说为什么。"""


class CvFaceEngine:
    """OpenCV YuNet + SFace。"""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        import cv2
        import numpy as np
        self._cv2, self._np = cv2, np
        self._det = cv2.FaceDetectorYN.create(str(model_dir / YUNET), "", (320, 320), 0.6, 0.3, 50)
        self._rec = cv2.FaceRecognizerSF.create(str(model_dir / SFACE), "")

    def features(self, jpeg: bytes) -> list[float]:
        cv2, np = self._cv2, self._np
        img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise FaceError("照片打不开(要 JPEG)")
        h, w = img.shape[:2]
        self._det.setInputSize((w, h))
        _, found = self._det.detect(img)
        faces = [f for f in (found if found is not None else []) if f[14] >= MIN_SCORE]
        if not faces:
            raise FaceError("照片里没找到脸:正对镜头、光线亮一点再拍")
        if len(faces) > 1:
            raise FaceError("照片里不止一张脸:只拍自己")
        f = faces[0]
        if f[2] < MIN_FACE_PX:
            raise FaceError("脸太小:手机拿近一点再拍")
        feat = self._rec.feature(self._rec.alignCrop(img, f))
        return [round(float(x), 6) for x in feat.reshape(-1)]


def load_engine(model_dir: Path = MODEL_DIR) -> FaceEngine | None:
    """装了 OpenCV、模型在 → 引擎;不然 ``None``(站点照常起,只是不能登记)。"""
    if not (model_dir / YUNET).is_file() or not (model_dir / SFACE).is_file():
        return None
    try:
        return CvFaceEngine(model_dir)
    except Exception as exc:  # noqa: BLE001 - 没装 OpenCV、模型坏了:不能登记,站点照常起
        log.warning("人脸模块起不来:%s", exc)
        return None


def _cos(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)


class FaceBook:
    def __init__(self, db: SiteDB, *, now_ms: Callable[[], int],
                 engine: FaceEngine | None = None) -> None:
        self.db = db
        self._now = now_ms
        self.engine = engine
        self._cache: dict[str, list[list[float]]] | None = None
        #: 外审 1.1 第 2 轮 #4:建缓存和撤销 / 加照片排队(不然撤销清掉的缓存会被正在建的旧缓存盖回去)
        self._lock = threading.Lock()
        #: 第 3 轮 #1:每个人撤销过几次。登记开始时记下,写库前再比:中间撤销过的那次登记不写
        self._revoked: dict[str, int] = {}

    # ---------------------------------------------------------------- 存取

    def _box(self) -> Any:
        box = getattr(self.db, "sealbox", None)
        if box is None:
            raise FaceError("站点没配密钥(secrets.key),不能存人脸资料")
        return box

    def _feats(self, account: str) -> list[list[float]]:
        rows = self.db.query("SELECT feats FROM face_book WHERE account=?", (account,))
        if not rows or not rows[0]["feats"]:
            return []
        return json.loads(self._box().open(rows[0]["feats"]))

    def view(self, account: str) -> dict[str, Any]:
        rows = self.db.query("SELECT * FROM face_book WHERE account=?", (account,))
        r = rows[0] if rows else None
        return {"account": account, "consent_ms": r["consent_ms"] if r else None,
                "photos": r["n"] if r else 0, "updated_ms": r["updated_ms"] if r else None,
                "max_photos": MAX_PHOTOS, "engine": self.engine is not None}

    def list(self) -> list[dict[str, Any]]:
        return [{"account": r["account"], "consent_ms": r["consent_ms"], "photos": r["n"],
                 "updated_ms": r["updated_ms"]}
                for r in self.db.query("SELECT * FROM face_book ORDER BY account")]

    # ---------------------------------------------------------------- 登记 / 删

    def add_photo(self, account: str, *, consent: Any, jpeg_b64: Any) -> dict[str, Any]:
        """本人加一张登记照(``consent`` 要是 ``True``)。满了先删再加。"""
        if consent is not True:
            raise FaceError("要本人勾「同意」才能登记")
        if self.engine is None:
            raise FaceError("此站点没装人脸模块")
        if not isinstance(jpeg_b64, str) or not jpeg_b64:
            raise FaceError("没有照片(jpeg_b64)")
        try:
            jpeg = base64.b64decode(jpeg_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FaceError("照片不是 base64") from exc
        box = self._box()
        with self._lock:
            gen = self._revoked.get(account, 0)
        old = self._feats(account)
        if len(old) >= MAX_PHOTOS:
            raise FaceError(f"已经登记了 {MAX_PHOTOS} 张:要重拍先删掉")
        feat = self.engine.features(jpeg)            # 照片只在这里用,不落盘
        feats = [*old, feat]
        now = self._now()
        sealed = box.seal(json.dumps(feats))
        with self._lock:
            if self._revoked.get(account, 0) != gen:
                raise FaceError("登记的时候撤销了同意:这张没存,要登记重新来")
            with self.db.tx() as c:
                c.execute("INSERT INTO face_book(account, consent_ms, feats, n, updated_ms) "
                          "VALUES (?,?,?,?,?) ON CONFLICT(account) DO UPDATE SET "
                          "feats=excluded.feats, n=excluded.n, updated_ms=excluded.updated_ms",
                          (account, now, sealed, len(feats), now))
            self._cache = None
        return self.view(account)

    def remove(self, account: str) -> bool:
        """撤销同意 / 管理员删:这个人的特征值全删。"""
        with self._lock:
            with self.db.tx() as c:
                n = c.execute("DELETE FROM face_book WHERE account=?", (account,)).rowcount
            self._revoked[account] = self._revoked.get(account, 0) + 1
            self._cache = None
        return bool(n)

    def consented(self, account: str) -> bool:
        """这个人此刻还在登记表里(没撤销)。"""
        return bool(self.db.query("SELECT 1 FROM face_book WHERE account=?", (account,)))

    # ---------------------------------------------------------------- 认

    def match(self, feat: list[float]) -> tuple[str, float] | None:
        """第 2 步:机器人拍到的一张脸 → 最像的那个人和分数;都不过门槛 ``None``。"""
        with self._lock:
            if self._cache is None:
                self._cache = {r["account"]: self._feats(r["account"])
                               for r in self.db.query("SELECT account FROM face_book")}
            cache = self._cache
        best: tuple[str, float] | None = None
        for acc, fs in cache.items():
            for f in fs:
                s = _cos(feat, f)
                if s >= MATCH_COSINE and (best is None or s > best[1]):
                    best = (acc, s)
        return best

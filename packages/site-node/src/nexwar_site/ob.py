"""1.1-5 电子值班簿(Occurrence Book,OB)+ 事件报告(设计 ``docs/1.1-5-值班簿-设计.md``)。

**值班簿**:保安手写的(上岗、下岗、访客、巡查、事件、维修、观察、其他)加上站点自己记的(报警
报了、谁确认、谁关、结论;巡检跑了哪趟、结果;外部报警器的事件;交班留言),按时间排成一本。

- 手写的**只追加,不改不删**(纸质 OB 的老规矩:写错了不涂,另写一条「更正第 n 条」)。
  :meth:`OccurrenceBook.add` 的 ``corrects`` 指向被更正的那条;列出来时被更正的标出来。
- 时间可以补记:``at_ms`` 最早 24 小时前(忘了当场写),不能写到将来;写的时刻另记(``written_ms``)。
- 自动的那几样不另存一份,读的时候从各自的表里拼(报警、巡检、外部事件、交班留言)。

**事件报告**:一条报警一页 —— 报了什么、在哪台机器人、什么时候报的、谁几点确认、谁几点到场、
做了什么(喊话、警灯)、值班簿里关于它的几条、怎么关的、结论、那段时间机器人拍的照片(最多
:data:`REPORT_PHOTOS` 张,直接嵌进页面)。

两样都出**能直接打印的网页**(``text/html``,样式、照片都在一个文件里):网页点「打印 / 存 PDF」、
App 分享出去用浏览器打开存 PDF。站点上不装 PDF 库(中文字体要嵌,包大、还要跟着中文字体授权走)。
"""

from __future__ import annotations

import base64
import html
import json
from collections.abc import Callable
from datetime import datetime, tzinfo
from typing import Any

from nexwar_site.alert_audience import GUARD_AUDIENCES, audience

CATEGORIES = ("duty_on", "duty_off", "patrol", "incident", "visitor", "handover", "maintenance",
              "observation", "other")
MAX_CHARS = 1000
BACKDATE_MS = 24 * 3600_000
#: 一本最多列这么多条(超了 ``truncated``)。
BOOK_MAX = 2000
REPORT_PHOTOS = 8
#: 报告里的照片:报警前后这么久里机器人拍的。
PHOTO_BEFORE_MS = 60_000
PHOTO_AFTER_MS = 10 * 60_000

_CAT = {
    "duty_on": ("On duty", "上岗"), "duty_off": ("Off duty", "下岗"),
    "patrol": ("Patrol", "巡查"), "incident": ("Incident", "事件"),
    "visitor": ("Visitor", "访客"), "handover": ("Handover", "交班"),
    "maintenance": ("Maintenance", "维修"), "observation": ("Observation", "观察"),
    "other": ("Other", "其他"), "alarm": ("Alarm", "报警"),
    "external": ("External alarm", "外部报警"),
}
_VERDICT = {"intruder": ("real intrusion", "确有入侵"), "false_alarm": ("false alarm", "误报"),
            "handled": ("handled", "已处理")}


class ObError(ValueError):
    """写的不对(接口回 400)。"""


def _l(pair: tuple[str, str], lang: str) -> str:
    return pair[1] if lang == "zh" else pair[0]


def cat_name(cat: str, lang: str) -> str:
    return _l(_CAT.get(cat, (cat, cat)), lang)


class OccurrenceBook:
    def __init__(self, db: Any, *, now_ms: Callable[[], int]) -> None:
        self.db = db
        self._now = now_ms

    # ------------------------------------------------------------ 手写

    def add(self, author: str, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ObError("要一个对象")
        cat, text = body.get("category"), body.get("text")
        if cat not in CATEGORIES:
            raise ObError(f"category 只认 {'/'.join(CATEGORIES)}")
        if not isinstance(text, str) or not text.strip():
            raise ObError("写点什么")
        text = text.strip()
        if len(text) > MAX_CHARS:
            raise ObError(f"一条最多 {MAX_CHARS} 字")
        now = self._now()
        at = body.get("at_ms", now)
        if isinstance(at, bool) or not isinstance(at, int) \
                or not now - BACKDATE_MS <= at <= now + 60_000:
            raise ObError("时间只能补记 24 小时以内的,不能写到将来")
        robot = body.get("robot") or ""
        alert = body.get("alert") or ""
        if not isinstance(robot, str) or len(robot) > 64 or not isinstance(alert, str) \
                or len(alert) > 256:
            raise ObError("robot、alert 写错了")
        corrects = body.get("corrects")
        if corrects is not None and (isinstance(corrects, bool) or not isinstance(corrects, int)):
            raise ObError("要更正的那条没有")
        with self.db.tx() as c:
            # 外审 1.1 第 2 轮 #12:查和写在同一个事务里(两个人同时更正同一条,后到的被拒)
            if corrects is not None:
                old = c.execute("SELECT robot, alert_key FROM ob_entries WHERE id=?",
                                (corrects,)).fetchone()
                if old is None:
                    raise ObError("要更正的那条没有")
                if c.execute("SELECT 1 FROM ob_entries WHERE corrects=?",
                             (corrects,)).fetchone():
                    raise ObError("这条已经更正过了:要改就更正最新的那条")
                # 外审 1.1 #13、第 2 轮 #13:更正跟着原来那条走(哪台机器人、哪条报警),不许改挂
                if (robot and robot != old["robot"]) or (alert and alert != old["alert_key"]):
                    raise ObError("更正跟着原来那条的机器人和报警,不能改挂到别的上")
                robot, alert = old["robot"], old["alert_key"]
            cur = c.execute(
                "INSERT INTO ob_entries(at_ms, written_ms, author, category, text, robot,"
                " alert_key, corrects) VALUES (?,?,?,?,?,?,?,?)",
                (at, now, author, cat, text, robot, alert, corrects))
            nid = int(cur.lastrowid)
        return self.entry(nid)

    def entry(self, nid: int) -> dict[str, Any]:
        rows = self.db.query("SELECT * FROM ob_entries WHERE id=?", (nid,))
        if not rows:
            raise KeyError(nid)
        return dict(rows[0])

    # ------------------------------------------------------------ 一本

    def book(self, since_ms: int, until_ms: int, *, lang: str = "en") -> dict[str, Any]:
        """``[since, until)`` 的值班簿:手写的 + 自动的,按时间排。每条 ``{at_ms, source, category,
        text, author, robot, id?, corrects?, corrected_by?, alert?}``。"""
        if not (isinstance(since_ms, int) and isinstance(until_ms, int)) or until_ms <= since_ms \
                or until_ms - since_ms > 31 * 86_400_000:
            raise ObError("时间段不对(最长 31 天)")
        w = (since_ms, until_ms)
        items: list[dict[str, Any]] = []
        fixed: dict[int, int] = {}
        for r in self.db.query("SELECT corrects, id FROM ob_entries WHERE corrects IS NOT NULL"):
            fixed.setdefault(int(r["corrects"]), int(r["id"]))
        for r in self.db.query("SELECT * FROM ob_entries WHERE at_ms>=? AND at_ms<? ORDER BY at_ms",
                               w):
            d = {"at_ms": r["at_ms"], "source": "manual", "category": r["category"],
                 "text": r["text"], "author": r["author"], "robot": r["robot"], "id": r["id"],
                 "written_ms": r["written_ms"]}
            if r["alert_key"]:
                d["alert"] = r["alert_key"]
            if r["corrects"] is not None:
                d["corrects"] = r["corrects"]
            if r["id"] in fixed:
                d["corrected_by"] = fixed[r["id"]]
            items.append(d)
        items += self._alarms(w, lang)
        items += self._runs(w, lang)
        items += self._external(w, lang)
        for r in self.db.query("SELECT * FROM shift_notes WHERE at_ms>=? AND at_ms<?", w):
            items.append({"at_ms": r["at_ms"], "source": "handover", "category": "handover",
                          "text": r["text"], "author": r["author"], "robot": ""})
        items.sort(key=lambda d: (d["at_ms"], 0 if d["source"] == "manual" else 1))
        cut = len(items) > BOOK_MAX
        return {"since_ms": since_ms, "until_ms": until_ms, "entries": items[:BOOK_MAX],
                "truncated": cut}

    def _alarms(self, w: tuple[int, int], lang: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        zh = lang == "zh"
        for r in self.db.query(
                "SELECT * FROM alerts WHERE (first_ms>=? AND first_ms<?)"
                " OR (acked_ms>=? AND acked_ms<?) OR (resolved_ms>=? AND resolved_ms<?)",
                w + w + w):
            if audience(r["kind"]) not in GUARD_AUDIENCES and r["level"] != "P1":
                continue
            base = {"source": "alarm", "category": "alarm", "robot": r["robot"], "alert": r["key"]}
            title = f"{r['level']} {r['title']}"
            if w[0] <= r["first_ms"] < w[1]:
                out.append({**base, "at_ms": r["first_ms"], "author": "",
                            "text": (f"{title}(报了 {r['count']} 次)" if zh and r["count"] > 1
                                     else f"{title} (raised {r['count']}×)" if r["count"] > 1
                                     else title)})
            if r["acked_ms"] is not None and w[0] <= r["acked_ms"] < w[1]:
                out.append({**base, "at_ms": r["acked_ms"], "author": r["acked_by"],
                            "text": f"确认:{title}" if zh else f"Acknowledged: {title}"})
            if r["resolved_ms"] is not None and w[0] <= r["resolved_ms"] < w[1]:
                v = _VERDICT.get(r["verdict"] if "verdict" in r.keys() else "")
                tail = f"({_l(v, lang)})" if v and zh else f" ({_l(v, lang)})" if v else ""
                out.append({**base, "at_ms": r["resolved_ms"], "author": r["resolved_by"],
                            "text": (f"关闭:{title}" if zh else f"Closed: {title}") + tail})
        return out

    def _runs(self, w: tuple[int, int], lang: str) -> list[dict[str, Any]]:
        zh = lang == "zh"
        out = []
        for r in self.db.query("SELECT * FROM runs WHERE first_ms>=? AND first_ms<?", w):
            res = r["result"] or ("未完" if zh else "unfinished")
            out.append({"at_ms": r["first_ms"], "source": "patrol", "category": "patrol",
                        "robot": r["robot_id"], "author": "", "run": r["id"],
                        "text": (f"机器人巡检「{r['mission']}」:{res},{r['photos']} 张照片" if zh
                                 else f"Robot patrol '{r['mission']}': {res}, "
                                      f"{r['photos']} photos")})
        return out

    def _external(self, w: tuple[int, int], lang: str) -> list[dict[str, Any]]:
        zh = lang == "zh"
        out = []
        for r in self.db.query("SELECT * FROM incidents WHERE received_at>=? AND received_at<?", w):
            who = f",派 {r['robot_id']}" if zh and r["robot_id"] else \
                f", sent {r['robot_id']}" if r["robot_id"] else ""
            out.append({"at_ms": r["received_at"], "source": "external", "category": "external",
                        "robot": r["robot_id"] or "", "author": "",
                        "text": (f"外部报警 {r['type']}(防区 {r['zone']},来自 {r['source']}){who}"
                                 if zh else f"External alarm {r['type']} (zone {r['zone']}, "
                                            f"from {r['source']}){who}")})
        return out


# ---------------------------------------------------------------- 能打印的网页

_CSS = """
:root { color-scheme: light; }
body { font: 13px/1.45 system-ui, -apple-system, "Segoe UI", "Noto Sans", "PingFang SC",
  "Microsoft YaHei", sans-serif; color: #111; background: #fff; margin: 24px; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 20px 0 6px; border-bottom: 1px solid #999; padding-bottom: 2px; }
.meta { color: #444; margin: 0 0 12px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #bbb; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #eee; font-weight: 600; }
td.t { white-space: nowrap; width: 1%; }
tr.fixed td { color: #777; text-decoration: line-through; }
.photos { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.photos figure { margin: 0; break-inside: avoid; }
.photos img { width: 100%; border: 1px solid #bbb; }
.photos figcaption { font-size: 11px; color: #444; }
.bar { margin-bottom: 16px; }
.bar button { font: inherit; padding: 6px 14px; }
.sign { margin-top: 32px; display: flex; gap: 48px; }
.sign div { flex: 1; border-top: 1px solid #111; padding-top: 4px; }
@media print { .bar { display: none; } body { margin: 12mm; } }
"""


def _page(title: str, body: str, lang: str) -> str:
    btn = "打印 / 存成 PDF" if lang == "zh" else "Print / Save as PDF"
    return (f'<!doctype html><html lang="{"zh" if lang == "zh" else "en"}"><head>'
            f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{html.escape(title)}</title><style>{_CSS}</style></head>'
            f'<body><div class="bar"><button onclick="window.print()">{btn}</button></div>'
            f"{body}</body></html>")


def _when(ms: int | None, tz: tzinfo, *, day: bool = True) -> str:
    if ms is None:
        return ""
    t = datetime.fromtimestamp(ms / 1000, tz)
    return t.strftime("%Y-%m-%d %H:%M:%S" if day else "%H:%M:%S")


def book_html(book: dict[str, Any], *, site: str, tz: tzinfo, lang: str) -> str:
    zh = lang == "zh"
    e = html.escape
    title = ("值班簿" if zh else "Occurrence Book") + (f" — {site}" if site else "")
    rows = []
    for d in book["entries"]:
        no = f"#{d['id']}" if "id" in d else ""
        txt = e(d["text"])
        if "corrects" in d:
            txt = (f"<b>更正 #{d['corrects']}:</b>" if zh else
                   f"<b>Correction to #{d['corrects']}:</b> ") + txt
        if "corrected_by" in d:
            txt += (f"(已由 #{d['corrected_by']} 更正)" if zh
                    else f" (corrected by #{d['corrected_by']})")
        rows.append(f'<tr class="{"fixed" if "corrected_by" in d else ""}">'
                    f'<td class="t">{e(_when(d["at_ms"], tz))}</td><td>{e(no)}</td>'
                    f"<td>{e(cat_name(d['category'], lang))}</td><td>{txt}</td>"
                    f"<td>{e(d.get('robot') or '')}</td><td>{e(d.get('author') or '')}</td></tr>")
    head = (("时间", "编号", "类别", "内容", "机器人", "记录人") if zh
            else ("Time", "No.", "Type", "Entry", "Robot", "By"))
    body = (f"<h1>{e(title)}</h1><p class='meta'>{e(_when(book['since_ms'], tz))} — "
            f"{e(_when(book['until_ms'], tz))} · "
            + (f"{len(book['entries'])} 条" if zh else f"{len(book['entries'])} entries")
            + (" · 只列了前 2000 条" if zh and book["truncated"] else
               " · first 2000 only" if book["truncated"] else "")
            + "</p><table><thead><tr>" + "".join(f"<th>{h}</th>" for h in head)
            + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
            + "<div class='sign'><div>" + ("交班人签名" if zh else "Handed over by")
            + "</div><div>" + ("接班人签名" if zh else "Taken over by") + "</div><div>"
            + ("主管签名" if zh else "Supervisor") + "</div></div>")
    return _page(title, body, lang)


def incident_report(db: Any, key: str, *, lang: str, photos: Callable[[str, int, int],
                    list[tuple[str, bytes]]] | None = None) -> dict[str, Any]:
    """一条报警的报告(给 :func:`report_html` 排版)。没有这条抛 ``KeyError``。"""
    rows = db.query("SELECT * FROM alerts WHERE key=?", (key,))
    if not rows:
        raise KeyError(key)
    a = dict(rows[0])
    try:
        ctx = json.loads(a.get("context") or "{}")
    except ValueError:
        ctx = {}
    zh = lang == "zh"
    steps: list[tuple[int, str, str]] = [(a["first_ms"], "", "报警" if zh else "Raised")]
    if a["count"] > 1:
        steps.append((a["last_ms"], "", f"最后一次报(共 {a['count']} 次)" if zh
                      else f"Last raised ({a['count']} times)"))
    if a["acked_ms"] is not None:
        steps.append((a["acked_ms"], a["acked_by"], "确认" if zh else "Acknowledged"))
    if isinstance(ctx, dict) and isinstance(ctx.get("arrived_ms"), int):
        steps.append((ctx["arrived_ms"], str(ctx.get("arrived_by") or ""),
                      "保安到场" if zh else "Guard on site"))
    for wv in (ctx.get("warnings") or []) if isinstance(ctx, dict) else []:
        if isinstance(wv, dict) and isinstance(wv.get("at_ms"), int):
            steps.append((wv["at_ms"], str(wv.get("by") or ""),
                          (f"{wv.get('robot', '')} 开 {wv.get('output', '')}" if zh
                           else f"{wv.get('robot', '')} {wv.get('output', '')} on")))
    obs = db.query("SELECT * FROM ob_entries WHERE alert_key=? ORDER BY at_ms", (key,))
    fixed = {int(r["corrects"]): int(r["id"]) for r in obs if r["corrects"] is not None}
    for r in obs:
        # 外审 1.1 #13:写错了的那条标「已由 #n 更正」,更正的标「更正 #n」
        txt = f"{cat_name(r['category'], lang)}:{r['text']}" if zh \
            else f"{cat_name(r['category'], lang)}: {r['text']}"
        if r["corrects"] is not None:
            txt = (f"更正 #{r['corrects']}:" if zh else f"Correction to #{r['corrects']}: ") + txt
        if int(r["id"]) in fixed:
            n = fixed[int(r["id"])]
            txt += f"(已由 #{n} 更正)" if zh else f" (corrected by #{n})"
        steps.append((r["at_ms"], r["author"], f"#{r['id']} " + txt))
    if a["resolved_ms"] is not None:
        v = _VERDICT.get(a.get("verdict") or "")
        steps.append((a["resolved_ms"], a["resolved_by"], ("关闭" if zh else "Closed")
                      + (f"({_l(v, lang)})" if v and zh else f" ({_l(v, lang)})" if v else "")))
    steps.sort(key=lambda s: s[0])
    until = (a["resolved_ms"] or a["last_ms"]) + PHOTO_AFTER_MS
    pics = photos(a["robot"], a["first_ms"] - PHOTO_BEFORE_MS, until) if photos and a["robot"] \
        else []
    return {"alert": a, "context": ctx if isinstance(ctx, dict) else {}, "steps": steps,
            "photos": pics[:REPORT_PHOTOS]}


def report_html(rep: dict[str, Any], *, site: str, tz: tzinfo, lang: str) -> str:
    zh = lang == "zh"
    e = html.escape
    a = rep["alert"]
    title = ("事件报告" if zh else "Incident report") + f" — {a['title']}"
    v = _VERDICT.get(a.get("verdict") or "")
    facts = [
        ("站点" if zh else "Site", site),
        ("级别" if zh else "Level", a["level"]),
        ("事件" if zh else "Event", a["title"]),
        ("说明" if zh else "Detail", a["detail"]),
        ("机器人" if zh else "Robot", a["robot"]),
        ("报警时间" if zh else "Raised", _when(a["first_ms"], tz)),
        ("状态" if zh else "Status", ((f"已关闭({_l(v, lang)})" if v else "已关闭") if zh
                                      else (f"Closed ({_l(v, lang)})" if v else "Closed"))
         if a["resolved_ms"] is not None else ("未关闭" if zh else "Open")),
        ("编号" if zh else "Reference", a["key"]),
    ]
    where = rep["context"].get("last_seen")
    if isinstance(where, dict) and {"x", "y"} <= set(where):
        facts.append(("最后位置" if zh else "Last position",
                      f"{where.get('map_id', '')} x={where['x']:.1f} y={where['y']:.1f}"))
    fact_rows = "".join(f"<tr><th>{e(k)}</th><td>{e(str(val))}</td></tr>" for k, val in facts
                        if val != "")
    step_rows = "".join(f'<tr><td class="t">{e(_when(t, tz))}</td><td>{e(what)}</td>'
                        f"<td>{e(who)}</td></tr>" for t, who, what in rep["steps"])
    pics = "".join(
        f"<figure><img alt='' src='data:image/jpeg;base64,{base64.b64encode(b).decode()}'>"
        f"<figcaption>{e(cap)}</figcaption></figure>" for cap, b in rep["photos"])
    head = ("时间", "经过", "谁") if zh else ("Time", "What happened", "By")
    body = (f"<h1>{e(title)}</h1>"
            f"<p class='meta'>{e('生成于 ' if zh else 'Generated ')}"
            f"{e(_when(int(datetime.now(tz).timestamp() * 1000), tz))}</p>"
            f"<table>{fact_rows}</table>"
            f"<h2>{'经过' if zh else 'Timeline'}</h2><table><thead><tr>"
            + "".join(f"<th>{h}</th>" for h in head) + f"</tr></thead><tbody>{step_rows}</tbody>"
            "</table>"
            + (f"<h2>{'照片' if zh else 'Photos'}</h2><div class='photos'>{pics}</div>"
               if pics else "")
            + "<div class='sign'><div>" + ("报告人" if zh else "Reported by") + "</div><div>"
            + ("主管" if zh else "Supervisor") + "</div></div>")
    return _page(title, body, lang)

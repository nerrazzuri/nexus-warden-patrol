// 全站活动日志(liang-d5 第 5 轮前):「11 月 5 日晚上谁撤的防、谁派的机器人」—— 按日期范围、人、操作类别
// 在站点查,能翻页,能导出 CSV。原来只能在用户页按人看最近 200 条。
import { useEffect, useState } from "preact/hooks";
import { api } from "./api";
import { t, type Key } from "./i18n";
import { dateInput, dayRange } from "./recordings";
import { AuditLine, mergeAudit, type AuditRow } from "./userspage";

const PAGE = 200;
/** 跟站点 audit.AUDIT_GROUPS 一一对应。 */
const GROUPS: { v: string; key: Key }[] = [
  { v: "", key: "actAll" }, { v: "dispatch", key: "actGrpDispatch" }, { v: "stop", key: "actGrpStop" },
  { v: "arming", key: "actGrpArming" }, { v: "alarms", key: "actGrpAlarms" }, { v: "accounts", key: "actGrpAccounts" },
  { v: "setup", key: "actGrpSetup" }, { v: "robots", key: "actGrpRobots" }, { v: "views", key: "actGrpViews" },
  { v: "system", key: "actGrpSystem" },
];

/** 查询串(列表和导出共用)。日期看不懂的回 null。 */
export function activityQuery(f: { from: string; to: string; actor: string; group: string }): string | null {
  const a = dayRange(f.from), b = dayRange(f.to);
  if (!a || !b || b.until <= a.since) return null;
  const q = new URLSearchParams({ since: String(a.since), until: String(b.until) });
  if (f.actor.trim()) q.set("actor", f.actor.trim());
  if (f.group) q.set("group", f.group);
  return q.toString();
}

export function ActivityPage({ now }: { now: number }) {
  const today = dateInput(now);
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [actor, setActor] = useState("");
  const [group, setGroup] = useState("");
  const [page, setPage] = useState(0);
  const [got, setGot] = useState<{ audit: AuditRow[]; total: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const qs = activityQuery({ from, to, actor, group });
  useEffect(() => { setPage(0); }, [qs]);
  useEffect(() => {
    if (qs == null) return;
    let live = true;
    setGot(null);
    setFailed(false);
    api<{ audit: AuditRow[]; total: number }>("GET", `/api/audit?${qs}&limit=${PAGE}&offset=${page * PAGE}`)
      .then((d) => { if (live) setGot({ audit: d.audit ?? [], total: d.total ?? 0 }); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [qs, page]);
  return (
    <section class="activity panel">
      <div class="panel-head"><h1>{t("tabActivity")}</h1></div>
      <p class="muted lead">{t("actLead")}</p>
      <div class="filters row">
        <label class="small">{t("actFrom")} <input type="date" value={from} max={today} onChange={(e) => setFrom(e.currentTarget.value)} /></label>
        <label class="small">{t("actTo")} <input type="date" value={to} max={today} onChange={(e) => setTo(e.currentTarget.value)} /></label>
        <label class="small">{t("actWho")} <input type="text" value={actor} placeholder={t("actWhoAny")} onChange={(e) => setActor(e.currentTarget.value)} /></label>
        <label class="small">{t("actWhat")} <select value={group} onChange={(e) => setGroup(e.currentTarget.value)}>
          {GROUPS.map((g) => <option key={g.v} value={g.v}>{t(g.key)}</option>)}
        </select></label>
        {qs != null && <a class="btn sm push" href={`/api/audit?${qs}&format=csv`} download data-export="1">{t("actExport")}</a>}
      </div>
      {qs == null && <p class="error small">{t("actBadRange")}</p>}
      {failed && <p class="empty warn" data-load-failed="1">{t("loadRetry")}</p>}
      {qs != null && !failed && got == null && <p class="muted">{t("loading")}</p>}
      {got && got.total === 0 && <p class="empty">{t("actNone")}</p>}
      {got && got.total > 0 && (
        <>
          <p class="row small" data-act-pages="1">
            <span class="muted">{t("actPageOf", { a: page * PAGE + 1, b: Math.min((page + 1) * PAGE, got.total), n: got.total })}</span>
            {got.total > PAGE && <>
              <button type="button" class="btn sm" disabled={page === 0} onClick={() => setPage(page - 1)}>{t("alPagePrev")}</button>
              <button type="button" class="btn sm" disabled={(page + 1) * PAGE >= got.total} onClick={() => setPage(page + 1)}>{t("alPageNext")}</button>
            </>}
          </p>
          <ul class="plain user-audit">{mergeAudit(got.audit).map((r) => <AuditLine key={r.id} r={r} who />)}</ul>
        </>
      )}
    </section>
  );
}

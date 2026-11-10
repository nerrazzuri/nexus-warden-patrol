// 今天的巡逻(W53):日程的每一轮和临时巡逻按时间排,一行一趟。值班页左下角。站点 GET /api/patrols/today。
import { byText, siteKnown, siteStr, siteText } from "./sitetext";
import { useEffect, useState } from "preact/hooks";
import { missingReason, plainReason } from "./alertinfo";
import { api } from "./api";
import { hm } from "./data";
import { t, type Key } from "./i18n";

export interface TodayItem {
  at_ms: number;
  kind: "schedule" | "adhoc";
  label: string;
  robot: string;
  stopped_by?: string;
  by: string;
  state: string;
  reason: string;
  end_ms: number | null;
  adhoc_id: string;
  /** W71:跑完了、跳过了几个点(到了一部分算完成)。老站点没有。 */
  skipped?: number;
}

const STATE: Record<string, [Key, string]> = {
  done: ["tdDone", "ok"], failed: ["tdFailed", "bad"], aborted: ["tdAborted", ""], running: ["tdRunning", "info"],
  waiting: ["tdWaiting", "warn"], missed: ["tdMissed", "bad"], next: ["tdNext", ""], later: ["tdLater", ""],
  queued: ["tdQueued", "warn"], cancelled: ["tdCancelled", ""], expired: ["tdExpired", ""],
};

/** 时刻按站点的钟(站点回的 ``utc_offset_min``);老站点没有就按浏览器的(外审 W53-1 #12)。 */
export function siteHm(ms: number, offsetMin: number | null | undefined): string {
  if (offsetMin == null) return hm(ms);
  const d = new Date(ms + offsetMin * 60_000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export function stateOf(s: string, skipped = 0): [string, string] {
  if (s === "done" && skipped > 0) return [t("tdDoneSkipped", { n: skipped }), "warn"];
  const x = STATE[s];
  return x ? [t(x[0]), x[1]] : [s, ""];
}

export function TodayPatrols({ retryMs = 5_000 }: { retryMs?: number } = {}) {
  const [items, setItems] = useState<TodayItem[] | null>(null);
  const [off, setOff] = useState<number | null>(null);
  // liang-d5 第 5 轮前:往天的每一趟也能查(选个日期;空 = 今天)
  const [day, setDay] = useState("");
  const [today, setToday] = useState("");
  // 第 2 轮:拉不到不能当成「今天没有巡逻」;拉不到的时候按 retryMs 重拉,拉到了回到 30 秒一次
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    let timer = 0;
    setItems(null);
    const load = () => api<{ items: TodayItem[]; utc_offset_min?: number; date?: string }>("GET", day ? `/api/patrols/day?date=${day}` : "/api/patrols/today")
      .then((d) => { if (live) { setItems(d.items ?? []); setOff(d.utc_offset_min ?? null); setFailed(false); if (!day && d.date) setToday(d.date); } return true; })
      .catch(() => { if (live) setFailed(true); return false; })
      .then((ok) => { if (live) timer = window.setTimeout(load, ok ? 30_000 : retryMs); });
    void load();
    return () => { live = false; window.clearTimeout(timer); };
  }, [day]);
  const past = day !== "" && day !== today;
  return (
    <section class="today" aria-label={t("tdTitle")}>
      <h3 class="today-h row">
        <span>{past ? t("tdTitleDay", { d: day }) : t("tdTitle")}</span>
        <input type="date" class="push small" aria-label={t("tdPickDay")} title={t("tdPickDay")} value={day || today}
          max={today || undefined} onChange={(e) => setDay(e.currentTarget.value === today ? "" : e.currentTarget.value)} />
        {past && <button type="button" class="btn sm" onClick={() => setDay("")}>{t("alToday")}</button>}
      </h3>
      {failed && <p class="warn small" role="status">{t("loadRetry")}</p>}
      {!failed && items != null && items.length === 0 && <p class="muted small">{t(past ? "tdNoneDay" : "tdNone")}</p>}
      <ul class="today-list">
        {(items ?? []).map((x, i) => {
          const [label, tone] = stateOf(x.state, x.skipped ?? 0);
          return (
            <li key={i} class="today-row" title={x.reason ? (siteText(x.reason).raw ?? siteStr(x.reason)) : undefined}>
              <span class="mono">{siteHm(x.at_ms, off)}</span>
              <span class="today-what">
                {/* 第 3 轮 zh N11:名字本身就是「临时路线…」时不再加「临时 ·」;叫停的那趟原因 halt 跟右边「被叫停」重复,不写 */}
                {[x.kind === "adhoc" && !/^(临时|One-off)/.test(siteKnown(x.label)) ? t("tdAdhoc") : "", siteKnown(x.label), x.robot, x.kind === "adhoc" && x.by ? t("tdSentBy", { who: x.by }) : ""].filter(Boolean).join(" · ")}
                {/* 第 4 轮 admin N7:写清是谁叫停的(派单的人不一定是叫停的人) */}
                {x.state === "aborted" && x.stopped_by && <span class="muted small" data-stopped-by="1"> · {t("tdStoppedBy", { who: byText(x.stopped_by) || x.stopped_by })}</span>}
                {x.reason && !(x.state === "aborted" && /^(halt|stop|stopped)$/i.test(x.reason.trim())) ? <span class="muted small"> · {plainReason(x.reason)}</span>
                  : (x.state === "failed" || x.state === "missed") && <span class="muted small"> · {missingReason()}</span>}
              </span>
              <span class={`tdchip ${tone}`}>{label}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

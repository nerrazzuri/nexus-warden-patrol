// 今天的巡逻(W53):日程的每一轮和临时巡逻按时间排,一行一趟。值班页左下角。站点 GET /api/patrols/today。
import { byText, siteKnown, siteStr, siteText } from "./sitetext";
import { useEffect, useState } from "preact/hooks";
import { missingReason, plainReason } from "./alertinfo";
import { api } from "./api";
import { hm } from "./data";
import { t, type Key } from "./i18n";
import { lapText } from "./loops";

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
  /** 易用性第 7 轮:路线画在哪一版、排给的那台用的哪一版(对不上才有)。 */
  map?: { route: string; robot: string };
  /** 第 8 轮:一直巡逻、在跑的第几圈、被谁接替(老站点没有)。 */
  forever?: boolean;
  /** 第 8 轮 W8-11:路线的显示名(没起是空)。 */
  title?: string;
  lap?: { n: number; of: number };
  handover?: { by: "schedule" | "teleop" | "task"; name: string; laps: number };
}

const ver = (v: string) => (/^\d+$/.test(v) ? `v${v}` : v);

const STATE: Record<string, [Key, string]> = {
  done: ["tdDone", "ok"], failed: ["tdFailed", "bad"], aborted: ["tdAborted", ""], running: ["tdRunning", "info"],
  waiting: ["tdWaiting", "warn"], missed: ["tdMissed", "bad"], next: ["tdNext", ""], later: ["tdLater", ""],
  queued: ["tdQueued", "warn"], cancelled: ["tdCancelled", ""], expired: ["tdExpired", ""],
  blocked: ["tdBlocked", "warn"], handed_over: ["tdHandedOver", ""],
};

/** 第 8 轮 W8-03:被接替的那趟 —— 跑了几圈、谁接的。 */
function handoverText(h: NonNullable<TodayItem["handover"]>): string {
  const who = h.by === "schedule" ? t("tdByScheduleName", { name: h.name }) : h.by === "teleop" ? t("tdByTeleop") : t("tdByTask");
  return h.laps > 0 ? t("tdHandoverLaps", { n: h.laps, who }) : t("tdHandover", { who });
}

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

export function TodayPatrols({ retryMs = 5_000, canFix = false }: { retryMs?: number; canFix?: boolean } = {}) {
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
                {[x.kind === "adhoc" && !/^(临时|One-off)/.test(siteKnown(x.label)) ? t("tdAdhoc") : "", x.title || siteKnown(x.label), x.robot, x.kind === "adhoc" && x.by ? t("tdSentBy", { who: x.by }) : ""].filter(Boolean).join(" · ")}
                {/* 第 4 轮 admin N7:写清是谁叫停的(派单的人不一定是叫停的人) */}
                {x.state === "aborted" && x.stopped_by && <span class="muted small" data-stopped-by="1"> · {t("tdStoppedBy", { who: byText(x.stopped_by) || x.stopped_by })}</span>}
                {/* 易用性第 6 轮 W6-02:到了也不会跑(排给的那台只许手动派):写原因,管理员给去改的入口 */}
                {x.state === "blocked" && x.reason === "manual_only" ? (
                  <span class="muted small" data-blocked="1"> · {t("tdManualOnly", { id: x.robot })}
                    {canFix && x.robot && <> <a href={`#/admin/robots?robot=${encodeURIComponent(x.robot)}`}>{t("tdFixRobot")}</a></>}
                  </span>
                ) : x.reason === "map_mismatch" && x.map ? null
                  : x.reason && !(x.state === "aborted" && /^(halt|stop|stopped)$/i.test(x.reason.trim())) ? <span class="muted small"> · {plainReason(x.reason)}</span>
                  : (x.state === "failed" || x.state === "missed") && <span class="muted small"> · {missingReason()}</span>}
                {x.state === "running" && x.lap && <span class="muted small" data-lap="1"> · {lapText(x.lap)}</span>}
                {x.state === "handed_over" && x.handover && <span class="muted small" data-handover="1"> · {handoverText(x.handover)}</span>}
                {x.map && <span class="muted small" data-map-gap="1"> · {t("tdMapGap", { a: ver(x.map.route), id: x.robot, b: ver(x.map.robot) })}</span>}
              </span>
              <span class={`tdchip ${tone}`}>{label}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// 警报详情(网页易用性第 1 轮 P0-04 / P0-05):点一条警报看怎么回事、在哪、该做什么,在这里接手、派机器人、
// 看录像;关警报要先选结论(有人 / 误报 / 处理好了),可以写备注;点错了 10 分钟内能撤销。
// 只读账号只看,不显示处理按钮(P0-20)。
import { useState } from "preact/hooks";
import { alertAdvice, alertHeadline, canHandleAlerts } from "./alertinfo";
import { api, ApiError, enc } from "./api";
import { hm, nameOf } from "./data";
import { Modal } from "./dialogs";
import { lang, t, type Lang } from "./i18n";
import { GoLookCard, verdictText } from "./mappage";
import type { UnitInfo } from "./live";
import { canDispatch, type Alert } from "./model";
import { recordingLink } from "./recordings";

const en = {
  dTitle: "Alarm details",
  dWhen: "Raised {a} · last {b} · {n}×",
  dWhenOnce: "Raised {a}",
  dWhere: "Where",
  dRobot: "Robot",
  dTaken: "Taken by {who}",
  dNotTaken: "Nobody has taken it yet",
  dDo: "What to do",
  dSite: "Details from the site",
  dRec: "See recordings",
  dSend: "Send a robot here",
  dCloseH: "Close this alarm",
  dWhat: "What was it?",
  dNote: "Note (optional)",
  dNoteHint: "e.g. a box blown over by the wind",
  dCloseBtn: "Close alarm",
  dClosed: "Closed: {v} · {who} · {t}",
  dUndo: "Undo close",
  dUndone: "Alarm reopened",
  dGone: "This alarm was already handled by someone else.",
  dReadOnly: "Your account can only view alarms.",
};
type DKey = keyof typeof en;
const zh: Record<DKey, string> = {
  dTitle: "报警详情",
  dWhen: "{a} 发生 · 最近 {b} · 共 {n} 次",
  dWhenOnce: "{a} 发生",
  dWhere: "位置",
  dRobot: "机器人",
  dTaken: "{who} 已接手",
  dNotTaken: "还没有人接手",
  dDo: "该做什么",
  dSite: "站点给的详情",
  dRec: "看录像",
  dSend: "派机器人过去",
  dCloseH: "关闭这条报警",
  dWhat: "是什么情况？",
  dNote: "备注（可不填）",
  dNoteHint: "例如：风吹倒的纸箱",
  dCloseBtn: "关闭报警",
  dClosed: "已关闭：{v} · {who} · {t}",
  dUndo: "撤销关闭",
  dUndone: "报警已重新打开",
  dGone: "这条报警已被别人处理。",
  dReadOnly: "你的账号只能查看报警。",
};
const DD: Record<Lang, Record<DKey, string>> = { en, zh };
function dt(key: DKey, vars?: Record<string, string | number>): string {
  let s = DD[lang.value][key] ?? en[key];
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

/** 处理后这么久内能撤销(站点 alerts.REOPEN_MS)。 */
export const REOPEN_MS = 10 * 60_000;
/** 要先到场才能关的(站点 alert_store.ARRIVAL_KINDS)。 */
const ARRIVE = new Set(["dog_sees_person"]);
const LOST = new Set(["loc_lost_paused", "loc_lost_idle"]);

type Verdict = "intruder" | "false_alarm" | "handled";

/** 这种警报能选哪些结论:有人闯入类三种都有,其余是「处理好了 / 误报」。 */
export function verdictsFor(a: Alert): Verdict[] {
  return a.audience === "intrusion" || a.audience === "fire" ? ["intruder", "false_alarm", "handled"] : ["handled", "false_alarm"];
}

const VKEY = { intruder: "vIntruder", false_alarm: "vFalse", handled: "vHandled" } as const;

export function AlertDetail(props: {
  a: Alert;
  role: string;
  now: number;
  units: UnitInfo[];
  onClose: () => void;
  refresh: () => Promise<void>;
  say: (s: string) => void;
  onFindPose?: (robot: string) => void;
}) {
  const a = props.a;
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sending, setSending] = useState(false);
  const open = a.resolved_ms == null;
  const can = canHandleAlerts(props.role);
  const mustArrive = ARRIVE.has(a.kind) && a.context?.arrived_ms == null;
  const site = a.robot === "site" || a.robot.includes(":");
  const where = a.context?.zone ?? a.context?.where ?? "";
  const pose = a.context?.pose;
  const advice = alertAdvice(a);

  async function post(action: string, body: unknown, after?: string) {
    setBusy(true);
    setErr("");
    try {
      await api("POST", `/api/alerts/${enc(a.key)}/${action}`, body);
      if (after) props.say(after);
      await props.refresh();
      if (action === "resolve") props.onClose();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) { props.say(dt("dGone")); await props.refresh(); props.onClose(); }
      else setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const when = a.count > 1 ? dt("dWhen", { a: hm(a.first_ms), b: hm(a.last_ms), n: a.count }) : dt("dWhenOnce", { a: hm(a.first_ms) });
  return (
    <Modal label={alertHeadline(a)} onClose={props.onClose} wide>
      <div class="alertdetail" data-key={a.key}>
        <p class="ad-meta">
          <span class={a.level === "P1" ? "tag p1" : a.level === "P2" ? "tag p2" : "tag"}>{a.level}</span>
          <span>{when}</span>
          {!site && <span>{dt("dRobot")}: <b>{nameOf(a.robot)}</b></span>}
          {where && <span>{dt("dWhere")}: <b>{where}</b></span>}
        </p>
        {open && <p class="muted small">{a.acked_by ? dt("dTaken", { who: a.acked_by }) : dt("dNotTaken")}</p>}
        {advice && (
          <div class="ad-do"><h3>{dt("dDo")}</h3><p>{advice}</p></div>
        )}
        {a.detail && (
          <div class="ad-site"><h3>{dt("dSite")}</h3><p class="small">{a.detail}</p></div>
        )}
        {!open && (
          <p class="ad-closed">
            {dt("dClosed", { v: verdictText(a), who: a.resolved_by || "—", t: a.resolved_ms ? hm(a.resolved_ms) : "" })}
            {a.context && (a.context as { note?: string }).note && <><br /><span class="muted">{(a.context as { note?: string }).note}</span></>}
          </p>
        )}
        <div class="row wrap ad-acts">
          {!site && <a class="btn sm" href={recordingLink(a)} onClick={props.onClose}>{dt("dRec")}</a>}
          {open && can && a.acked_ms == null && (
            <button type="button" class="btn sm" disabled={busy} onClick={() => post("ack", {})}>{t("dutyTake")}</button>
          )}
          {open && can && mustArrive && (
            <button type="button" class="btn sm" disabled={busy} onClick={() => post("arrive", {})}>{t("dutyArrive")}</button>
          )}
          {open && can && LOST.has(a.kind) && props.onFindPose && (
            <button type="button" class="btn sm" onClick={() => { props.onFindPose?.(a.robot); props.onClose(); }}>{t("dutyFindPose")}</button>
          )}
          {open && pose && canDispatch(props.role) && !sending && (
            <button type="button" class="btn sm" onClick={() => setSending(true)}>{dt("dSend")}</button>
          )}
          {!open && can && a.resolved_ms != null && props.now - a.resolved_ms < REOPEN_MS && (
            <button type="button" class="btn sm" disabled={busy} onClick={() => post("reopen", {}, dt("dUndone"))}>{dt("dUndo")}</button>
          )}
        </div>
        {sending && pose && (
          <GoLookCard map={{ map_id: pose.map_id, version: pose.map_version }} at={[pose.x, pose.y]} units={props.units}
            onClose={() => setSending(false)} say={props.say} />
        )}
        {open && can && !mustArrive && (
          <fieldset class="ad-close">
            <legend>{dt("dCloseH")}</legend>
            <p class="small">{dt("dWhat")}</p>
            <div class="seg" role="group" aria-label={dt("dWhat")}>
              {verdictsFor(a).map((v) => (
                <button key={v} type="button" aria-pressed={verdict === v} onClick={() => setVerdict(v)}>{t(VKEY[v])}</button>
              ))}
            </div>
            <label class="field">
              {dt("dNote")}
              <input value={note} maxLength={200} placeholder={dt("dNoteHint")} onInput={(e) => setNote(e.currentTarget.value)} />
            </label>
            <div class="row end">
              <button type="button" class="btn" onClick={props.onClose}>{t("cancel")}</button>
              <button type="button" class={verdict === "false_alarm" ? "btn" : "btn primary"} disabled={busy || verdict == null}
                onClick={() => verdict && post("resolve", { verdict, note: note.trim() })}>{dt("dCloseBtn")}</button>
            </div>
          </fieldset>
        )}
        {!can && <p class="muted small">{dt("dReadOnly")}</p>}
        {err && <p class="error" role="alert">{err}</p>}
      </div>
    </Modal>
  );
}

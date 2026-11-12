// POC 第 5 项:路线页「派一趟」。挑一台机器人 → 站点估预计多久、现在走还是排在日程后面 → 确认了才派
// (走现成的临时巡逻:撞日程就排队、通知经理和管理员)。
import { useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { Modal } from "./dialogs";
import { t } from "./i18n";
import { LoopsSelect } from "./loops";
import { siteHm } from "./todaypatrols";

interface Plan { estimate_s?: number | null; start_ms?: number; queued?: boolean; because?: string; utc_offset_min?: number; forever?: boolean; interrupted_by?: string; return_pct?: number }
interface Sent { queued?: boolean; start_after_ms?: number; because?: string; utc_offset_min?: number; ack?: { result?: string; reason?: string } }

/** 两种用法:路线页定了路线、挑机器人(``route``);第 8 轮 W8-09 值守页定了机器人、挑路线(``robot``)。 */
export function DispatchOnce({ route: fixedRoute, robot: fixedRobot, say, cls }: {
  route?: string; robot?: string; say: (s: string) => void; cls?: string;
}) {
  const [open, setOpen] = useState(false);
  const [robots, setRobots] = useState<string[] | null>(null);
  const [routes, setRoutes] = useState<string[] | null>(null);
  const [robot, setRobot] = useState(fixedRobot ?? "");
  const [route, setRoute] = useState(fixedRoute ?? "");
  const [loops, setLoops] = useState(1);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const why = (e: unknown) => (e instanceof ApiError ? e.message : String(e));
  const start = () => {
    setOpen(true);
    setRobot(fixedRobot ?? "");
    setRoute(fixedRoute ?? "");
    setLoops(1);
    setPlan(null);
    setErr(null);
    if (fixedRobot == null) {
      api<{ robots: { robot_id: string; fresh?: boolean; revoked?: boolean }[] }>("GET", "/api/robots")
        .then((d) => setRobots(d.robots.filter((r) => !r.revoked && r.fresh !== false).map((r) => r.robot_id)))
        .catch((e) => { setRobots([]); setErr(why(e)); });
    }
    if (fixedRoute == null) {
      api<{ routes: { id: string }[] }>("GET", "/api/routes?kind=patrol")
        .then((d) => setRoutes(d.routes.map((r) => r.id)))
        .catch((e) => { setRoutes([]); setErr(why(e)); });
    }
  };
  const ask = (id: string, rt: string, n: number) => {
    setPlan(null);
    setErr(null);
    if (!id || !rt) return;
    // 外审 W76-1 #7:选了 1 圈也发 —— 不发站点按路线里存的圈数跑
    const lq = `&loops=${n}`;
    api<Plan>("GET", `/api/robots/${enc(id)}/patrol-plan?mission_id=${encodeURIComponent(rt)}${lq}`)
      .then(setPlan).catch((e) => setErr(why(e)));
  };
  const pick = (id: string) => { setRobot(id); ask(id, route, loops); };
  const pickRoute = (rt: string) => { setRoute(rt); ask(robot, rt, loops); };
  const pickLoops = (n: number) => { setLoops(n); ask(robot, route, n); };
  const go = async () => {
    setBusy(true);
    try {
      const r = await api<Sent>("POST", `/api/robots/${enc(robot)}/patrol`, { mission_id: route, loops });
      if (r.queued) say(t("trQueued", { id: robot, at: siteHm(r.start_after_ms ?? 0, r.utc_offset_min), why: r.because ?? "" }));
      else if (r.ack && r.ack.result !== "accepted" && r.ack.result !== "duplicate") {
        setErr(t("rdNotAccepted", { why: r.ack.reason || r.ack.result || "" }));
        return;
      } else say(t("rdPatrolSent", { id: robot, route }));
      setOpen(false);
    } catch (e) {
      setErr(why(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" class={cls ?? "btn"} data-dispatch-once="1" data-robot-patrol={fixedRobot} onClick={start}>{t("doBtn")}</button>
      {open && (
        <Modal label={fixedRoute != null ? t("doTitle", { route: fixedRoute }) : t("doTitleRobot", { id: fixedRobot ?? "" })} onClose={() => setOpen(false)}>
          <div class="route-dispatch">
            {fixedRobot == null && <>
              <label class="field">{t("doRobot")}
                <select name="robot" value={robot} onChange={(e) => pick(e.currentTarget.value)}>
                  <option value="">{t("doPickRobot")}</option>
                  {(robots ?? []).map((id) => <option key={id} value={id}>{id}</option>)}
                </select>
              </label>
              {robots !== null && robots.length === 0 && <p class="muted small">{t("doNoRobot")}</p>}
            </>}
            {fixedRoute == null && <>
              <label class="field">{t("doRoute")}
                <select name="route" value={route} onChange={(e) => pickRoute(e.currentTarget.value)}>
                  <option value="">{t("doPickRoute")}</option>
                  {(routes ?? []).map((id) => <option key={id} value={id}>{id}</option>)}
                </select>
              </label>
              {routes !== null && routes.length === 0 && <p class="muted small">{t("doNoRoute")}</p>}
            </>}
            <label class="field">{t("loopsLabel")}
              <LoopsSelect value={loops} onChange={pickLoops} />
            </label>
            {plan && (plan.forever ? (
              <p class="small" data-plan="1">
                {plan.return_pct != null ? t("doForeverPct", { n: plan.return_pct }) : t("doForever")}
                {plan.interrupted_by ? <> · {t("doForeverCut", { what: plan.interrupted_by })}</> : null}
              </p>
            ) : (
              <p class="small" data-plan="1">
                {plan.estimate_s != null && <>{t("doEta", { m: Math.max(1, Math.round(plan.estimate_s / 60)) })} · </>}
                {plan.queued
                  ? t("doQueued", { at: siteHm(plan.start_ms ?? 0, plan.utc_offset_min), why: plan.because ?? "" })
                  : t("doNow")}
              </p>
            ))}
            {err && <p class="error small" role="alert">{err}</p>}
            <div class="row end">
              <button type="button" class="btn" onClick={() => setOpen(false)}>{t("cancel")}</button>
              <button type="button" class="btn primary" disabled={!plan || busy} onClick={() => void go()}>
                {plan?.queued ? t("doQueueIt") : t("doSend")}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

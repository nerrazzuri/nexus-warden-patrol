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
export function DispatchOnce({ route: fixedRoute, robot: fixedRobot, say, cls, title }: {
  route?: string; robot?: string; say: (s: string) => void; cls?: string;
  /** 第 8 轮 W8-11:定了的那条路线的显示名。 */
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const [robots, setRobots] = useState<string[] | null>(null);
  const [routes, setRoutes] = useState<{ id: string; title?: string; map_id?: string; map_version?: string }[] | null>(null);
  // 第 9 轮 W9-04:每台在用哪张图哪一版 —— 画在别的版本上的路线灰掉写原因(跟机器人页一样)
  const [maps, setMaps] = useState<Record<string, { id?: string; version?: string }>>({});
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
    // 第 10 轮 W9-04:/api/robots 里在用哪张图在 running.map_id / map_version(没有 map 这个字段;
    // 以前读 r.map,测试的假数据带了、真站点没有,判断不了)
    api<{ robots: { robot_id: string; fresh?: boolean; revoked?: boolean; running?: { map_id?: string | null; map_version?: string | null } | null }[] }>("GET", "/api/robots")
      .then((d) => {
        setMaps(Object.fromEntries(d.robots.filter((r) => r.running?.map_id)
          .map((r) => [r.robot_id, { id: r.running?.map_id ?? undefined, version: r.running?.map_version ?? undefined }])));
        if (fixedRobot == null) setRobots(d.robots.filter((r) => !r.revoked && r.fresh !== false).map((r) => r.robot_id));
      })
      .catch((e) => { if (fixedRobot == null) { setRobots([]); setErr(why(e)); } });
    if (fixedRoute == null) {
      api<{ routes: { id: string; title?: string; map_id?: string; map_version?: string }[] }>("GET", "/api/routes?kind=patrol")
        .then((d) => setRoutes(d.routes.map((r) => ({ id: r.id, title: r.title, map_id: r.map_id, map_version: r.map_version }))))
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
  /** 这条路线这台跑不了:画在哪(「v11」或「estate-2 v3」);跑得了或不知道回 null。 */
  const otherMap = (rt: { map_id?: string; map_version?: string } | undefined, id: string): string | null => {
    const m = maps[id];
    if (!rt || !rt.map_version || !m?.version) return null;
    if (rt.map_id && m.id && rt.map_id !== m.id) return `${rt.map_id} v${rt.map_version}`;
    return rt.map_version === m.version ? null : `v${rt.map_version}`;
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
      } else say(t("rdPatrolSent", { id: robot, route: title || routes?.find((x) => x.id === route)?.title || route }));
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
        <Modal label={fixedRoute != null ? t("doTitle", { route: title || fixedRoute }) : t("doTitleRobot", { id: fixedRobot ?? "" })} onClose={() => setOpen(false)}>
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
                  {(routes ?? []).map((x) => {
                    const o = robot ? otherMap(x, robot) : null;
                    return <option key={x.id} value={x.id} disabled={o !== null}>
                      {o === null ? x.title || x.id : `${x.title || x.id} — ${t("doRouteOtherMap", { at: o, id: robot, v: `v${maps[robot]?.version ?? ""}` })}`}
                    </option>;
                  })}
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

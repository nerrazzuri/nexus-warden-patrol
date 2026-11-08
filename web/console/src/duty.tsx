// 总览(W44 第一期的值班页,W60 改版;默认首页)。先告诉人「现在最要紧的是什么」:
// 出事时顶上横幅(P1 红、P2 琥珀):什么事、在哪、几点,几个按钮;第一个画面位换成现场。
// 没事时只有一行安静的「一切正常」(W60 约束:正常状态要安静,不放大绿条)。
// 下面四块:地图、待处理报警、现场画面(两个位,按紧急程度自动挑,可以钉住)、机器人(每台一条 + 今日巡逻)。
// 保安只看四类事(有人闯入、起火或过热、机器人需要帮忙、机器人掉线);技术类不在这里。
import { byText } from "./sitetext";
import { useEffect, useMemo, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { hm, nameOf } from "./data";
import { modeLabel } from "./armingpage";
import { Shape } from "./icons";
import { AlertDetail } from "./alertdetail";
import { Confirm } from "./dialogs";
import { alertHeadline, canHandleAlerts } from "./alertinfo";
import { guardAlarms, pickSlots, rankUnits, type SlotPick } from "./dutyrank";
import { t } from "./i18n";
import { StateText, type UnitInfo } from "./live";
import type { CanvasArea } from "./mapcanvas";
import { SiteMap } from "./mappage";
import { pointInPolygon } from "./mapview";
import { canDispatch, type Alert, type Mode } from "./model";
import { pageAllowed } from "./shell";
import { VideoSlot, type Scene } from "./slot";
import { TodayPatrols } from "./todaypatrols";

/** 迷路了的两种(站点 alerts.LEVEL_OF):横幅上多一个「帮它找位置」。 */
const LOST = new Set(["loc_lost_paused", "loc_lost_idle"]);
/** W74:要保安先到场才能关的告警(站点 alert_store.ARRIVAL_KINDS)。 */
const ARRIVE = new Set(["dog_sees_person"]);

interface FixedCam { name: string; zone: string }

export function DutyPage(props: {
  units: UnitInfo[];
  alerts: Alert[];
  now: number;
  role: string;
  say: (s: string) => void;
  refresh: () => Promise<void>;
  onZoom: (robot: string) => void;
  /** 布防状态(一切正常那一行写上);没有就不写。 */
  mode?: Mode | null;
  /** 跟站点断了 / 数据过期(P0-02):不能说「一切正常」。 */
  stale?: boolean;
}) {
  // P2-08:钉住的两路记在这台浏览器上,刷新不丢
  const [pins, setPinsRaw] = useState<[string | null, string | null]>(loadPins);
  const setPins = (f: (p: [string | null, string | null]) => [string | null, string | null]) => setPinsRaw((p) => {
    const n = f(p);
    try { localStorage.setItem(PINS_KEY, JSON.stringify(n)); } catch { /* 隐私模式:不记 */ }
    return n;
  });
  // 网页易用性第 1 轮 P0-04/05:点一条警报看详情,关警报要选结论
  const [detail, setDetail] = useState<string | null>(null);
  const [finding, setFinding] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [areas, setAreas] = useState<CanvasArea[]>([]);
  const [cams, setCams] = useState<FixedCam[]>([]);

  useEffect(() => {
    let live = true;
    api<{ cameras: FixedCam[] }>("GET", "/api/cameras").then((d) => live && setCams(d.cameras ?? [])).catch(() => {});
    return () => { live = false; };
  }, []);

  const alarms = useMemo(() => guardAlarms(props.alerts), [props.alerts]);
  const ranked = useMemo(() => rankUnits(props.units, props.alerts), [props.units, props.alerts]);
  const slots = pickSlots(ranked, pins, alarms);
  const top = alarms[0];
  const hot = new Set(alarms.map((a) => a.context?.zone).filter((z): z is string => !!z));
  const unitOf = (id: string) => props.units.find((u) => u.robot.robot_id === id);

  /** 有人闯入的现场:那个防区的固定摄像头。 */
  function sceneOf(a: Alert | undefined): Scene | undefined {
    if (!a || a.audience !== "intrusion" || !a.context?.zone) return undefined;
    const c = cams.find((x) => x.zone === a.context?.zone);
    return c ? { label: c.name, src: `/api/cameras/${enc(c.name)}/live`, health: `/api/cameras/${enc(c.name)}/health` } : undefined;
  }

  async function post(path: string, body: unknown) {
    try {
      await api("POST", path, body);
    } catch (e) {
      // 别人已经处理掉了(解决了、删了):说一次,刷新,横幅自己就没了
      if (e instanceof ApiError && e.status === 404) props.say(t("dutyGone"));
      else props.say(t("failed", { why: e instanceof ApiError ? e.message : String(e) }));
    }
    await props.refresh();
  }
  const ack = (a: Alert) => post(`/api/alerts/${enc(a.key)}/ack`, {});
  const arrive = (a: Alert) => post(`/api/alerts/${enc(a.key)}/arrive`, {});
  const can = canHandleAlerts(props.role);
  const shown = detail ? props.alerts.find((a) => a.key === detail) ?? null : null;
  /** W74:看见人那一类要保安点过「已到场」才能关(站点也这么拦)。 */
  const mustArrive = (a: Alert) => ARRIVE.has(a.kind) && a.context?.arrived_ms == null;

  const pin = (i: 0 | 1, robot: string) => setPins((p) => {
    const n: [string | null, string | null] = [p[0], p[1]];
    n[i] = n[i] === robot ? null : robot;
    return n;
  });
  /** 点状态条:放进没钉住的那个位(两个都钉住了就换掉第二个)。 */
  const put = (robot: string) => setPins((p) => (p[0] == null || p[1] != null && p[0] !== robot ? [robot, p[1]] : [p[0], robot]));

  const zoneOf = (u: UnitInfo): string => {
    const p = u.robot.loc?.pose;
    if (!p) return "";
    return areas.find((a) => pointInPolygon([p.x, p.y], a.pts))?.name ?? "";
  };

  const slot = (s: SlotPick | null, i: 0 | 1) => {
    const u = s ? unitOf(s.robot) : undefined;
    if (!s || !u) return <div class="slot empty-slot" />;
    return (
      <VideoSlot key={`${i}:${s.robot}:${s.alert?.key ?? ""}`} u={u} now={props.now} pinned={pins[i] === s.robot}
        onPin={() => pin(i, s.robot)} onZoom={() => props.onZoom(s.robot)}
        forceLive={!!s.alert} scene={sceneOf(s.alert)} alarm={!!s.alert} />
    );
  };

  const online = props.units.filter((u) => u.state !== "offline").length;
  // P0-06:「全部急停」以后每台都叫停着,要人恢复;不是「一切正常」
  const held = props.units.filter((u) => u.robot.held != null);
  const [askResume, setAskResume] = useState(false);
  async function resumeAll() {
    setAskResume(false);
    const res = await Promise.allSettled(held.map((u) => api("POST", `/api/robots/${enc(u.robot.robot_id)}/resume`, {})));
    const bad = res.filter((r) => r.status === "rejected").length;
    props.say(bad ? t("failed", { why: `${bad}/${held.length}` }) : t("dutyResumed", { n: held.length }));
    await props.refresh();
  }
  return (
    <div class="duty">
      {top ? (
        <div class={top.level === "P1" ? "banner" : "banner p2"} role="alert">
          <Shape kind={top.level === "P1" ? "P1" : "P2"} />
          <div class="banner-text">
            <b>{alertHeadline(top)}</b>
            <span>{[top.context?.zone ?? (top.context?.where ? t("atWhere", { w: top.context.where }) : ""), hm(top.first_ms)].filter(Boolean).join(" · ")}</span>
            {top.context?.lost_ms != null && <span class="banner-who">{t("dutyLost")}</span>}
            {top.context?.follow === "follow" && <span class="banner-who">{t("dutyFollowing")}</span>}
            {top.context?.follow !== "follow" && top.context?.person?.where && <span class="banner-who">{t("dutyLastAt", { w: top.context.person.where })}</span>}
            {top.context?.arrived_by ? <span class="banner-who">{t("dutyArrived", { who: top.context.arrived_by })}</span>
              : mustArrive(top) ? <span class="banner-who">{t("dutyArriveFirst")}</span>
              : top.acked_ms != null && top.acked_by && <span class="banner-who">{t("dutyTakenBy", { who: byText(top.acked_by) })}</span>}
            {alarms.length > 1 && <span class="banner-more">{t("dutyMore", { n: alarms.length - 1 })}</span>}
          </div>
          <div class="banner-acts">
            {can && top.acked_ms == null && <button type="button" class="btn onsolid" onClick={() => ack(top)}>{t("dutyTake")}</button>}
            {can && mustArrive(top) && <button type="button" class="btn onsolid" onClick={() => arrive(top)}>{t("dutyArrive")}</button>}
            {can && LOST.has(top.kind) && (
              <button type="button" class="btn onsolid" onClick={() => { setFinding(top.robot); setSelected(top.robot); }}>{t("dutyFindPose")}</button>
            )}
            <button type="button" class="btn onsolid ghost" onClick={() => setDetail(top.key)}>{t(can && !mustArrive(top) ? "dutyDetailClose" : "dutyDetail")}</button>
          </div>
        </div>
      ) : props.stale ? (
        <p class="allclear unknown" role="status">
          <i class="dot" aria-hidden="true" /><b>{t("dutyUnknown")}</b>
          <span>{t("dutyUnknownSub")}</span>
        </p>
      ) : held.length > 0 ? (
        <div class="banner p2" role="status">
          <Shape kind="P2" />
          <div class="banner-text">
            <b>{t("dutyHeld", { n: held.length })}</b>
            <span>{held.map((u) => nameOf(u.robot.robot_id)).join("、")} · {t("dutyHeldSub")}</span>
          </div>
          {canDispatch(props.role) && (
            <div class="banner-acts">
              <button type="button" class="btn onsolid" onClick={() => setAskResume(true)}>{t("dutyResumeAll")}</button>
            </div>
          )}
        </div>
      ) : (
        <p class="allclear" role="status">
          <i class="dot" aria-hidden="true" /><b>{t("dutyAllClear")}</b>
          {props.mode && <span>{modeLabel(props.mode)}</span>}
          <span>{t("dutyOnline", { n: online, m: props.units.length })}</span>
        </p>
      )}
      <section class="dcard duty-mapcard" aria-label={t("tabMap")}>
        <h2 class="dcard-h">{t("tabMap")}</h2>
        <div class="duty-map">
          <SiteMap units={props.units} p1={alarms.filter((a) => a.level === "P1")} now={props.now} role={props.role} stale={props.stale}
            selected={finding ?? selected ?? slots[0]?.robot ?? null} onSelect={setSelected} hot={hot} episodes={false}
            hint={finding ? t("dutyFindHint", { id: finding }) : null} pick={!!finding}
            onLocated={(id) => { setFinding(null); props.say(t("locDoneMsg", { id: nameOf(id) })); }}
            onAreas={(a) => setAreas((old) => (sameAreas(old, a) ? old : a))} />
          {finding && <p class="sr-only">{t("dutyFindHint", { id: finding })}</p>}
        </div>
      </section>
      <section class="dcard duty-alarms" aria-label={t("dutyAlarmsTitle")}>
        <h2 class="dcard-h">{t("dutyAlarmsTitle")}<span class="mono muted push">{alarms.length}</span></h2>
        {alarms.length === 0 && <p class={props.stale ? "warn dcard-empty" : "muted dcard-empty"}>{t(props.stale ? "dutyStaleAlarms" : "dutyNoAlarms")}</p>}
        <ul class="alarmlist">
          {alarms.map((a) => (
            <li key={a.key} class={a.level === "P1" ? "p1" : "p2"}>
              <Shape kind={a.level === "P1" ? "P1" : "P2"} />
              <button type="button" class="alarmlist-main" onClick={() => { setSelected(a.robot); setDetail(a.key); }}>
                <b>{alertHeadline(a)}</b>
                <span class="muted small">{[a.context?.zone ?? (a.context?.where ?? ""), nameOf(a.robot)].filter(Boolean).join(" · ")}</span>
              </button>
              <span class="mono small alarmlist-t">{a.level} · {hm(a.first_ms)}</span>
            </li>
          ))}
        </ul>
      </section>
      <section class="dcard duty-video" aria-label={t("dutyVideo")}>
        <h2 class="dcard-h">{t("dutyVideo")}</h2>
        <div class="duty-slots">
          {slot(slots[0], 0)}
          {slot(slots[1], 1)}
        </div>
      </section>
      <section class="dcard duty-left" aria-label={t("robots")}>
        <h2 class="dcard-h">{t("robots")}</h2>
        <ul class="duty-list" aria-label={t("robots")}>
          {ranked.length === 0 && <li class={props.stale ? "warn" : "muted"}>{t(props.stale ? "dutyStaleRobots" : "dutyNoRobots")}</li>}
          {ranked.map((u) => (
            <li key={u.robot.robot_id}>
              <button type="button" class={selected === u.robot.robot_id ? "duty-row on" : "duty-row"}
                onClick={() => { put(u.robot.robot_id); setSelected(u.robot.robot_id); }}>
                <span class="unit-id mono">{nameOf(u.robot.robot_id)}</span>
                <StateText s={u.state} stale={u.stale} />
                <span class="muted small">{zoneOf(u)}</span>
                {u.battery != null && <span class="batt push">{Math.round(u.battery)}%</span>}
              </button>
              {/* P2-08:点行 = 放进画面位;「详情」打开这台的详情(能看机器人页的去机器人页,别的去地图上找它) */}
              <a class="btn sm duty-row-more" data-robot-more={u.robot.robot_id}
                href={pageAllowed("admin/robots", props.role) ? `#/admin/robots?robot=${enc(u.robot.robot_id)}` : `#/map?robot=${enc(u.robot.robot_id)}`}
                aria-label={t("dutyRobotMore", { id: nameOf(u.robot.robot_id) })}>{t("dutyDetails")}</a>
            </li>
          ))}
        </ul>
        <TodayPatrols />
      </section>
      {askResume && (
        <Confirm text={t("dutyResumeAsk", { n: held.length })} yes={t("dutyResumeAll")} onNo={() => setAskResume(false)} onYes={resumeAll} />
      )}
      {shown && (
        <AlertDetail a={shown} role={props.role} now={props.now} units={props.units} onClose={() => setDetail(null)}
          refresh={props.refresh} say={props.say} onFindPose={(r) => { setFinding(r); setSelected(r); }} />
      )}
    </div>
  );
}

/** 区域换没换(名字和点一样就算没换,不重画)。 */
function sameAreas(a: CanvasArea[], b: CanvasArea[]): boolean {
  return a.length === b.length && a.every((x, i) => x.name === b[i].name && JSON.stringify(x.pts) === JSON.stringify(b[i].pts));
}

const PINS_KEY = "nexwar.duty.pins";
function loadPins(): [string | null, string | null] {
  try {
    const v = JSON.parse(localStorage.getItem(PINS_KEY) ?? "null");
    if (Array.isArray(v) && v.length === 2 && v.every((x) => x === null || typeof x === "string")) return [v[0], v[1]];
  } catch { /* 读不到就不钉 */ }
  return [null, null];
}

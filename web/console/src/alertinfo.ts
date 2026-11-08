// 网页易用性第 1 轮(11-07):警报说清楚「怎么回事、该做什么」,派机器人出去后如实说它走没走。
// - P0-01:出发前检查没过(站点 preflight_refused,context.check 是哪一项)按那一项写原因和办法。
// - P0-03:机器人先回执收下、再做出发前检查;收下 ≠ 出发了。派出后盯一会儿,被拒就说被拒和原因。
import { api, ApiError } from "./api";
import { alertTitle, lang, type Lang } from "./i18n";
import type { Alert } from "./model";
import { siteStr } from "./sitetext";

const en = {
  pfHome: "the map has no origin yet",
  pfHomeDo: "Localize the robot on this map, then press “Mark origin here” on the Localization page (or in the phone app).",
  pfLocalized: "localization is not settled",
  pfLocalizedDo: "Help it find its position on the Localization page, then send it again.",
  pfDevice: "the robot is not ready (control or emergency stop)",
  pfDeviceDo: "Check that the emergency stop is released and the site has control.",
  pfNav: "navigation is not ready",
  pfNavDo: "Wait a minute and send it again. If it stays like this, check navigation on the Diagnostics page.",
  pfBattery: "battery too low to start",
  pfBatteryDo: "Charge it or swap the battery first.",
  pfStorage: "robot storage is full",
  pfStorageDo: "Free up space on the Diagnostics page.",
  pfRemovable: "robot storage has a problem",
  pfRemovableDo: "Check storage on the Diagnostics page.",
  pfOther: "see the details",
  pfOtherDo: "Read the site's details below.",
  sendChecking: "Sent to {id}. Checking that it can start…",
  sendStarted: "{id} is on its way",
  sendRefused: "{id} did not start: {why}. {act}",
  pfFailed: "Pre-departure check failed: {why}",
  batteryTurned: "battery low, it turned back",
  noReason: "reason not given — see Alarms",
  markHome: "Mark origin here",
  markHomeAsk: "Mark where {id} stands now as its origin on this map? The origin is where it returns and swaps batteries. Make sure it is localized (green) and standing at the right spot.",
  markHomeDone: "Origin marked for {id}",
  markHomeFail: "Could not mark the origin: {why}",
};
type AKey = keyof typeof en;
const zh: Record<AKey, string> = {
  pfHome: "地图还未标原点",
  pfHomeDo: "让机器人在这张地图上定好位，再到「定位」页（或手机 App）点「在这儿标原点」。",
  pfLocalized: "定位还未稳定",
  pfLocalizedDo: "到「定位」页帮它找位置，定好后再派。",
  pfDevice: "机器人还未就绪（控制权或急停）",
  pfDeviceDo: "看急停是否已松开、控制权是否在站点。",
  pfNav: "导航还未就绪",
  pfNavDo: "等一分钟再派；一直不好就到「诊断」页看导航。",
  pfBattery: "电量不够出发",
  pfBatteryDo: "先去充电或换电池。",
  pfStorage: "机器人存储空间不足",
  pfStorageDo: "到「诊断」页清理空间。",
  pfRemovable: "机器人存储设备有问题",
  pfRemovableDo: "到「诊断」页看存储。",
  pfOther: "原因见详情",
  pfOtherDo: "看下面站点给的详情。",
  sendChecking: "已发给 {id}，正在确认它能出发…",
  sendStarted: "{id} 已出发",
  sendRefused: "{id} 没有出发：{why}。{act}",
  pfFailed: "出发前检查未通过：{why}",
  batteryTurned: "电量不足，中途返回",
  noReason: "没有写原因，去报警记录看",
  markHome: "在这儿标原点",
  markHomeAsk: "把 {id} 现在站的位置标成这张地图上的原点？原点是它返航、换电池的地方。请确认它定位良好（绿色）并站在正确的位置。",
  markHomeDone: "已给 {id} 标好原点",
  markHomeFail: "标原点失败：{why}",
};
const DICTS: Record<Lang, Record<AKey, string>> = { en, zh };

export function at(key: AKey, vars?: Record<string, string | number>): string {
  let s = DICTS[lang.value][key] ?? en[key];
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

/** 出发前检查的各项(狗上 engine/preflight.py 的名字)→ 原因、办法的词条。 */
const PREFLIGHT: Record<string, [AKey, AKey]> = {
  home: ["pfHome", "pfHomeDo"],
  localized: ["pfLocalized", "pfLocalizedDo"],
  device_ready: ["pfDevice", "pfDeviceDo"],
  nav_ready: ["pfNav", "pfNavDo"],
  battery: ["pfBattery", "pfBatteryDo"],
  storage: ["pfStorage", "pfStorageDo"],
  removable: ["pfRemovable", "pfRemovableDo"],
};

function preflightKeys(a: Alert): [AKey, AKey] {
  const c = (a.context as { check?: string } | undefined)?.check;
  return (c && PREFLIGHT[c]) || ["pfOther", "pfOtherDo"];
}

/** 网页易用性 P1-14:站点给的巡逻失败原因(机器人上的原话,常带检查项名、括号里的细节)翻成人话;
 *  认不出的原样给(悬停看全文)。 */
export function plainReason(raw: string): string {
  const pf = /起飞前检查未通过[:：]\s*([a-z_]+)/.exec(raw);
  if (pf) return at("pfFailed", { why: at((PREFLIGHT[pf[1]] ?? ["pfOther"])[0]) });
  if (/电量\s*[\d.]+%\s*低于中止线/.test(raw)) return at("batteryTurned");
  // 第 3 轮 admin N7:被人按「停止」停下的,站点记的是原始代码 halt
  if (/^(halt|stop|stopped)$/i.test(raw.trim())) return lang.value === "zh" ? "被人停下" : "stopped by hand";
  // 第 2 轮 P1-01:英文界面别的原因也翻(中文界面原样)
  return siteStr(raw);
}

/** 没走完却没写原因的(P1-14):说去哪儿看。 */
export function missingReason(): string {
  return at("noReason");
}

/** 警报标题:按种类的固定标题;出发前检查没过的再接上是哪一项。 */
export function alertHeadline(a: Alert): string {
  const base = alertTitle(lang.value, a.kind, a.title);
  if (a.kind !== "preflight_refused") return base;
  return `${base}${lang.value === "zh" ? "：" : ": "}${at(preflightKeys(a)[0])}`;
}

/** 该做什么(认得的才有)。 */
export function alertAdvice(a: Alert): string | null {
  if (a.kind === "preflight_refused") return at(preflightKeys(a)[1]);
  return null;
}

/** 能处理警报的(站点 HANDLE_ALERTS):管理员、工程师、保安、经理。只读账号不能。 */
export function canHandleAlerts(role: string): boolean {
  return role === "admin" || role === "engineer" || role === "guard" || role === "owner";
}

/** 站点的钟跟浏览器的钟可能差几秒:被拒的那条落在发出前这么久内也算(同一个原因多半还在)。 */
const CLOCK_SLACK_MS = 30_000;

export type StartCheck = { state: "started" } | { state: "refused"; why: string; act: string } | { state: "unknown" };

/** 派出后盯一会儿(P0-03):这台在 ``sentAt`` 以后出了「出发前检查未通过」就是被拒;
 *  盯完都没有就算出发了。站点问不通(断线)就是 ``unknown``,别说出发了。 */
export async function watchStart(id: string, sentAt: number,
  o: { tries?: number; gapMs?: number; sleep?: (ms: number) => Promise<void>; robot?: string } = {}): Promise<StartCheck> {
  const rid = o.robot ?? id;
  const tries = o.tries ?? 8;
  const gap = o.gapMs ?? 1500;
  const sleep = o.sleep ?? ((ms: number) => new Promise<void>((r) => window.setTimeout(r, ms)));
  let reached = false;
  for (let i = 0; i < tries; i++) {
    await sleep(gap);
    try {
      const d = await api<{ alerts: Alert[] }>("GET", `/api/alerts?all=1&limit=50`);
      reached = true;
      const hit = (d.alerts ?? []).find((a) => a.robot === rid && a.kind === "preflight_refused"
        && Math.max(a.first_ms, a.last_ms) >= sentAt - CLOCK_SLACK_MS);
      if (hit) {
        const [why, act] = preflightKeys(hit);
        return { state: "refused", why: at(why), act: at(act) };
      }
    } catch (e) {
      if (!(e instanceof ApiError)) continue;
    }
  }
  return reached ? { state: "started" } : { state: "unknown" };
}

/** 派出去以后的一整套提示:先说「已发,正在确认」,确认完再说走了没走。 */
export async function reportStart(id: string, sentAt: number, say: (s: string) => void,
  o?: Parameters<typeof watchStart>[2]): Promise<StartCheck> {
  say(at("sendChecking", { id }));
  const r = await watchStart(id, sentAt, o);
  if (r.state === "refused") say(at("sendRefused", { id, why: r.why, act: r.act }));
  else if (r.state === "started") say(at("sendStarted", { id }));
  return r;
}

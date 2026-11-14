// 第三档 #40(用户 11-14):网页的报警弹窗和声音,跟站点的升档(alerts.ESCALATE_AFTER_MS)走。
// - 新来一条没确认的 P1 / P2(给保安看的那些):右下角弹卡片,响一声(P1 高、P2 低)。P3 不弹不响。
//   值守页不弹(那里有横幅),照样响。「关闭」只关这一条,只在这个标签页里。
// - 升到「声音」档(channel === "sound":入侵一来就是,别的 P1 没人确认 5 分钟)一直响,有人确认才停
//   (跟手机 alertWantsSound 一样)。关卡片不停。
// - 只有能处理报警的角色响;声音开关记在这台浏览器上(账号菜单)。
// - 浏览器刷新后没点过页面不让出声:卡片上给一个「点这里开声音」。
import { signal } from "@preact/signals";
import type { JSX } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { alertHeadline, canHandleAlerts } from "./alertinfo";
import { hm, nameOf } from "./data";
import { guardAlarms } from "./dutyrank";
import { t } from "./i18n";
import { Shape } from "./icons";
import type { Alert } from "./model";

const SOUND_KEY = "nexwar.alarmSound";

function loadSound(): boolean {
  try { return localStorage.getItem(SOUND_KEY) !== "off"; } catch { return true; }
}

/** 这台浏览器响不响报警(缺省响)。 */
export const alarmSound = signal<boolean>(loadSound());

export function setAlarmSound(on: boolean): void {
  alarmSound.value = on;
  try {
    if (on) localStorage.removeItem(SOUND_KEY);
    else localStorage.setItem(SOUND_KEY, "off");
  } catch { /* 隐私模式:不记 */ }
}

/** 出声的那一层;测试换成假的。 */
export interface Beeper {
  /** 响一声:P1 高两声、P2 低一声。 */
  chime(level: "P1" | "P2"): void;
  /** 一直响(每 2 秒一遍)/ 停。 */
  ring(on: boolean): void;
  /** 浏览器让不让出声(刷新后没点过页面不让)。 */
  ready(): boolean;
  /** 在一次点击里解锁出声。 */
  unlock(): void;
}

/** 升到声音档、没人确认、没解决(跟手机 alertWantsSound 一样)。 */
export function wantsRing(a: Alert): boolean {
  return a.level === "P1" && a.channel === "sound" && a.acked_ms == null && a.resolved_ms == null;
}

/** 用 WebAudio 合成的提示音:不带音频文件,离线也响。 */
export function webBeeper(): Beeper {
  type Ctx = AudioContext;
  let ctx: Ctx | null = null;
  let timer = 0;
  const get = (): Ctx | null => {
    if (ctx) return ctx;
    const C = (window as unknown as { AudioContext?: new () => Ctx; webkitAudioContext?: new () => Ctx }).AudioContext
      ?? (window as unknown as { webkitAudioContext?: new () => Ctx }).webkitAudioContext;
    if (!C) return null;
    try { ctx = new C(); } catch { return null; }
    return ctx;
  };
  const tone = (hz: number, at: number, len: number, vol = 0.25) => {
    const c = get();
    if (!c || c.state !== "running") return;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = "square";
    o.frequency.value = hz;
    const t0 = c.currentTime + at;
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(vol, t0 + 0.01);
    g.gain.setValueAtTime(vol, t0 + len - 0.03);
    g.gain.linearRampToValueAtTime(0, t0 + len);
    o.connect(g).connect(c.destination);
    o.start(t0);
    o.stop(t0 + len + 0.02);
  };
  const siren = () => { tone(988, 0, 0.3); tone(740, 0.35, 0.3); tone(988, 0.7, 0.3); tone(740, 1.05, 0.3); };
  // 浏览器要一次点击才让出声:页面上随便点一下就解锁(不用非得点卡片上的按钮)
  const onGesture = () => { const c = get(); if (c && c.state !== "running") void c.resume(); };
  if (typeof document !== "undefined") document.addEventListener("pointerdown", onGesture, true);
  return {
    chime(level) {
      if (level === "P1") { tone(988, 0, 0.18); tone(1319, 0.22, 0.28); } else tone(660, 0, 0.25, 0.18);
    },
    ring(on) {
      window.clearInterval(timer);
      timer = 0;
      if (!on) return;
      siren();
      timer = window.setInterval(siren, 2000);
    },
    ready() {
      const c = get();
      return c != null && c.state === "running";
    },
    unlock() { onGesture(); },
  };
}

let shared: Beeper | null = null;
const defaultBeeper = (): Beeper => (shared ??= webBeeper());

/** 账号菜单里打开声音时试听一声(这次点击顺带解锁出声;解锁要一小会儿,稍等再响)。 */
export function testChime(): void {
  const b = defaultBeeper();
  b.unlock();
  window.setTimeout(() => b.chime("P1"), 150);
}

export function AlarmPop(props: {
  /** 没搁置的报警(console 的 active)。 */
  alerts: Alert[];
  role: string;
  /** 在值守页:那里有横幅,不弹,照样响。 */
  onDuty: boolean;
  onAck: (a: Alert) => void;
  onGo: () => void;
  beeper?: Beeper;
}): JSX.Element | null {
  const beeper = props.beeper ?? defaultBeeper();
  const can = canHandleAlerts(props.role);
  const loud = can && alarmSound.value;
  const open = useMemo(() => guardAlarms(props.alerts).filter((a) => a.acked_ms == null), [props.alerts]);
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const chimed = useRef(new Set<string>());
  const ring = loud && open.some(wantsRing);
  // 只为重画:点了「开声音」以后把那一行收掉
  const [, setTick] = useState(0);

  // 新来的(这个标签页里第一次见到)响一声;P1 先响(guardAlarms 已经排好),一次只响一声
  useEffect(() => {
    const fresh = open.filter((a) => !chimed.current.has(a.key));
    for (const a of fresh) chimed.current.add(a.key);
    if (loud && fresh.length) beeper.chime(fresh.some((a) => a.level === "P1") ? "P1" : "P2");
  }, [open, loud]);

  useEffect(() => {
    beeper.ring(ring);
  }, [ring]);
  useEffect(() => () => beeper.ring(false), []);

  if (props.onDuty) return null;
  const shown = open.filter((a) => !closed.has(a.key));
  const top = shown[0];
  if (!top) return null;
  const p1 = top.level === "P1";
  const where = top.context?.zone ?? (top.context?.where ? t("atWhere", { w: top.context.where }) : "");
  return (
    <div class={p1 ? "alarm-pop" : "alarm-pop p2"} role="alert" data-alarm-pop="1" data-level={top.level}>
      <div class="alarm-pop-head">
        <Shape kind={p1 ? "P1" : "P2"} />
        <b>{alertHeadline(top)}</b>
        {/* UIUX-048:× 把眼下这几条一起收起(以前只关一条、下一条马上补上来);再来新的照样弹,没确认的照样响 */}
        <button type="button" class="alarm-pop-x" aria-label={t("popHideAll")} title={t("popHideAll")}
          onClick={() => setClosed(new Set([...closed, ...shown.map((a) => a.key)]))}>×</button>
      </div>
      <span class="alarm-pop-sub">{[top.robot ? nameOf(top.robot) : "", where, hm(top.first_ms),
        shown.length > 1 ? t("dutyMore", { n: shown.length - 1 }) : ""].filter(Boolean).join(" · ")}</span>
      {can && !alarmSound.value && <span class="alarm-pop-note">{t("popSoundOff")}</span>}
      {ring && !beeper.ready() && (
        <button type="button" class="btn sm" onClick={() => { beeper.unlock(); setTick((n) => n + 1); }}>{t("popUnlock")}</button>
      )}
      <div class="alarm-pop-acts">
        {can && <button type="button" class="btn sm onsolid" onClick={() => props.onAck(top)}>{t("dutyTake")}</button>}
        <button type="button" class="btn sm onsolid ghost" onClick={props.onGo}>{t("popGo")}</button>
      </div>
    </div>
  );
}

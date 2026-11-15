// 值班台外壳(W44 第一期,设计 §4.0;W60 改版):路由、左侧导航、顶栏、用户菜单、主题。
// 左侧导航:品牌、站点名,按角色分「值班 / 管理 / 系统」三组(高级默认收着)。
// 顶栏只有:页面名、布防状态(只显示)、报警数、时钟、帮助、用户名下拉(语言、外观、改密码、退出)、全部急停。
// W60:全站默认深色(不再按页面换深浅色),浅色在「外观」里个人选。
import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import type { Me } from "./app";
import { alarmSound, setAlarmSound, testChime } from "./alarmpop";
import { canHandleAlerts } from "./alertinfo";
import { modeLabel } from "./armingpage";
import { Confirm, Modal } from "./dialogs";
import { hm, siteClock } from "./data";
import { lang, setLang, t, type Key } from "./i18n";
import { Icon, Shape } from "./icons";
import { canArm, canDispatch, isOwnerLike, type Mode } from "./model";

export type GuardPage = "duty" | "live" | "map" | "recordings" | "alarms" | "notes";
/** 「管理」各页(W44 第二期,设计 §5):常用 = 现场概况、布防时间、授权和临时撤防、用户、机器人、报表;
 *  布置、高级两组先挂现有页面(第三、四期重做)。 */
export type AdminPage =
  | "admin/home" | "admin/arming" | "admin/access" | "admin/users" | "admin/robots" | "admin/reports"
  | "admin/layout" | "admin/maps" | "admin/localization" | "admin/diag" | "admin/upgrade" | "admin/system"
  | "admin/activity"
  | "admin/mapedit";
export type Page = GuardPage | AdminPage;

/** 「实时画面」「地图」两页并进了值班页(redesign 第二轮):老地址跳值班。 */
export const GUARD_PAGES: GuardPage[] = ["duty", "recordings", "alarms", "notes"];

/** 顶栏的三个大块(redesign 第二轮,design/console-v2/HANDOFF.md):值班 / 记录与录像 / 现场设置。 */
export type Section = "monitor" | "events" | "setup";
export const SECTIONS: { id: Section; key: Key }[] = [
  { id: "monitor", key: "secMonitor" }, { id: "events", key: "secEvents" }, { id: "setup", key: "secSetup" },
];

/** 现场设置左栏的一项:点了去 ``id``;``also`` 里的页也算在这一项下面(页里有一排小标签切换)。 */
export interface SetupItem { id: AdminPage; key: Key; badge?: "notices"; also?: AdminPage[] }
export interface SetupGroup { id: "daily" | "site" | "records" | "advanced"; key: Key; items: SetupItem[] }
/** 现场设置左栏(HANDOFF):日常[概况, 机器人, 人员] 现场[布置, 布防与巡逻, 授权] 记录[报告] 高级[维护]。 */
export const SETUP_NAV: SetupGroup[] = [
  { id: "daily", key: "setDaily", items: [
    { id: "admin/home", key: "setOverview", badge: "notices" }, { id: "admin/robots", key: "setRobots" }, { id: "admin/users", key: "setUsers" },
  ] },
  { id: "site", key: "setSite", items: [
    { id: "admin/layout", key: "setLayout" }, { id: "admin/arming", key: "setArming" }, { id: "admin/access", key: "setAccess" },
  ] },
  { id: "records", key: "setRecords", items: [{ id: "admin/reports", key: "setReports", also: ["admin/activity"] }] },
  { id: "advanced", key: "setAdvanced", items: [
    { id: "admin/system", key: "setMaint", also: ["admin/maps", "admin/localization", "admin/diag", "admin/upgrade", "admin/mapedit"] },
  ] },
];
/** 一个大块(或现场设置的一项)里的几页,页头下面一排小标签切换。 */
export const SUBPAGES: { pages: Page[]; keys: Key[] }[] = [
  { pages: ["alarms", "recordings", "notes"], keys: ["subEvents", "subRecordings", "subNotes"] },
  { pages: ["admin/reports", "admin/activity"], keys: ["tabReports", "subAudit"] },
  { pages: ["admin/system", "admin/upgrade", "admin/maps", "admin/localization", "admin/diag"],
    keys: ["subSite", "tabUpgrade", "tabMapMgmt", "tabLocalization", "tabDiag"] },
];
const ADMIN_PAGES: AdminPage[] = SETUP_NAV.flatMap((g) => g.items.flatMap((x) => [x.id, ...(x.also ?? [])]));

export function sectionOf(p: Page): Section {
  if (p === "alarms" || p === "recordings" || p === "notes") return "events";
  return isAdminPage(p) ? "setup" : "monitor";
}

/** 这一页在现场设置左栏里算哪一项。 */
export function setupItemOf(p: Page): SetupItem | null {
  for (const g of SETUP_NAV) for (const x of g.items) if (x.id === p || x.also?.includes(p as AdminPage)) return x;
  return null;
}

/** 这个角色在现场设置左栏里看得到的组、项(没权限的不列,空组不列)。 */
export function setupNavFor(role: string): SetupGroup[] {
  return SETUP_NAV.map((g) => ({ ...g, items: g.items.filter((x) => pageAllowed(x.id, role)) })).filter((g) => g.items.length > 0);
}

/** 点顶栏「现场设置」去哪一页(这个角色能开的第一项);一项都开不了是 ``null``(顶栏不放这一块)。 */
export function setupHome(role: string): AdminPage | null {
  return setupNavFor(role)[0]?.items[0]?.id ?? null;
}

/** 页面的名字(浏览器标签、帮助用):所在大块 + 页名。 */
export function navLabel(page: Page): { section: Key; page: Key } | null {
  const sec = SECTIONS.find((x) => x.id === sectionOf(page))!.key;
  if (page === "duty" || page === "live" || page === "map") return { section: sec, page: "secMonitor" };
  const sub = SUBPAGES.find((g) => g.pages.includes(page));
  if (sub && !isAdminPage(page)) return { section: sec, page: sub.keys[sub.pages.indexOf(page)] };
  const it = setupItemOf(page);
  if (!it) return null;
  if (sub && page !== it.id) return { section: sec, page: sub.keys[sub.pages.indexOf(page)] };
  return { section: sec, page: page === "admin/mapedit" ? "tabMapMgmt" : it.key };
}
/** 改版前的地址(书签、手机分享的链接)。 */
const LEGACY: Record<string, Page> = {
  localization: "admin/localization", reports: "admin/reports", "admin/notices": "admin/home", "admin/lists": "admin/access",
  "admin/zones": "admin/layout", "admin/routes": "admin/layout", live: "duty", map: "duty",
};

export interface Route {
  page: Page;
  robot: string | null;
  at: number | null;
  /** 值班页打开哪一件(报警记录页的「Respond」)。 */
  alarm?: string | null;
}

export function readRoute(hash: string = typeof location === "undefined" ? "" : location.hash): Route {
  const [p, q] = hash.replace(/^#\/?/, "").split("?");
  const qs = new URLSearchParams(q ?? "");
  const at = Number(qs.get("t") ?? "");
  const page: Page = (GUARD_PAGES as string[]).includes(p) || (ADMIN_PAGES as string[]).includes(p)
    ? (p as Page) : LEGACY[p] ?? "duty";
  return { page, robot: qs.get("robot"), at: at > 0 ? at : null, alarm: qs.get("alarm") };
}

export function isAdminPage(p: Page): p is AdminPage {
  return p.startsWith("admin/");
}

/** 角色的界面名字(设计 §3):admin 叫管理员,owner 叫经理,engineer 是工程师(临时)。 */
export function roleLabel(role: string): Key {
  return role === "admin" ? "roleOwner" : role === "guard" ? "roleGuard" : role === "engineer" ? "roleEngineer"
    : role === "viewer" ? "roleViewer" : "roleFamily";
}

/** 顶栏账号后面的短角色名(「gina · Guard」)。 */
export function roleShort(role: string): Key {
  return role === "admin" ? "roleShortAdmin" : role === "guard" ? "roleGuard" : role === "engineer" ? "roleShortEngineer"
    : role === "viewer" ? "roleViewer" : "roleFamily";
}

/** 页面默认的明暗(redesign,用户 2026-11-14「两种都有」):保安页深色(夜间值班室),管理页浅色(白天办公室)。
 *  W60 当初嫌切页面像进了另一个系统 —— 现在侧栏两套都是深石墨色的「立柱」,标识语言一致,深浅只换工作区。 */
export function pageScheme(p: Page): "dark" | "light" {
  return isAdminPage(p) ? "light" : "dark";
}

/** 个人在「外观」里的选择:默认(深色)、跟随系统、一直深色、一直浅色。 */
export type ThemePref = "auto" | "system" | "dark" | "light";
const PREF_KEY = "nexwar.look";

export function schemeFor(p: Page, pref: ThemePref, systemDark: boolean): "dark" | "light" {
  if (pref === "dark" || pref === "light") return pref;
  if (pref === "system") return systemDark ? "dark" : "light";
  return pageScheme(p);
}

/** 外壳要把主题定成哪一套:选了「跟随系统」就不定(``null``),交给系统换颜色的事件 —— 定成「当时」那一套的话,
 *  系统后来再换就不跟了(真浏览器实测查出来的)。 */
export function pinFor(p: Page, pref: ThemePref, systemDark: boolean): "dark" | "light" | null {
  return pref === "system" ? null : schemeFor(p, pref, systemDark);
}

/** 这个角色能不能开这一页(管理那几页要管理员、经理、工程师;「用户」只有管理员)。没权限的写清楚,不给空白页(演示站点实测查出)。 */
export function pageAllowed(p: Page, role: string): boolean {
  if (!isAdminPage(p)) return true;
  if (p === "admin/users") return role === "admin";
  // W53:经理能排布防时间(App 里排巡逻日程,布防时间在这里)。W60:经理也看机器人(只看)、报表
  if (p === "admin/arming" || p === "admin/robots" || p === "admin/reports") return isOwnerLike(role) || role === "owner";
  return isOwnerLike(role);
}

export function loadThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(PREF_KEY);
    return v === "system" || v === "dark" || v === "light" ? v : "auto";
  } catch {
    return "auto";
  }
}

export function saveThemePref(v: ThemePref): void {
  try {
    localStorage.setItem(PREF_KEY, v);
  } catch {
    /* 存不下就只管这一次 */
  }
}

/** 顶栏(redesign 第二轮,HANDOFF「结构」):左 品牌、站点名、三个大块;右 布防状态、机器人在线、未处理数、时间、账号、全部急停。 */
export function TopBar(props: {
  me: Me;
  page: Page;
  mode: Mode | null;
  /** 给保安看的未解决 P1、P2 有几条;数据过期时是 null(说不清)。 */
  alarms: number | null;
  /** 机器人在线几台 / 一共几台;没数据是 null。 */
  robots?: { on: number; all: number } | null;
  now: number;
  pref: ThemePref;
  onPref: (p: ThemePref) => void;
  onStop: () => void;
  /** 易用性第 6 轮 W6-05:顶栏点布防状态切模式(外壳弹确认、发请求);不给就只显示。 */
  onMode?: (m: Mode["mode"]) => void;
  /** 第 2 轮 duty N10:有几台被叫停、等人点恢复(哪一页都看得见,点了去值班恢复)。 */
  held?: number;
  stale?: boolean;
  onSignOut: (note?: string) => void;
  onSay: (s: string) => void;
  /** 「?」:使用教程、常见问题(W53)。 */
  onHelp?: () => void;
}) {
  const cur = sectionOf(props.page);
  const setup = setupHome(props.me.role);
  const href: Record<Section, string | null> = { monitor: "#/duty", events: "#/alarms", setup: setup ? `#/${setup}` : null };
  useEffect(() => { document.title = tabTitle(props.page); }, [props.page, lang.value]);
  const clock = siteClock(props.now, props.mode?.timezone);
  return (
    <header class="topbar">
      <BrandMark />
      <span class="topbar-site" title={props.me.site_name}>{props.me.site_name}</span>
      <nav class="topnav" aria-label={t("mainNav")}>
        {SECTIONS.filter((x) => href[x.id]).map((x) => (
          <a key={x.id} href={href[x.id]!} aria-current={cur === x.id ? "page" : undefined}>{t(x.key)}</a>
        ))}
      </nav>
      <span class="topbar-gap" />
      {props.mode && <ArmState mode={props.mode} role={props.me.role} stale={props.stale} onMode={props.onMode} />}
      {props.held
        ? <a href="#/duty" class="chip-top bad" data-held-chip="1"><Shape kind="P1" size={12} />{t("topHeld", { n: props.held })}</a>
        : props.robots && (
          <span class="chip-top" data-robots-online="1">{t("robotsOnline", { a: props.robots.on, b: props.robots.all })}</span>
        )}
      <a href="#/alarms" class={props.alarms ? "chip-top alarmcount bad" : "chip-top alarmcount"} aria-live="polite">
        {!!props.alarms && <Shape kind="P1" size={12} />}
        {t("openCount", { n: props.alarms == null ? "?" : props.alarms })}
      </a>
      {/* P2-27:带上日期(值夜班跨零点看得清是哪天),日期放在悬停里 */}
      <span class="clock mono" data-tz={props.mode?.timezone ?? ""} title={(() => {
        const o: Intl.DateTimeFormatOptions = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
        const loc = lang.value === "zh" ? "zh-CN" : "en-GB";
        try { return new Date(props.now).toLocaleDateString(loc, props.mode?.timezone ? { ...o, timeZone: props.mode.timezone } : o); } catch { return new Date(props.now).toLocaleDateString(loc, o); }
      })()}>
        <span class="clock-date">{clock.md}</span>{" "}{clock.hm}
      </span>
      <UserMenu me={props.me} pref={props.pref} onPref={props.onPref} onSignOut={props.onSignOut} onSay={props.onSay} onHelp={props.onHelp} />
      {(canDispatch(props.me.role) || props.me.role === "owner") && (
        <button type="button" class="btn stop" onClick={props.onStop}><Shape kind="P1" size={12} />{t("stopAllTop")}</button>
      )}
    </header>
  );
}

/** 浏览器标签标题(网页易用性第 1 轮 P1-04):「页名 · Nexus Warden」,开好几个标签也分得清;跟着语言换。 */
export function tabTitle(page: Page): string {
  const l = navLabel(page);
  return l ? `${t(l.page)} · Nexus Warden` : "Nexus Warden";
}

/** 品牌标识(W60):外部设计的标志到了以后只换这一个组件。现在是文字。 */
export function BrandMark() {
  return (
    <span class="brandmark" aria-label="Nexus Warden">
      <span class="brandmark-a">NEXUS</span>
      <span class="brandmark-b">WARDEN</span>
    </span>
  );
}

/** 现场设置的左栏(HANDOFF):分组标题 + 项;当前项蓝底(蓝只给选中)。窄屏收进「菜单」。 */
export function SetupNav(props: { me: Me; page: Page; notices: number }) {
  const groups = setupNavFor(props.me.role);
  const cur = setupItemOf(props.page);
  const [menu, setMenu] = useState(false);
  useEffect(() => setMenu(false), [props.page]);
  const side = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!menu) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    const down = (e: PointerEvent) => { if (side.current && !side.current.contains(e.target as Node)) setMenu(false); };
    window.addEventListener("keydown", key);
    window.addEventListener("pointerdown", down);
    return () => { window.removeEventListener("keydown", key); window.removeEventListener("pointerdown", down); };
  }, [menu]);
  // 第 3 轮 admin N1:不对链接调 scrollIntoView,只滚侧栏里能滚的那一层
  useEffect(() => {
    const a = document.querySelector<HTMLElement>('.sidenav a[aria-current="page"]');
    if (a) revealInScroller(a);
  }, [props.page]);
  return (
    <aside class="sidenav" ref={side}>
      <button type="button" class="btn sm nav-toggle" aria-expanded={menu} aria-controls="setupnav" onClick={() => setMenu(!menu)}>
        {t("navMenu")}
      </button>
      <nav id="setupnav" class={menu ? "sidenav-nav open" : "sidenav-nav"} aria-label={t("secSetup")}>
        {groups.map((g) => (
          <div key={g.id} class="navgroup">
            <div class="navgroup-title">{t(g.key)}</div>
            {g.items.map((x) => (
              <a key={x.id} href={`#/${x.id}`} aria-current={cur?.id === x.id ? "page" : undefined}>
                <span>{t(x.key)}</span>
                {x.badge === "notices" && props.notices > 0 && <span class="badge mono">{props.notices}</span>}
              </a>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}

/** 一个大块(或现场设置一项)里几页之间的小标签;只列这个角色开得了的;只有一页就不放。 */
export function SubTabs({ page, role, rail }: { page: Page; role: string; rail?: boolean }) {
  const g = SUBPAGES.find((x) => x.pages.includes(page));
  if (!g) return null;
  // 记录与录像(G-records):三个标签在左栏最上面(页面自己放,rail),不在页头
  if (sectionOf(page) === "events" && !rail) return null;
  const items = g.pages.map((p, i) => ({ p, key: g.keys[i] })).filter((x) => pageAllowed(x.p, role));
  if (items.length < 2) return null;
  const on = page === "admin/mapedit" ? "admin/maps" : page;
  return (
    <nav class={rail ? "subtabs ev-tabs" : "subtabs"} aria-label={t(navLabel(page)?.section ?? "mainNav")}>
      {items.map((x) => (
        <a key={x.p} href={`#/${x.p}`} aria-current={on === x.p ? "page" : undefined}>{t(x.key)}</a>
      ))}
    </nav>
  );
}

/** 布防状态。易用性第 6 轮 W6-05(用户 11-11:保安也能撤防):能切的人点开就是布防 / 留守 / 临时撤防,
 *  确认框在外壳里(原来只在「系统状态」页最底下才找得到)。只看的账号照旧只显示。 */
function ArmState({ mode, role, stale, onMode }: { mode: Mode; role: string; stale?: boolean; onMode?: (m: Mode["mode"]) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", off);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  const text = mode.source === "schedule" ? modeLabel(mode) : mode.mode === "armed" ? t("armArmed")
    : mode.mode === "home" ? t("armHome")
    : t("armVisitor", { t: mode.until_ms ? hm(mode.until_ms) : "—" });
  // 第 2 轮 duty N11:连不上站点时变灰、写「最后已知」,不像一切正常
  const cls = stale ? "stale" : mode.source === "schedule" ? (mode.state === "armed" ? "armed" : "home") : mode.mode;
  const label = <><i class="dot" aria-hidden="true" />{stale ? t("lastKnown", { s: text }) : text}</>;
  const can = !!onMode && canArm(role);
  if (!can) {
    return <span class={`armstate ${cls}`} data-stale={stale || undefined} title={stale ? t("armStaleTip") : t("armStateTipViewer")}>
      {/* UIUX-034:切不了的不像按钮:写「只看」,样式去掉按钮感(styles.css span.armstate) */}
      {label}{!stale && <small class="armstate-ro" data-ro="1">{t("armViewOnly")}</small>}</span>;
  }
  const items: { m: Mode["mode"]; key: Key }[] = [{ m: "armed", key: "modeArmed" }, { m: "home", key: "modeHome" }, { m: "visitor", key: "modeVisitorAll" }];   // UIUX-035:顶栏这一项是全站 4 小时
  return (
    <div class="armmenu" ref={box}>
      <button type="button" class={`armstate ${cls}`} data-stale={stale || undefined} disabled={stale} aria-haspopup="menu" aria-expanded={open}
        title={stale ? t("armStaleTip") : t(pageAllowed("admin/arming", role) ? "armStateTip" : "armStateTipGuard")} onClick={() => setOpen(!open)}>{label}</button>
      {open && (
        <div class="menu armmenu-list" role="menu" data-mode-menu="1">
          {items.map((x) => (
            <button key={x.m} type="button" role="menuitem" aria-pressed={mode.source !== "schedule" && mode.mode === x.m}
              onClick={() => { setOpen(false); onMode!(x.m); }}>{t(x.key)}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function UserMenu(props: { me: Me; pref: ThemePref; onPref: (p: ThemePref) => void; onSignOut: (note?: string) => void; onSay: (s: string) => void;
  onHelp?: () => void }) {
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState(false);
  // undefined = 没开;"" = 读着;null = 读不到
  const [notices, setNotices] = useState<string | null | undefined>(undefined);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    // P2-22:Esc 关菜单,焦点回到按钮
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      box.current?.querySelector<HTMLButtonElement>("button.who")?.focus();
    };
    document.addEventListener("mousedown", off);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  const looks: { v: ThemePref; key: Key }[] = [
    // 第 3 轮 admin N9:「默认(深色)」跟「深色」一样,只留三个,深色标出是默认
    { v: "system", key: "lookSystem" }, { v: "dark", key: "lookDarkDefault" }, { v: "light", key: "lookLight" },
  ];
  return (
    <div class="usermenu" ref={box}>
      {/* 网页易用性第 1 轮 P0-16:窄屏只剩一个圆头像(首字),菜单还在:退出、语言、改密码都从这里 */}
      <button type="button" class="who" aria-haspopup="menu" aria-expanded={open} aria-label={t("userMenu")} onClick={() => setOpen(!open)}>
        <span class="who-initial" aria-hidden="true">{(props.me.display_name || props.me.name).slice(0, 1).toUpperCase()}</span>
        <span class="who-name">{props.me.display_name || props.me.name}<span class="who-role"> · {t(roleShort(props.me.role))}</span></span>
      </button>
      {open && (
        <div class="menu" role="menu">
          <div class="menu-head">
            <b>{props.me.display_name || props.me.name}</b>
            <span class="muted small">{t(roleLabel(props.me.role))}</span>
          </div>
          <div class="menu-row">
            <span class="muted small">{t("language")}</span>
            <div class="seg" role="group" aria-label={t("language")}>
              <button type="button" aria-pressed={lang.value === "en"} onClick={() => setLang("en")}>EN</button>
              <button type="button" aria-pressed={lang.value === "zh"} onClick={() => setLang("zh")}>中文</button>
            </div>
          </div>
          <div class="menu-row">
            <span class="muted small">{t("menuLook")}</span>
            <div class="seg" role="group" aria-label={t("menuLook")}>
              {looks.map((l) => (
                <button key={l.v} type="button" aria-pressed={(props.pref === "auto" ? "dark" : props.pref) === l.v} onClick={() => props.onPref(l.v)}>{t(l.key)}</button>
              ))}
            </div>
          </div>
          {/* 第三档 #40:报警声音记在这台浏览器上;打开时响一声试听(顺带在这次点击里解锁出声) */}
          {canHandleAlerts(props.me.role) && (
            <div class="menu-row">
              <span class="muted small">{t("menuAlarmSound")}</span>
              <div class="seg" role="group" aria-label={t("menuAlarmSound")}>
                <button type="button" data-alarm-sound="on" aria-pressed={alarmSound.value}
                  onClick={() => { setAlarmSound(true); testChime(); }}>{t("soundOnShort")}</button>
                <button type="button" data-alarm-sound="off" aria-pressed={!alarmSound.value} onClick={() => setAlarmSound(false)}>{t("soundOffShort")}</button>
              </div>
            </div>
          )}
          {props.onHelp && (
            <button type="button" class="menu-item" role="menuitem" data-menu-help="1" onClick={() => { setOpen(false); props.onHelp!(); }}>{t("helpTitle")}</button>
          )}
          <button type="button" class="menu-item" role="menuitem" onClick={() => { setOpen(false); setPw(true); }}>{t("changePassword")}</button>
          {/* P2-22:第三方声明在对话框里看(原来是开一个原始 txt) */}
          <button type="button" class="menu-item" role="menuitem" onClick={() => {
            setOpen(false);
            setNotices("");
            fetch("/assets/third-party-notices.txt").then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
              .then(setNotices).catch(() => setNotices(null));
          }}>{t("thirdParty")}</button>
          <button type="button" class="menu-item" role="menuitem" onClick={() => props.onSignOut()}><Icon name="logout" />{t("signOut")}</button>
        </div>
      )}
      {notices !== undefined && (
        <Modal label={t("thirdParty")} wide onClose={() => setNotices(undefined)}>
          {notices === null ? <p class="error">{t("noticesFailed")}</p>
            : <pre class="notices" data-notices="1">{notices || "…"}</pre>}
        </Modal>
      )}
      {pw && <OwnPassword onClose={() => setPw(false)} onDone={() => { setPw(false); props.onSignOut(t("pwDoneRelogin")); }} />}
    </div>
  );
}

/** 密码至少几个字符(站点 accounts.MIN_PASSWORD)。 */
const PW_MIN = 10;

function OwnPassword({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [old, setOld] = useState("");
  const [neu, setNeu] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState(false);
  async function save(e: Event) {
    e.preventDefault();
    setErr("");
    // P1-67:规则先写出来、当场查(站点也查);新旧一样不改;改之前确认(改完要重新登录)
    if (neu.length < PW_MIN) return setErr(t("pwRule", { n: PW_MIN }));
    if (neu === old) return setErr(t("pwSame"));
    setAsk(true);
  }
  async function commit() {
    setAsk(false);
    setBusy(true);
    try {
      await api("POST", "/api/me/password", { old, new: neu });
      onDone();
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : String(x));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal label={t("changePassword")} onClose={onClose}>
      <form class="field" onSubmit={save}>
        <label>{t("pwOld")}<input type="password" autoComplete="current-password" value={old} onInput={(e) => setOld((e.target as HTMLInputElement).value)} /></label>
        <label>{t("pwNew")}<input type="password" autoComplete="new-password" value={neu} onInput={(e) => setNeu((e.target as HTMLInputElement).value)} /></label>
        <span class="muted small">{t("pwRule", { n: PW_MIN })}</span>
        {err && <p class="error">{err}</p>}
        {/* 第 3 轮 zh N13:跟别的对话框一样有「取消」 */}
        <div class="row end"><button type="button" class="btn" onClick={onClose}>{t("cancel")}</button><button type="submit" class="btn primary" disabled={busy || !old || !neu}>{t("pwSave")}</button></div>
      </form>
      {ask && <Confirm text={t("pwAsk")} yes={t("pwSave")} onNo={() => setAsk(false)} onYes={() => void commit()} />}
    </Modal>
  );
}

/** 把 ``el`` 滚进离它最近的、能竖着滚的祖先里看得见的地方;只改那一层的 scrollTop,不动焦点起点。 */
export function revealInScroller(el: HTMLElement): void {
  let box = el.parentElement;
  while (box && !(box.scrollHeight > box.clientHeight && /auto|scroll/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
  if (!box) return;
  const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
  if (r.top < b.top) box.scrollTop -= b.top - r.top;
  else if (r.bottom > b.bottom) box.scrollTop += r.bottom - b.bottom;
}

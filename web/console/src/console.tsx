// 值班台外框(W44 第一期;W60 改版):左侧导航 + 顶栏(shell.tsx)+ 站点数据 + 各页 + 共用的对话框。
// 值班五页:总览、实况、地图、报警记录、录像;管理、系统各页按角色给(没权限的不列)。全站深色。
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { ToastAction } from "./alertdetail";
import { api, ApiError, enc } from "./api";
import type { Me } from "./app";
import type { Cam } from "./camera";
import { hms, isStale, siteDown, useNow, useSiteData } from "./data";
import { anyUnsaved, dropUnsaved } from "./unsaved";
import { Confirm } from "./dialogs";
import { lang, t } from "./i18n";
import { Shape } from "./icons";
import { FullCamera, taskNote, type UnitInfo } from "./live";
import { LocPage } from "./advloc";
import { RecordingsPage } from "./recpage";
import { ReportsPage } from "./reportpage";
import { MapPage } from "./mappage";
import { FELL_KINDS, forGuard, isOwnerLike, queue, robotCams, robotState, type Alert, type Mode } from "./model";
import { AlarmLogPage } from "./alarmlog";
import { HelpDialog, WEB_TOUR } from "./guide";
import { ArmingPage } from "./armingpage";
import { ArmWizard, needsWizard, patrolHint, wt } from "./armwizard";
import { AlarmPop } from "./alarmpop";
import { DutyPage } from "./duty";
import { LiveWall } from "./livewall";
import { DrillNote } from "./alerttest";
import { groupTodo, homeTodo, HomePage } from "./homepage";
import { ActivityPage } from "./activitypage";
import { DiagPage } from "./advdiag";
import { SystemPage2 } from "./advsystem";
import { UpgradePage } from "./advupgrade";
import { RobotsPage } from "./robotspage";
import { UsersPage } from "./userspage";
import { AdvMapsPage } from "./advmaps";
import { editTarget, MapEditPage } from "./mapedit";
import { AccessPage } from "./accesspage";
import { LayoutPage } from "./layoutpage";
import { LAYOUT_TABS } from "./layouttabs";
import { isAdminPage, loadThemePref, navLabel, pageAllowed, pinFor, readRoute, roleLabel, saveThemePref, SideNav, TopBar, type Page, type ThemePref } from "./shell";
import { pinScheme, systemIsDark } from "./theme";


type Pending =
  | { kind: "mode"; mode: Mode["mode"] }
  | { kind: "stop" }
  | { kind: "cam"; robot: string; cam: Cam }
  | null;


const CAN_POPOVER = typeof HTMLElement !== "undefined" && "showPopover" in HTMLElement.prototype;
export function Console({ me, onOut }: { me: Me; onOut: (note?: string) => void }) {
  const [data, refresh, conn] = useSiteData();
  const now = useNow();
  // B 阶段外审 I5:拿不到新数据时,旧的照显示但标明过期 —— 不能把旧的「在线、没有报警」当成现在
  const stale = isStale(conn, now);
  useEffect(() => { siteDown.value = stale; }, [stale]);
  const [route, setRoute] = useState(readRoute);
  const [pending, setPending] = useState<Pending>(null);
  const [toast, setToast] = useState("");
  // 第 4 轮 admin N2:提示放到浏览器最上层,开着弹窗时也不被遮罩压暗(每次重新显示,排到弹窗上面)
  const toastRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = toastRef.current as (HTMLDivElement & { showPopover?: () => void; hidePopover?: () => void }) | null;
    if (!el || !CAN_POPOVER) return;
    try {
      if (el.matches(":popover-open")) el.hidePopover?.();
      if (toast) el.showPopover?.();
    } catch { /* 不支持就照旧 */ }
  }, [toast]);
  // 第 2 轮 duty N8:提示上能带一个按钮(比如关掉报警后的「撤销」)
  const [toastAct, setToastAct] = useState<ToastAction | null>(null);
  // W53:第一次登录(这个账号没看过当前版本的网页教程)自动打开;老站点不带 guide 就不弹
  const [help, setHelp] = useState(() => me.guide != null && (me.guide.web_tour ?? 0) < WEB_TOUR);
  void lang.value; // 换语言整页重画

  // 网页易用性第 1 轮 P0-12:有没存的改动,换页前先问;不走就把地址改回来
  const [leave, setLeave] = useState<string | null>(null);
  const shownHash = useRef(location.hash);
  const shownPage = useRef(route.page);
  shownPage.current = route.page;
  useEffect(() => {
    const on = () => {
      const r = readRoute();
      if (anyUnsaved() && r.page !== shownPage.current) {
        const want = location.hash;
        history.replaceState(null, "", shownHash.current || "#/");
        setLeave(want);
        return;
      }
      shownHash.current = location.hash;
      setRoute(r);
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const [pref, setPref] = useState<ThemePref>(loadThemePref);
  useEffect(() => {
    pinScheme(pinFor(route.page, pref, systemIsDark()));
  }, [route.page, pref]);
  useEffect(() => () => pinScheme(null), []);
  const go = (page: Page, robot?: string) => {
    location.hash = `#/${page}${robot ? `?robot=${encodeURIComponent(robot)}` : ""}`;
  };

  // 第 2 轮 duty N2:新提示换掉旧的计时(原来上一条的 6 秒计时会把下一条提前清掉,中间空着);长的多留一会儿
  const toastTimer = useRef(0);
  const say = (s: string, act?: ToastAction) => {
    setToast(s);
    setToastAct(act ?? null);
    window.clearTimeout(toastTimer.current);
    // 带按钮的多留一会儿(要来得及点)
    toastTimer.current = window.setTimeout(() => { setToast(""); setToastAct(null); },
      act ? 20_000 : Math.min(15_000, Math.max(6000, s.length * 90)));
  };
  const act = async (fn: () => Promise<unknown>): Promise<boolean> => {
    try {
      await fn();
      await refresh();
      return true;
    } catch (e) {
      say(t("failed", { why: e instanceof ApiError ? e.message : String(e) }));
      return false;
    }
  };

  const alerts = data?.alerts ?? [];
  const { active } = queue(alerts, now);
  const guardAlarms = active.filter(forGuard).length;
  const p1 = active.filter((a) => a.level === "P1");
  const fell = new Set(alerts.filter((a) => a.resolved_ms == null && FELL_KINDS.has(a.kind)).map((a) => a.robot));
  const units: UnitInfo[] = useMemo(() => {
    const deter = new Map((data?.deter ?? []).map((d) => [d.robot_id, d]));
    const deterUnknown = data != null && data.deter === null;
    const batt = new Map((data?.summary?.robots ?? []).map((r) => [r.robot_id, r.battery_pct]));
    return (data?.robots ?? [])
      .filter((r) => r.active && !r.revoked)
      .map((r) => {
        const kind = r.status?.task?.kind ?? "";
        const state = robotState(r, deter.get(r.robot_id), kind.includes("dock") || kind.includes("charg"), fell.has(r.robot_id));
        return { robot: r, state, battery: stale ? null : batt.get(r.robot_id) ?? null, deter: deter.get(r.robot_id),
          task: stale ? "" : taskNote(r, kind, state), taskShort: stale ? "" : taskNote(r, kind, state, true), stale, deterUnknown };
      });
  }, [data, lang.value, stale]);
  const online = units.filter((u) => u.state !== "offline");

  async function stopAll() {
    setPending(null);
    const res = await Promise.allSettled(online.map((u) => api("POST", `/api/robots/${enc(u.robot.robot_id)}/halt`, {})));
    const bad = online.map((u, i) => [u.robot.robot_id, res[i]] as const).filter(([, r]) => r.status === "rejected");
    say(bad.length
      ? bad.map(([id, r]) => t("stopFailed", { id, why: r.status === "rejected" && r.reason instanceof ApiError ? r.reason.message : "?" })).join(" ")
      : t("stopAllDone", { n: online.length }));
    await refresh();
  }

  const ack = (a: Alert) => act(() => api("POST", `/api/alerts/${enc(a.key)}/ack`, {}));
  const resolve = (a: Alert, verdict: string) => act(() => api("POST", `/api/alerts/${enc(a.key)}/resolve`, { verdict }));
  const firstP1 = p1.find(forGuard);
  // 第 3 轮 config N7:跟「系统状态」页「需要你处理」一栏一样数(原来把 P3 通知也算上,页面上看不到也清不掉)
  const notices = groupTodo(homeTodo(alerts)).length;
  const admin = isOwnerLike(me.role);
  // 布防向导(用户 11-13):管理员点「布防」时,防区 / 防区路线 / 值守方案 / 能派的机器人缺哪样就先开向导
  const [wiz, setWiz] = useState<"open" | "arm" | null>(null);
  // 布防向导外审 2 #1:向导会改布防时间、防区、路线 —— 当前页有没存的草稿先问(不然存草稿会把向导存的盖回去);
  // 向导改过东西,关掉后当前页整页重开(从站点重读)
  const [askWiz, setAskWiz] = useState<"open" | "arm" | null>(null);
  const [pageGen, setPageGen] = useState(0);
  const wizChanged = useRef(false);
  const openWiz = (k: "open" | "arm") => (anyUnsaved() ? setAskWiz(k) : setWiz(k));
  const askMode = (m: Mode["mode"]) => {
    if (m !== "armed" || !admin) return setPending({ kind: "mode", mode: m });
    void needsWizard().then((n) => (n ? openWiz("arm") : setPending({ kind: "mode", mode: m })));
  };

  // 带地图的页整页一屏(地图撑满顶栏以下):地图、防区、巡检路线
  const fill = route.page === "duty" || route.page === "map" || route.page === "admin/layout" || route.page === "admin/mapedit";
  return (
    <div class={fill ? (route.page === "duty" ? "console fill fill-duty" : "console fill") : "console"}>
      {/* P2-01:「跳到内容」是第一个焦点;不改地址(地址是页面路由) */}
      <a class="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>{t("skipToContent")}</a>
      <SideNav me={me} page={route.page} alarms={stale ? null : guardAlarms} notices={admin ? notices : 0} />
      <div class="workspace">
      <TopBar me={me} page={route.page} mode={data?.mode ?? null} alarms={stale ? null : guardAlarms} now={now}
        pref={pref} onPref={(p) => { saveThemePref(p); setPref(p); }}
        onStop={() => setPending({ kind: "stop" })} onSay={say} stale={stale}
        onMode={askMode}
        held={units.filter((u) => u.robot.held != null).length}
        onHelp={() => setHelp(true)}
        onSignOut={async (note?: string) => {
          // 改完密码站点已经让旧会话失效:不再调 logout(会 401),直接回登录页带上说明
          if (note) return onOut(note);
          // P2-22:退出后地址不再停在原来那一页
          try { await api("POST", "/api/logout", {}); } finally { history.replaceState(null, "", location.pathname + location.search); onOut(); }
        }} />
      {help && <HelpDialog role={me.role} page={route.page} onClose={() => setHelp(false)}
        noAccess={pageAllowed(route.page, me.role) ? undefined
          : (["guard", "owner", "admin"] as const).filter((r) => pageAllowed(route.page, r)).map((r) => t(roleLabel(r))).join(" / ")} />}
      {stale && (
        <div class="stalebar" role="alert">
          <Shape kind="P2" />
          {conn.okAt ? t("staleBanner", { t: hms(conn.okAt) }) : t("staleNever")}
        </div>
      )}

      <main class="page" id="main" tabIndex={-1} data-page={route.page}>
        {/* P2-02:值班这几页本身没有大标题,给读屏一个 */}
        {(["duty", "live", "map", "alarms", "recordings"] as Page[]).includes(route.page) && navLabel(route.page) && (
          <h1 class="sr-only">{t(navLabel(route.page)!.page)}</h1>
        )}
        {/* W6-13 / minor #25:演练开着,保安的值班、实时画面、地图页也说一句(以前只有管理员总览、报警记录页) */}
        {(["duty", "live", "map"] as Page[]).includes(route.page) && <DrillNote role={me.role} />}
        {route.page === "duty" && (
          <DutyPage units={units} alerts={alerts} now={now} role={me.role} say={say} refresh={refresh} mode={data?.mode ?? null} stale={stale}
            onZoom={(id) => setPending({ kind: "cam", robot: id, cam: "front" })} />
        )}
        {route.page === "live" && (
          <LiveWall units={units} alerts={alerts} now={now} onZoom={(id) => setPending({ kind: "cam", robot: id, cam: "front" })} />
        )}
        {route.page === "alarms" && <AlarmLogPage now={now} role={me.role} me={me.name} />}
        {/* UIUX-034:无权限页说清楚给谁用,给一个回去的按钮 */}
        {!pageAllowed(route.page, me.role) && (
          <section class="empty noaccess" role="alert">
            <h2>{t("noAccessTitle")}</h2>
            <p>{t("noAccessWho", { who: (["guard", "owner", "admin"] as const).filter((r) => pageAllowed(route.page, r)).map((r) => t(roleLabel(r))).join(" / ") })}</p>
            {pageAllowed("admin/home", me.role)
              ? <a class="btn primary" href="#/admin/home" data-noaccess-home="1">{t("noAccessHome")}</a>
              : <a class="btn primary" href="#/duty" data-noaccess-home="1">{t("noAccessDuty")}</a>}
          </section>
        )}
        {isAdminPage(route.page) && pageAllowed(route.page, me.role) && (
          <div class="adminwrap">
            <div class="adminbody" key={pageGen}>
              {route.page === "admin/home" && (
                <HomePage alerts={alerts} mode={data?.mode ?? null} now={now} onAck={ack} onDone={(a) => resolve(a, "handled")}
                  onMode={askMode} onWizard={admin ? () => openWiz("open") : undefined} />
              )}
              {route.page === "admin/arming" && <ArmingPage say={say} now={now} role={me.role} />}
              {route.page === "admin/users" && pageAllowed(route.page, me.role) && <UsersPage me={me.name} say={say} now={now} />}
              {route.page === "admin/robots" && <RobotsPage key={route.robot ?? ""} say={say} now={now} units={units} readOnly={!admin} role={me.role} robot={route.robot} />}
              {route.page === "admin/system" && <SystemPage2 me={me} now={now} say={say} />}
              {route.page === "admin/diag" && <DiagPage say={say} />}
              {route.page === "admin/activity" && pageAllowed(route.page, me.role) && <ActivityPage now={now} />}
              {route.page === "admin/mapedit" && <MapEditPage say={say} target={editTarget(location.hash)} />}
              {route.page === "admin/upgrade" && <UpgradePage say={say} />}
              {route.page === "admin/layout" && <LayoutPage say={say} robots={units.map((u) => u.robot.robot_id)} tabs={LAYOUT_TABS} />}
              {route.page === "admin/maps" && <AdvMapsPage say={say} />}
              {route.page === "admin/access" && <AccessPage say={say} now={now} />}
              {route.page === "admin/localization" && <LocPage units={units} alerts={alerts} now={now} role={me.role} />}
              {route.page === "admin/reports" && <ReportsPage now={now} />}
            </div>
          </div>
        )}
        {route.page === "recordings" && (
          <RecordingsPage key={`${route.robot ?? ""}@${route.at ?? ""}`} robots={units.map((u) => u.robot.robot_id)} role={me.role} now={now}
            camsOf={(id) => robotCams(units.find((u) => u.robot.robot_id === id)?.robot)}
            robot={route.robot} at={route.at} say={say} />
        )}
        {route.page === "map" && (
          <MapPage units={units} p1={p1} now={now} role={me.role} selected={route.robot ?? firstP1?.robot ?? null}
            onSelect={(id) => go("map", id)}
            onVideo={(id) => go("duty", id)} mode={data?.mode ?? null} say={say} stale={stale}
            onArm={() => askMode("armed")} />
        )}
      </main>
      </div>

      {pending?.kind === "mode" && (
        <Confirm text={t(pending.mode === "armed" ? "modeArmConfirm" : pending.mode === "home" ? "modeHomeConfirm" : "modeVisitorAllConfirm")}
          yes={t(pending.mode === "armed" ? "modeArmed" : pending.mode === "home" ? "modeHome" : "modeVisitorAll")}
          onNo={() => setPending(null)}
          onYes={() => {
            const m = pending.mode; setPending(null);
            void act(() => api("POST", "/api/mode", { mode: m })).then((ok) => {
              // UIUX-039:开不了向导的角色布防后,机器人不会自己巡逻也要说一声(管理员缺东西时上面就进了向导)
              if (ok && m === "armed" && !admin) void patrolHint().then((h) => { if (h) say(h); });
            });
          }} />
      )}
      {wiz && <ArmWizard say={say} arming={wiz === "arm"} onChanged={() => { wizChanged.current = true; }}
        onClose={() => { setWiz(null); if (wizChanged.current) { wizChanged.current = false; setPageGen((g) => g + 1); } }} />}
      {askWiz && <Confirm text={wt("dropPage")} yes={wt("dropYes")} danger onNo={() => setAskWiz(null)}
        onYes={() => { const k = askWiz; setAskWiz(null); dropUnsaved(); setPageGen((g) => g + 1); setWiz(k); }} />}
      {leave != null && (
        <Confirm text={t("leaveUnsaved")} yes={t("leaveUnsavedYes")} danger onNo={() => setLeave(null)}
          onYes={() => { const h = leave; setLeave(null); dropUnsaved(); location.hash = h; }} />
      )}
      {pending?.kind === "stop" && (
        <Confirm text={t("stopAllConfirm", { n: online.length })} yes={t("stopAll")} stop onNo={() => setPending(null)} onYes={stopAll} />
      )}
      {pending?.kind === "cam" && <FullCamera robot={pending.robot} cam={pending.cam} now={now} onClose={() => setPending(null)}
        cams={robotCams(units.find((u) => u.robot.robot_id === pending.robot)?.robot)} />}
      {/* 第三档 #40:新报警弹卡片、出声(值守页有横幅,只出声) */}
      <AlarmPop alerts={active} role={me.role} onDuty={route.page === "duty"} onAck={(a) => void ack(a)}
        onGo={() => { location.hash = "#/duty"; }} />
      <div class="toast" role="status" aria-live="polite" ref={toastRef} {...(CAN_POPOVER ? { popover: "manual" } : {})}>{toast}
        {toast && toastAct && <button type="button" class="btn sm toast-act" data-toast-act="1"
          onClick={() => { const a = toastAct; setToast(""); setToastAct(null); a.run(); }}>{toastAct.label}</button>}</div>
    </div>
  );
}

// 用户页(W44 第二期,设计 §5.1「用户」;只给管理员,工程师不能管账号):一张表 —— 名字、角色(界面名字)、最后登录、
// 状态、改角色 / 停用 / 重设密码 / 删除。「给工程师开临时账号」单独一个按钮:4 或 24 小时,再输一次密码,口令只显示这一次;
// 工程师那一行写还剩多久,只能提前关、删。点一个人看他做过什么(审计)。
import { useCallback, useEffect, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { ConfirmPassword } from "./confirmpw";
import { routeName } from "./bundlepanel";
import { hm, hms, md, nameOf, siteDown } from "./data";
import { Confirm, Modal } from "./dialogs";
import { alertTitle, colon, lang, t } from "./i18n";
import { roleLabel } from "./shell";
import { siteStr, zhPunct } from "./sitetext";

type Say = (s: string) => void;
interface Account { name: string; role: string; disabled: boolean; display_name: string; expires_ms: number | null; last_login_ms: number | null; expired: boolean }
export interface AuditRow { id: number; at: number; actor: string; actor_role?: string | null; action: string; target: string; status: number;
  /** 第 10 轮 W9-01:对象是日程、路线时站点给的显示名(老站点没有)。 */
  target_name?: string;
  detail?: { error?: string; role?: string; disabled?: boolean; password_reset?: boolean; display_name?: string;
    first_day?: string; last_day?: string;
    // 日志设计 第 1、2 条:前后变化、来源、当时在做什么、系统事件的说明
    from?: string | null; to?: string; op?: "add" | "update" | "remove"; name?: string; x?: number; y?: number;
    source?: "web" | "app" | "api" | "system"; doing?: { task?: string | null; kind?: string; state?: string }; why?: string;
    note?: string; verdict?: string; mission?: string; mission_title?: string; robot?: string | null; title?: string; level?: string; kind?: string;
    channel?: string; by?: string; task_id?: string | null; err?: string; err_name?: string; req?: string;
    // minor #18:派单的点数、去一个点的目标、存草稿存成的版本
    points?: number; request?: { target?: unknown }; version?: string } }

/** 第 3 轮 P1-66:改账号写清改了什么(原来只写「改了账号」)。 */
export function changeText(d: AuditRow["detail"], target = ""): string {
  if (!d) return "";
  // W6-07:对象是报警的,标题已经在对象里(按界面语言),这里不再贴站点那句中文
  if (ALERT_KEY.test(target)) d = { ...d, title: undefined };
  const out: string[] = [];
  if (d.role) out.push(t("auditRoleTo", { r: t(roleLabel(d.role)) }));
  if (d.disabled === true) out.push(t("auditDisabled"));
  if (d.disabled === false) out.push(t("auditEnabled"));
  if (d.password_reset) out.push(t("auditPwReset"));
  if (d.display_name) out.push(t("auditRenamed", { n: d.display_name }));
  if (d.first_day) out.push(d.last_day && d.last_day !== d.first_day ? `${d.first_day} – ${d.last_day}` : d.first_day);
  const MODE: Record<string, Parameters<typeof t>[0]> = { armed: "modeArmed", home: "modeHome", stay: "modeHome", visitor: "modeVisitor" };
  const mode = (m: string) => (MODE[m] ? t(MODE[m]) : m);
  if (d.to && d.from !== undefined) out.push(t("auditFromTo", { a: d.from ? mode(d.from) : "—", b: mode(d.to) }));
  if (d.op && d.name) {
    const at = typeof d.x === "number" && typeof d.y === "number" ? ` (${d.x.toFixed(2)}, ${d.y.toFixed(2)})` : "";
    out.push(t(d.op === "remove" ? "auditOpRemove" : d.op === "update" ? "auditOpUpdate" : "auditOpAdd", { n: d.name }) + at);
  }
  if (d.doing) out.push(d.doing.task ? t("auditDoing", { k: d.doing.kind ?? "", task: d.doing.task }) : t("auditIdle"));
  if (d.why) out.push(t("auditWhy", { w: d.why }));
  // minor #18:临时路线写几个点(原来露 temp-… 编号);去一个点写出来;存草稿写存成第几版
  // 第 9 轮 W9-01:路线起了显示名写显示名(站点带 mission_title)
  if (d.mission) out.push(d.mission.startsWith("temp-") && d.points ? t("bpTempRouteN", { n: d.points }) : d.mission_title || routeName(d.mission));
  else if (d.request?.target) {
    // minor #26:去哪写出来(地图坐标,一位小数)
    const g = d.request.target as { x?: unknown; y?: unknown };
    const at = typeof g.x === "number" && typeof g.y === "number"
      ? (lang.value === "zh" ? `（${g.x.toFixed(1)}, ${g.y.toFixed(1)}）` : ` (${g.x.toFixed(1)}, ${g.y.toFixed(1)})`) : "";
    out.push(t("bpGoto") + at);
  }
  if (d.version && /^[^:/\s]+:[^:/\s]+$/.test(target)) out.push(t("auditDraftVer", { v: d.version }));
  if (d.verdict) out.push(t("auditVerdict", { v: d.verdict }));
  if (d.title) out.push(d.title);
  if (d.channel) out.push(t("auditChannel", { c: d.channel }));
  if (d.robot && !d.title) out.push(d.robot);
  if (d.note) out.push(siteStr(d.note));
  return out.join(lang.value === "zh" ? "；" : "; ");
}

// 第 2 轮 admin N12:三处角色下拉框同一个顺序,按权限从小到大
const ROLES = ["viewer", "guard", "owner", "admin"] as const;

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

function day(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** 最后登录:没登录过 / 今天 08:12 / 昨天 / 3 天前。 */
export function lastLoginText(ms: number | null, now: number): string {
  if (ms == null) return t("loginNever");
  if (day(ms) === day(now)) return t("loginToday", { t: hm(ms) });
  const days = Math.max(1, Math.round((new Date(day(now)).getTime() - new Date(day(ms)).getTime()) / 86_400_000));
  return days === 1 ? t("loginYesterday") : t("loginDaysAgo", { n: days });
}

/** 工程师还剩多久。 */
export function leftText(until: number, now: number): string {
  const m = Math.max(0, Math.round((until - now) / 60_000));
  return t("engLeft", { h: Math.floor(m / 60), m: m % 60 });
}

/** 审计里的动作翻成人话;认不得的原样。 */
const ACTIONS: [RegExp, string][] = [
  [/^POST \/api\/arming\/exceptions\/\d+\/remove$/, "actArmExceptionDel"],
  [/^(POST|DELETE) \/api\/arming\/exceptions/, "actArmExceptionAdd"],
  // 第 4 轮 P1-66:巡逻日程真正的接口是 route-schedules;遥控速度
  [/^POST \/api\/route-schedules/, "actPatrolSched"], [/^POST \/api\/teleop-speeds/, "actTeleopSpeeds"],
  [/^POST \/api\/problem-reports\/[^/]+\/delete$/, "actProblemDel"], [/^POST \/api\/problem-reports$/, "actProblemSent"],
  // 第 9 轮 W9-07:遥控开始、结束(站点记的是 teleop_start / teleop_end)
  [/^teleop_start$/, "actTeleopStart"], [/^teleop_end$/, "actTeleopEnd"],
  [/^login/, "actLogin"], [/^POST \/api\/login$/, "actLogin"], [/^POST \/api\/logout/, "actLogout"], [/^POST \/api\/mode$/, "actMode"],
  [/^POST \/api\/alerts\/.+\/resolve$/, "actResolve"], [/^POST \/api\/alerts\/.+\/ack$/, "actAck"], [/^POST \/api\/alerts\/.+\/arrive$/, "actArrive"],
  [/^POST \/api\/robots\/[^/]+\/(goto|patrol)$/, "actDispatch"], [/^POST \/api\/robots\/[^/]+\/halt$/, "actHalt"],
  [/^POST \/api\/accounts\/engineer$/, "actEngineer"], [/^POST \/api\/accounts/, "actAccounts"],
  [/^POST \/api\/lists\/authorizations/, "actAuthz"], [/^POST \/api\/arming\//, "actSchedule"],
  [/^POST \/api\/shift-notes$/, "actNote"], [/^POST \/api\/routes/, "actRoutes"], [/^POST \/api\/(zones|nav-zones|maps)/, "actMaps"],
  // P1-66:常见的再多认几个;认不得的写「其他操作」,原话放悬停里
  [/^POST \/api\/robots\/[^/]+\/home\/return$/, "actReturnHome"], [/^POST \/api\/robots\/[^/]+\/standby\/return$/, "actReturnStandby"], [/^POST \/api\/robots\/[^/]+\/abort$/, "actAbort"],
  [/^POST \/api\/robots\/[^/]+\/resume$/, "actResume"], [/^POST \/api\/robots\/[^/]+\/posture$/, "actPosture"],
  [/^POST \/api\/robots\/[^/]+\/relocalize/, "actLocate"],
  // 第 5 轮 P1-66:「改了机器人」太笼统 —— 换图、建图、待命点、标原点、遥控、驱离、服务模式、看管、设置、升级、Wi-Fi
  [/^POST \/api\/robots\/[^/]+\/map$/, "actRobotMap"], [/^POST \/api\/robots\/[^/]+\/(mapping|map_build)$/, "actRobotMapping"],
  [/^POST \/api\/robots\/[^/]+\/standby$/, "actRobotStandby"], [/^POST \/api\/robots\/[^/]+\/home(\/here)?$/, "actRobotHome"],
  [/^POST \/api\/robots\/[^/]+\/teleop$/, "actRobotTeleop"], [/^POST \/api\/robots\/[^/]+\/deter$/, "actRobotDeter"],
  [/^POST \/api\/robots\/[^/]+\/service$/, "actRobotService"], [/^POST \/api\/robots\/[^/]+\/supervise$/, "actRobotSupervise"],
  [/^POST \/api\/robots\/[^/]+\/(settings|wifi)$/, "actRobotSettings"], [/^POST \/api\/robots\/[^/]+\/release$/, "actRobotRelease"],
  [/^POST \/api\/robots/, "actRobots"],
  // 第 2 轮 P1-66:添加、解绑、重出激活码、改名、批准加入、退回布置、告警演练
  [/^POST \/api\/admin\/robots$/, "actRobotAdd"], [/^POST \/api\/admin\/robots\/[^/]+\/code$/, "actRobotCode"],
  [/^POST \/api\/admin\/robots\/[^/]+\/revoke$/, "actRobotUnbind"], [/^POST \/api\/admin\/robots\/[^/]+\/name$/, "actRobotName"],
  [/^POST \/api\/admin\/bind/, "actBind"], [/^POST \/api\/layout\/history\/\d+\/restore$/, "actRestore"],
  [/^POST \/api\/alert-test/, "actAlertTest"], [/^POST \/api\/admin\/cameras/, "actLayout"],
  [/^POST \/api\/admin\/maps\/[^/]+\/[^/]+\/delete$/, "actMapDelete"], [/^POST \/api\/admin\/maps\/[^/]+\/[^/]+\/edit$/, "actMapDraft"], [/^POST \/api\/admin\/maps/, "actMaps"], [/^POST \/api\/(standby|cameras|layout|guard-routes)/, "actLayout"],
  [/^POST \/api\/(releases|system)/, "actSystem"], [/^POST \/api\/me/, "actMe"],
  // 第 3 轮 P1-66:巡逻日程、值班设置、布防例外、看录像 / 下载
  [/^POST \/api\/schedule/, "actPatrolSched"], [/^POST \/api\/duty-settings/, "actDutySettings"],
  [/^VIEW$/, "actView"], [/^DOWNLOAD$/, "actDownload"],
  // 第 10 轮 W10-04:App 开后台值守(以前「其他操作 · App」)
  [/^POST \/api\/watch\/token$/, "actWatchToken"],
  // 日志设计 第 2 条:系统自己做的事
  [/^schedule started$/, "actSchedStarted"], [/^schedule (skip|alarm)$/, "actSchedMissed"], [/^schedule /, "actSchedBlocked"],
  [/^robot online$/, "actRobotOnline"], [/^robot offline$/, "actRobotOffline"],
  [/^alert raised$/, "actAlertRaised"], [/^alert recorded$/, "actAlertRecorded"],
  [/^alert escalated$/, "actAlertEscalated"], [/^alert auto-resolved$/, "actAlertAutoResolved"],
];
/** 第 2 轮 P1-66:对象里的内部编号不摆出来(悬停看原文):「图:版本/层:哈希」只留图和版本,长哈希去掉。 */
/** 报警的键 ``机器人/种类#序号``(易用性第 6 轮 W6-07)。 */
const ALERT_KEY = /^([^/\s]+)\/([a-z0-9_$]+)#\d+$/;

/** 「报警:标题 · 机器人」—— 标题按种类、跟界面语言(不用站点那句中文)。 */
function alertObj(key: string): string | null {
  const m = ALERT_KEY.exec(key);
  if (!m) return null;
  const site = m[1] === "site" || m[1].includes(":");
  return `${t("auditAlertObj")}${colon()}${alertTitle(lang.value, m[2], m[2])}${site ? "" : ` · ${m[1]}`}`;
}

/** 诊断包:``support-bundle/<引用>/<开始>-<结束>``;引用是 alert:… / run:… / task:… / robot:… / problem:… / range。 */
function bundleObj(target: string): string | null {
  const m = /^support-bundle\/(.*)\/(\d+)-(\d+)$/.exec(target);
  if (!m) return null;
  const [, ref, a, b] = m;
  const since = Number(a), until = Number(b);
  const span = `${md(since)} ${hm(since)}–${md(until) === md(since) ? "" : `${md(until)} `}${hm(until)}`;
  const r = /^(alert|run|task|robot|problem):(.+)$/.exec(ref);
  // 补测 W6-08:一趟巡逻写「机器人 · 路线」(``run:<号>:<机器人>:<任务名>``),跟导出列表一样;老格式只有号
  const run = r && r[1] === "run" ? /^\d+:([^:]+):(.+)$/.exec(r[2]) : null;
  const what = !r ? null : r[1] === "alert" ? alertObj(r[2])
    : run ? `${nameOf(run[1])} · ${routeName(run[2])}` : r[1] === "run" ? t("auditBundleRun", { n: r[2] })
    : r[1] === "task" ? t("auditBundleTask", { n: r[2].replace(/\b[0-9a-f]{12,}\b/gi, "…") })
    : r[1] === "robot" ? t("auditBundleRobot", { n: r[2] }) : t("auditBundleProblem", { n: r[2] });
  return [t("auditBundle"), what, span].filter(Boolean).join(" · ");
}

export function targetText(target: string): string {
  const alert = alertObj(target) ?? bundleObj(target);
  if (alert) return alert;
  // 补测:派临时路线、去看看的那一行对象是 temp-… / task-…,写人话
  if (/^(temp-\d+|task-[0-9a-f]+)$/i.test(target)) return routeName(target);
  // 补测:删地图版本的对象是「图:版本」
  const mv = /^([^:/\s]+):(\d+)$/.exec(target);
  if (mv) return t("auditMapVer", { map: mv[1], v: mv[2] });
  // 第 3 轮 P1-66:布防模式写成人话;例外、录像编号写清是什么
  const MODE: Record<string, Parameters<typeof t>[0]> = { armed: "modeArmed", home: "modeHome", stay: "modeHome", visitor: "modeVisitor", disarmed: "modeDisarmedAll" };
  if (MODE[target]) return t(MODE[target]);
  const ex = /^exception\/(\d+)$/.exec(target);
  if (ex) return t("auditException", { n: ex[1] });
  const rec = /^recording\/(\d+)$/.exec(target);
  if (rec) return t("auditRecording", { n: rec[1] });
  if (/^recording-clip\//.test(target)) return t("auditClip");
  const m = /^(?:[a-z_]+:)?([^:/\s]+):([^/\s]+)\/(?:[a-z_]+:)?[0-9a-f]{8,}$/i.exec(target);
  if (m) return t("auditMapVer", { map: m[1], v: m[2] });
  // 第 4 轮 P1-66:「图:版本/名字」「camera/名字」写成人话
  const mz = /^([^:/\s]+):(\d+)\/(.+)$/.exec(target);
  if (mz) return `${t("auditMapVer", { map: mz[1], v: mz[2] })} · ${mz[3]}`;
  // 第 10 轮 W10-04:看直播的对象「live/B/front」写成「B 前摄像头」
  const live = /^live\/([^/]+)\/(front|back|thermal)$/.exec(target);
  if (live) return t("auditLiveCam", { robot: nameOf(live[1]), cam: t(live[2] as "front" | "back" | "thermal") });
  const cam = /^camera\/(.+)$/.exec(target);
  if (cam) return t("camNamed", { name: cam[1] });
  return target.replace(/\b[0-9a-f]{12,}\b/gi, "…");
}

/** 第 10 轮 W10-04:巡逻开始、结束、临时巡逻这类通知(P3)记的是「alert raised」,不是报警 —— 写机器人事件。 */
const ROBOT_EVENTS = new Set(["run_start", "run_done", "adhoc_patrol", "patrol_started", "patrol_done"]);

/** 一行的动作:多看一眼对象和详情(看直播、机器人事件)。 */
export function rowActionText(r: Pick<AuditRow, "action" | "target" | "detail">): string {
  if (r.action === "VIEW" && /^live\//.test(r.target)) return t("actWatchLive");
  const d = r.detail ?? {};
  if (/^alert (raised|recorded)$/.test(r.action) && (d.level === "P3" || ROBOT_EVENTS.has(d.kind ?? ""))) return t("actRobotEvent");
  return actionText(r.action);
}

export function actionText(a: string): string {
  const hit = ACTIONS.find(([re]) => re.test(a));
  return hit ? t(hit[1] as Parameters<typeof t>[0]) : /^(POST|PUT|DELETE|PATCH) \/api\//.test(a) ? t("actOther") : a;
}

function useAccounts(say: Say): [Account[], () => void, (a: Account[]) => void] {
  const [rows, setRows] = useState<Account[]>([]);
  const load = useCallback(() => {
    api<{ accounts: Account[] }>("GET", "/api/accounts").then((d) => setRows(d.accounts ?? [])).catch((e) => say(errText(e)));
  }, []);
  useEffect(load, [load]);
  return [rows, load, setRows];
}

export function UsersPage({ me, say, now }: { me: string; say: Say; now: number }) {
  const [rows, reload, setRows] = useAccounts(say);
  const [adding, setAdding] = useState(false);
  const [eng, setEng] = useState<"form" | { display: string; hours: number; vpn: boolean } | null>(null);
  const [made, setMade] = useState<{ name: string; password: string; expires_ms: number;
    vpn?: { conf?: string; address?: string; error?: string; warning?: string } } | null>(null);
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Account | null>(null);
  const [who, setWho] = useState<string | null>(null);
  // P1-05 / P1-63:改角色、停用、提前关工程师账号都先确认
  const [ask, setAsk] = useState<{ text: string; yes: string; danger?: boolean; go: () => void } | null>(null);

  const change = async (name: string, body: Record<string, unknown>, msg = t("saved")) => {
    try {
      const d = await api<{ accounts: Account[] }>("POST", `/api/accounts/${enc(name)}`, body);
      if (d.accounts) setRows(d.accounts);
      say(msg);
    } catch (e) {
      say(errText(e));
      reload();
    }
  };

  return (
    <div class="users">
      <div class="panel-head">
        <h1>{t("users")}</h1>
        <button type="button" class="btn push" onClick={() => setEng("form")}>{t("engOpen")}</button>
        <button type="button" class="btn primary" onClick={() => setAdding(true)}>{t("addUser")}</button>
      </div>
      <p class="muted lead">{t("usersLead")}</p>
      <Requests say={say} onDone={reload} />
      {ask && <Confirm text={ask.text} yes={ask.yes} danger={ask.danger} onNo={() => setAsk(null)} onYes={() => { const g = ask.go; setAsk(null); g(); }} />}
      <div class={who ? "users-split" : undefined}>
        <table class="grid users-table">
          <thead><tr><th>{t("name")}</th><th>{t("role")}</th><th>{t("lastLogin")}</th><th>{t("status")}</th><th>{t("colActions")}</th></tr></thead>
          <tbody>
            {rows.length === 0 && siteDown.value && <tr><td colSpan={5} class="warn" data-load-failed="1">{t("loadRetry")}</td></tr>}
            {rows.map((a) => {
              const isEng = a.role === "engineer";
              const self = a.name === me;
              const off = a.disabled || a.expired;
              return (
                <tr key={a.name} data-name={a.name} class={off ? "off" : undefined}>
                  <td>
                    <button type="button" class="linklike user-name" onClick={() => setWho(a.name)}>{a.display_name || a.name}</button>
                    <div class="muted small mono">{a.name}</div>
                  </td>
                  <td data-label={t("role")}>
                    {isEng || self ? t(roleLabel(a.role)) : (
                      <select aria-label={`${t("role")} ${a.name}`} value={a.role} onChange={(e) => {
                        const r = e.currentTarget.value;
                        e.currentTarget.value = a.role;           // 确认了才改
                        setAsk({ text: t(r === "admin" ? "roleAskAdmin" : "roleAsk", { who: a.display_name || a.name, role: t(roleLabel(r)) }),
                          yes: t("roleAskYes"), danger: r === "admin", go: () => void change(a.name, { role: r }, t("roleChanged", { who: a.display_name || a.name, role: t(roleLabel(r)) })) });
                      }}>
                        {ROLES.map((r) => <option key={r} value={r}>{t(roleLabel(r))}</option>)}
                      </select>
                    )}
                  </td>
                  <td data-label={t("lastLogin")}>{lastLoginText(a.last_login_ms, now)}</td>
                  <td data-label={t("status")}>
                    {isEng && !off && a.expires_ms ? leftText(a.expires_ms, now)
                      : a.expired ? t("engExpired") : a.disabled ? t("disabled") : t("active")}
                  </td>
                  <td class="actions">
                    {isEng ? (
                      <>
                        {!off && <button type="button" class="btn sm" onClick={() => setAsk({ text: t("engCloseAsk", { who: a.display_name || a.name }), yes: t("engClose"), danger: true,
                          go: () => void change(a.name, { disabled: true }, t("engClosed")) })}>{t("engClose")}</button>}
                        <button type="button" class="btn sm" onClick={() => setRemoving(a)}>{t("remove")}</button>
                      </>
                    ) : !self && (
                      <>
                        <button type="button" class="btn sm" onClick={() => (a.disabled ? void change(a.name, { disabled: false }, t("userEnabled", { who: a.display_name || a.name }))
                          : setAsk({ text: t("disableAsk", { who: a.display_name || a.name }), yes: t("disable"), danger: true,
                            go: () => void change(a.name, { disabled: true }, t("userDisabled", { who: a.display_name || a.name })) }))}>{a.disabled ? t("enable") : t("disable")}</button>
                        <button type="button" class="btn sm" onClick={() => setResetFor(a.name)}>{t("resetPassword")}</button>
                        <button type="button" class="btn sm" onClick={() => setRemoving(a)}>{t("remove")}</button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {who && <UserAudit name={who} account={rows.find((r) => r.name === who)} onClose={() => setWho(null)} />}
      </div>

      {adding && <AddUser onClose={() => setAdding(false)} say={say} onDone={() => { setAdding(false); say(t("userAddedMsg")); reload(); }} />}
      {eng === "form" && <EngineerForm onClose={() => setEng(null)} onNext={(display, hours, vpn) => setEng({ display, hours, vpn })} />}
      {eng && eng !== "form" && (
        <ConfirmPassword title={t("engOpen")} onClose={() => setEng(null)}
          onConfirm={async (pw) => {
            const d = await api<{ name: string; password: string; expires_ms: number; accounts: Account[];
              vpn?: { conf?: string; address?: string; error?: string; warning?: string } }>(
              "POST", "/api/accounts/engineer", { display_name: eng.display, hours: eng.hours, vpn: eng.vpn, confirm_password: pw });
            setEng(null);
            setMade({ name: d.name, password: d.password, expires_ms: d.expires_ms, vpn: d.vpn });
            if (d.accounts) setRows(d.accounts);
          }} />
      )}
      {made && (
        <Modal label={t("engMade")} onClose={() => setMade(null)}>
          <p class="muted small">{t("engMadeHint", { t: `${day(made.expires_ms)} ${hm(made.expires_ms)}` })}</p>
          <dl class="kv">
            <dt>{t("name")}</dt><dd class="mono">{made.name}</dd>
            <dt>{t("password")}</dt><dd class="mono">{made.password}</dd>
          </dl>
          <p class="warn">{t("engOnce")}</p>
          {made.vpn?.conf && (
            <p class="row">
              <span class="muted small">{t("engVpnConf", { a: made.vpn.address ?? "" })}</span>
              <a class="btn sm" download={`nexwar_${made.name}.conf`}
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(made.vpn.conf)}`}>{t("download")}</a>
            </p>
          )}
          {(made.vpn?.error || made.vpn?.warning) && <p class="warn">{made.vpn.error ?? made.vpn.warning}</p>}
          <div class="row end">
            <button type="button" class="btn" onClick={() => { void navigator.clipboard?.writeText(`${made.name}\n${made.password}`).then(() => say(t("copied"))); }}>{t("copy")}</button>
            <button type="button" class="btn primary" onClick={() => setMade(null)}>{t("close")}</button>
          </div>
        </Modal>
      )}
      {resetFor && (
        <PasswordDialog name={resetFor} onClose={() => setResetFor(null)}
          onSave={(pw) => { const n = resetFor; setResetFor(null); void change(n, { password: pw }, t("passwordReset", { name: n })); }} />
      )}
      {removing && (
        <Confirm text={t("userRemoveConfirm", { name: removing.display_name || removing.name })} yes={t("remove")} danger onNo={() => setRemoving(null)}
          onYes={() => {
            const a = removing;
            setRemoving(null);
            api<{ accounts: Account[] }>("POST", `/api/accounts/${enc(a.name)}/remove`, {})
              .then((d) => { setRows(d.accounts ?? []); if (who === a.name) setWho(null); say(t("userRemovedMsg", { name: a.display_name || a.name })); })
              .catch((e) => say(errText(e)));
          }} />
      )}
    </div>
  );
}

const DISPLAY = /^POST \/api\/admin\/maps\/([^/]+)\/([^/]+)\/display$/;
const EDIT = /^POST \/api\/admin\/maps\/([^/]+)\/[^/]+\/edit$/;

/** minor #18:网页存地图草稿是两次请求(编辑存成新版本、再存显示设置),记成两行「修改地图」。
 * 紧跟在「存成第 N 版」后面(同一个人、一分钟内、正是那一版)的显示设置不单列。``rows`` 新的在前。 */
export function mergeAudit(rows: AuditRow[]): AuditRow[] {
  return rows.filter((r, i) => {
    const m = DISPLAY.exec(r.action);
    const prev = rows[i + 1];
    if (!m || !prev || prev.actor !== r.actor || r.at - prev.at > 60_000) return true;
    const e = EDIT.exec(prev.action);
    return !(e && e[1] === m[1] && prev.detail?.version === m[2] && prev.status < 400);
  });
}

/** 活动记录的一行(用户页「他做过什么」、全站活动日志共用)。``who``:行里写上是谁做的。 */
export function AuditLine({ r, who }: { r: AuditRow; who?: boolean }) {
  return (
    <li class={r.status >= 400 ? "bad" : undefined} data-audit={r.id}
      title={r.status < 400 && r.detail?.err ? [r.detail.err, r.detail.err_name].filter(Boolean).join(" ") : undefined}>
      <time class="mono small">{day(r.at)} {hms(r.at)}</time>
      <div class="audit-body">
      {who && <b class="audit-who">{r.actor.startsWith("site:") ? t("auditSystem") : r.actor.replace(/^login:/, "")}</b>}
      <span title={r.action}>{rowActionText(r)}</span>
      {r.status >= 400 ? <span class="tag bad" data-result="refused">{t("auditRefused")}</span>
        : r.status >= 200 ? <span class="tag ok" data-result="ok">{t("auditOk")}</span> : null}
      {r.target && <span class="muted small" title={r.target}>{r.target_name || targetText(r.target)}</span>}
      {r.actor_role === "engineer" && <span class="tag">{t("roleEngineer")}</span>}
      {r.status >= 400 && r.detail?.err && <span class="tag mono" data-err={r.detail.err} title={r.detail.err_name ?? ""}>{r.detail.err}</span>}
      {r.detail?.source && r.detail.source !== "system" && <span class="tag" data-source={r.detail.source}>{t(r.detail.source === "web" ? "auditViaWeb" : r.detail.source === "api" ? "auditViaApi" : "auditViaApp")}</span>}
      {r.status < 400 && changeText(r.detail, r.target) && <span class="small muted" data-change="1">{changeText(r.detail, r.target)}</span>}
      {r.status >= 400 && r.detail?.error && <span class="small audit-why" data-why="1" title={zhPunct(r.detail.error)}>{siteStr(r.detail.error)}</span>}
      </div>
    </li>
  );
}

function UserAudit({ name, account, onClose }: { name: string; account?: Account; onClose: () => void }) {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  useEffect(() => {
    setRows(null);
    api<{ audit: AuditRow[] }>("GET", `/api/audit?actor=${encodeURIComponent(name)}`).then((d) => setRows(d.audit ?? [])).catch(() => setRows([]));
  }, [name]);
  return (
    <aside class="panel user-audit" aria-label={t("userDid", { name })}>
      <div class="panel-head">
        <h2>{t("userDid", { name: account?.display_name || name })}</h2>
        <button type="button" class="btn sm push" onClick={onClose}>{t("close")}</button>
      </div>
      {rows == null ? <p class="muted">…</p> : rows.length === 0 ? <p class="muted">{t("userDidNone")}</p> : (
        <ul class="plain">
          {mergeAudit(rows.slice(0, 200)).map((r) => <AuditLine key={r.id} r={r} />)}
        </ul>
      )}
    </aside>
  );
}

function EngineerForm({ onClose, onNext }: { onClose: () => void; onNext: (display: string, hours: number, vpn: boolean) => void }) {
  const [display, setDisplay] = useState("");
  const [hours, setHours] = useState(4);
  const [vpn, setVpn] = useState(false);          // P1-65:多数站点没装 VPN,默认不勾
  // 第 2 轮 P1-65:站点说没装 VPN 就灰着、写原因(不用到最后一步才说);老站点不报这一项就照旧能勾
  const [noVpn, setNoVpn] = useState(false);
  useEffect(() => {
    let live = true;
    api<{ vpn?: boolean }>("GET", "/api/system/caps").then((c) => { if (live && c.vpn === false) { setNoVpn(true); setVpn(false); } }).catch(() => {});
    return () => { live = false; };
  }, []);
  return (
    <Modal label={t("engOpen")} onClose={onClose}>
      <form class="form eng-form" onSubmit={(e) => { e.preventDefault(); if (display.trim()) onNext(display.trim(), hours, vpn); }}>
        <p class="muted small">{t("engHint")}</p>
        <label class="field">{t("engWho")}<input name="display" value={display} maxLength={64} required onInput={(e) => setDisplay(e.currentTarget.value)} /></label>
        <fieldset class="checks row-wrap">
          <legend>{t("engFor")}</legend>
          {[4, 24].map((h) => (
            <label key={h}><input type="radio" name="hours" value={String(h)} checked={hours === h} onChange={() => setHours(h)} /> {t("accHours", { n: h })}</label>
          ))}
        </fieldset>
        <label class="check"><input type="checkbox" name="vpn" checked={vpn} disabled={noVpn} onChange={(e) => setVpn(e.currentTarget.checked)} /> {t("engVpn")}</label>
        <p class="muted small" data-novpn={noVpn ? "1" : undefined}>{t(noVpn ? "engNoVpn" : "engVpnHint")}</p>
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={!display.trim()}>{t("engNext")}</button>
        </div>
      </form>
    </Modal>
  );
}

function AddUser({ onClose, onDone }: { onClose: () => void; onDone: () => void; say?: Say }) {
  const [name, setName] = useState("");
  const [display, setDisplay] = useState("");
  const [role, setRole] = useState("guard");
  const [pw, setPw] = useState("");
  // 第 4 轮 admin N2:错误写在框里(toast 在弹窗遮罩下面看不清)
  const [err, setErr] = useState("");
  async function submit(e: Event) {
    e.preventDefault();
    try {
      await api("POST", "/api/accounts", { name, display_name: display, role, password: pw });
      onDone();
    } catch (x) {
      setErr(errText(x));
    }
  }
  return (
    <Modal label={t("addUser")} onClose={onClose}>
      <form class="form" onSubmit={submit}>
        <label class="field">{t("displayName")}<input value={display} maxLength={64} onInput={(e) => setDisplay(e.currentTarget.value)} /></label>
        <label class="field">{t("accountName")}<input value={name} pattern="[A-Za-z0-9._\-]{1,64}" required autocomplete="off" onInput={(e) => { setName(e.currentTarget.value); setErr(""); }} /></label>
        <label class="field">{t("role")}
          <select value={role} onChange={(e) => setRole(e.currentTarget.value)}>
            {ROLES.map((r) => <option key={r} value={r}>{t(roleLabel(r))}</option>)}
          </select>
        </label>
        <label class="field">{t("newPassword")}<input type="password" minLength={10} required autocomplete="new-password" value={pw} onInput={(e) => setPw(e.currentTarget.value)} /></label>
        {err && <p class="error small" role="alert" data-form-error="1">{err}</p>}
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary">{t("addUser")}</button>
        </div>
      </form>
    </Modal>
  );
}

function PasswordDialog({ name, onClose, onSave }: { name: string; onClose: () => void; onSave: (pw: string) => void }) {
  const [pw, setPw] = useState("");
  return (
    <Modal label={`${t("resetPassword")}: ${name}`} onClose={onClose}>
      <form class="form" onSubmit={(e) => { e.preventDefault(); onSave(pw); }}>
        <label class="field">{t("newPassword")}<input type="password" minLength={10} required autocomplete="new-password" value={pw} onInput={(e) => setPw(e.currentTarget.value)} /></label>
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary">{t("save")}</button>
        </div>
      </form>
    </Modal>
  );
}

/** W52:App 上申请的账号,等管理员批准(选权限,默认只看;批准再输一次密码)。没有就不占地方。 */
interface AccountRequest { id: string; name: string; display: string; created_ms: number }

export function Requests({ say, onDone }: { say: Say; onDone: () => void }) {
  const [rows, setRows] = useState<AccountRequest[]>([]);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [approving, setApproving] = useState<AccountRequest | null>(null);
  const load = useCallback(() => {
    api<{ requests: AccountRequest[] }>("GET", "/api/account-requests").then((d) => setRows(d.requests ?? [])).catch(() => setRows([]));
  }, []);
  useEffect(load, [load]);
  if (rows.length === 0) return null;
  const roleOf = (r: AccountRequest) => roles[r.id] ?? "viewer";
  return (
    <section class="panel requests" aria-label={t("reqTitle")}>
      <h2>{t("reqTitle")}</h2>
      <table class="grid users-table">
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} data-req={r.id}>
              <td><b>{r.display}</b><div class="muted small mono">{r.name}</div></td>
              <td class="muted small">{hm(r.created_ms)}</td>
              <td>
                <select aria-label={`${t("role")} ${r.name}`} value={roleOf(r)} onChange={(e) => setRoles({ ...roles, [r.id]: e.currentTarget.value })}>
                  {ROLES.map((x) => <option key={x} value={x}>{t(roleLabel(x))}</option>)}
                </select>
              </td>
              <td class="actions">
                <button type="button" class="btn sm" onClick={async () => {
                  try { await api("POST", `/api/account-requests/${enc(r.id)}/reject`, {}); say(t("reqRejected", { name: r.name })); }
                  catch (e) { say(errText(e)); }
                  load();
                }}>{t("reqReject")}</button>
                <button type="button" class="btn sm primary" onClick={() => setApproving(r)}>{t("reqApprove")}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {approving && (
        <ConfirmPassword title={t("reqApproveTitle", { name: approving.display, role: t(roleLabel(roleOf(approving))) })}
          onClose={() => setApproving(null)}
          onConfirm={async (pw) => {
            await api("POST", `/api/account-requests/${enc(approving.id)}/approve`, { role: roleOf(approving), confirm_password: pw });
            say(t("reqApproved", { name: approving.name }));
            setApproving(null);
            load();
            onDone();
          }} />
      )}
    </section>
  );
}

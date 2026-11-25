// 高级 → 软件升级(W44 第四期,设计 §5.3「软件升级」):现在的版本(站点、每台机器人);上传公司给的升级包(再输一次密码,
// 站点照旧核签名和指纹);在线下载等站点联网(W45)。每台机器人:下载到机器人、换成这一版(现在 / 等它在充电、空闲时)、
// 退回上一版。谁还在用老 App 也在这一页。
import { pkgProblem } from "./pkgcheck";
import { useEffect, useState } from "preact/hooks";
import { useLoad, clientTooOld, groupClients, type ClientRow } from "./admin";
import { api, apiUpload, ApiError, badPackage, enc } from "./api";
import { siteStr } from "./sitetext";
import { ConfirmPassword } from "./confirmpw";
import { Confirm } from "./dialogs";
import { hm, nameOf } from "./data";
import { t } from "./i18n";
import { AppPackages, platformName, SiteUpdate } from "./remoteops";
export { platformName };

type Say = (s: string) => void;
interface Release { name: string; size?: number; note?: string; added_ms?: number; build?: number | null }
interface LastCmd { kind: string; name?: string | null; at_ms: number; result?: string | null; reason?: string | null }
interface LastEv { kind: string; name?: string | null; reason?: string | null; at_ms: number }
/** 真机 11-25:机器人装到哪一步(站点 _release_last 的 progress)。 */
interface Progress { name?: string | null; stage: string; pct: number | null; at_ms: number }
interface Queued { robot_id: string; name: string; last_reason?: string; retry_at_ms?: number | null }
interface Releases {
  releases: Release[];
  robots: Record<string, string | null>;
  rollback?: Record<string, boolean>;
  builds?: Record<string, number | null>;
  last?: Record<string, { cmd: LastCmd | null; event: LastEv | null; progress?: Progress | null }>;
  queue?: Queued[];
}
/** 排队的门槛(站点 release_queue.MIN_BATTERY)。 */
const QUEUE_PCT = 80;
interface Versions { site: { version: string; min_app_level?: number; release_name?: string | null; release_build?: number | null }; robots: { robot_id: string; verdict: string }[]; clients?: ClientRow[] }

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

// 真机 11-20 用户「点下发和切换的时候没有状态显示，不知道是否下发成功，或者切换成功」:
// 每台写最近一条命令(机器人收下没有、拒了为什么)和最近一条升级事件(下载好了、切换中、现在跑哪一版)。
function cmdText(c: LastCmd): string {
  const what = c.kind === "release_install" ? t("upCmdInstall", { name: c.name ?? "" })
    : c.kind === "release_activate" ? t("upCmdActivate", { name: c.name ?? "" }) : t("upCmdRollback");
  const at = hm(c.at_ms);
  const res = c.result === "accepted" || c.result === "duplicate" ? t("upAccepted", { at })
    : c.result ? t("upRejected", { at, why: siteStr(c.reason || c.result) }) : t("upPending", { at });
  return `${what}: ${res}`;
}

const EVENT_TEXT: Record<string, Parameters<typeof t>[0]> = {
  release_installed: "upEvInstalled", release_install_failed: "upEvInstallFailed",
  release_activating: "upEvActivating", release_committed: "upEvCommitted",
  release_activate_failed: "upEvActivateFailed", release_rolling_back: "upEvRollingBack",
  release_rolled_back: "upEvRolledBack", release_rollback_failed: "upEvRollbackFailed",
};

function evText(e: LastEv): string | null {
  const key = EVENT_TEXT[e.kind];
  return key ? t(key, { name: e.name ?? "", at: hm(e.at_ms), why: siteStr(e.reason || "") }) : null;
}

const evBad = (k: string) => k.endsWith("_failed");

/** 「build 35」;老包没写构建号就不写。 */
export function buildTag(n: number | null | undefined): string {
  return n ? t("upBuild", { n }) : "";
}

const STAGE_KEY: Record<string, Parameters<typeof t>[0]> = {
  download: "upStDownload", unpack: "upStUnpack", verify: "upStVerify", stage: "upStStage",
  venv: "upStVenv", sidecar: "upStSidecar", superlio: "upStSuperlio",
};

function Bar({ pct, label, kind }: { pct: number; label: string; kind: string }) {
  return (
    <div class="up-prog" data-up-progress={kind}>
      <div class="up-prog-h small"><span>{label}</span><b class="mono">{pct}%</b></div>
      <div class="up-prog-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label}>
        <div class="up-prog-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** 真机 11-25 用户「下载给机器人的时候需要有进度条，升级也是」。下载(装):机器人报的哪一步、百分比。
 *  切换:三步 —— 机器人收下、正在重启到新版、新版跑起来了(切的时候代理要重启,中间报不了更细的)。 */
function UpProgress({ last }: { last: { cmd: LastCmd | null; event: LastEv | null; progress?: Progress | null } }) {
  const p = last.progress;
  if (p && p.pct != null) {
    const step = STAGE_KEY[p.stage] ? t(STAGE_KEY[p.stage]) : p.stage;
    return <Bar kind="install" pct={p.pct} label={t("upProgInstall", { name: p.name ?? "", step })} />;
  }
  const c = last.cmd, e = last.event;
  if (!c || c.kind !== "release_activate" || (c.result !== "accepted" && c.result !== "duplicate")) return null;
  if (e && e.at_ms >= c.at_ms && (e.kind === "release_committed" || evBad(e.kind) || e.kind === "release_rolled_back")) return null;
  const restarting = !!e && e.at_ms >= c.at_ms && e.kind === "release_activating";
  return <Bar kind="activate" pct={restarting ? 66 : 33}
    label={restarting ? t("upProgRestart", { name: c.name ?? "" }) : t("upProgAccepted", { name: c.name ?? "" })} />;
}

function RobotUpStatus({ rid, rel, onUnqueue }: { rid: string; rel: Releases | null; onUnqueue: () => void }) {
  const last = rel?.last?.[rid];
  const q = (rel?.queue ?? []).find((x) => x.robot_id === rid);
  const ev = last?.event ? evText(last.event) : null;
  if (!last?.cmd && !ev && !q && !last?.progress) return null;
  const refused = !!last?.cmd?.result && last.cmd.result !== "accepted" && last.cmd.result !== "duplicate";
  return (
    <div class="up-status small" data-up-status={rid} role="status">
      {last && <UpProgress last={last} />}
      {last?.cmd && <p class={refused ? "error" : undefined} data-up-cmd={last.cmd.result ?? "pending"}><span class="muted">{t("upLast")}: </span>{cmdText(last.cmd)}</p>}
      {ev && <p class={evBad(last!.event!.kind) ? "error" : undefined} data-up-event={last!.event!.kind}>{ev}</p>}
      {q && (
        <div class="row wrap" data-up-queue={q.name}>
          <span class="tag">{t("upInQueue", { name: q.name, pct: QUEUE_PCT })}</span>
          {q.last_reason && <span class="error">{t("upQueueRefused", { why: siteStr(q.last_reason), at: q.retry_at_ms ? hm(q.retry_at_ms) : "—" })}</span>}
          <button type="button" class="btn sm" onClick={onUnqueue}>{t("upUnqueue")}</button>
        </div>
      )}
    </div>
  );
}

export function UpgradePage({ say }: { say: Say }) {
  const [rel, reload] = useLoad<Releases>("/api/releases");
  // 命令发出去以后机器人几秒到几十秒才回事件、切完重连:页面开着就每 5 秒刷一次
  useEffect(() => { const h = setInterval(reload, 5000); return () => clearInterval(h); }, [reload]);
  const [versions] = useLoad<Versions>("/api/versions");
  const [file, setFile] = useState<File | null>(null);
  const [bad, setBad] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [upPct, setUpPct] = useState<number | null>(null);
  const [backing, setBacking] = useState<string | null>(null);

  const act = async (robot: string, body: Record<string, unknown>, msg: string) => {
    try {
      const got = await api<{ ack?: { result?: string; reason?: string } }>("POST", `/api/robots/${enc(robot)}/release`, body);
      // 原来只要 HTTP 200 就说「正在切换」,机器人拒了(回执 rejected)也一样
      const r = got?.ack?.result;
      if (r && r !== "accepted" && r !== "duplicate") say(t(r === "rejected" ? "upRefused" : "upNoReply", { id: nameOf(robot), why: siteStr(got?.ack?.reason || r) }));
      else say(msg);
      reload();
    } catch (e) {
      say(errText(e));
    }
  };

  return (
    <section class="advupgrade">
      <h1>{t("tabUpgrade")}</h1>
      <p class="muted lead">{t("upWhen")}</p>
      <section class="panel">
        <h2>{t("upNow")}</h2>
        {/* 真机 11-25:「站点上的版本」被当成站点自己的版本 —— 站点(这台电脑)自己是哪一版单独一行 */}
        <div class="sys-row" data-site-version="1"><span class="muted">{t("upSite")}</span>
          <b class="mono">{[versions?.site.version ?? "—", buildTag(versions?.site.release_build), versions?.site.release_name].filter(Boolean).join(" · ")}</b></div>
        {Object.entries(rel?.robots ?? {}).map(([rid, cur]) => (
          <div key={rid} class="sys-row" data-robot={rid}>
            {/* 第 2 轮 P1-78:没报版本时写为什么,不只是「—」 */}
            <span class="muted">{nameOf(rid)}</span>{cur ? <b class="mono">{[cur, buildTag(rel?.builds?.[rid])].filter(Boolean).join(" · ")}</b> : <span class="small muted" data-no-release="1">{t("upNoRelease")}</span>}
            {/* P1-78:先确认;站点说这台不能退(老代理)就不给按钮 */}
            {/* 第 3 轮 config N11:没报版本的不再接着说「软件太老、不能退回」 */}
            {!cur ? null : rel?.rollback?.[rid] !== false
              ? <button type="button" class="btn sm push" onClick={() => setBacking(rid)}>{t("upRollback")}</button>
              : <span class="muted small push">{t("upNoRollback")}</span>}
            <RobotUpStatus rid={rid} rel={rel} onUnqueue={() => void act(rid, { action: "unqueue" }, t("upUnqueued", { id: nameOf(rid) }))} />
          </div>
        ))}
      </section>
      {backing && (
        <Confirm text={t("upRollbackAsk", { id: nameOf(backing) })} yes={t("upRollback")} danger
          onNo={() => setBacking(null)}
          onYes={() => { const rid = backing; setBacking(null); void act(rid, { action: "rollback" }, t("upRolledBack", { id: nameOf(rid) })); }} />
      )}
      <SiteUpdate say={say} />
      <AppPackages say={say} />
      <section class="panel up-get">
        <h2>{t("upGet")}</h2>
        <div class="row wrap">
          <input type="file" name="pkg" accept=".tar.gz,.tgz,application/gzip"
            onChange={(e) => { const f = e.currentTarget.files?.[0] ?? null; setFile(f); setBad(null); if (f) void pkgProblem(f).then(setBad); }} />
          <button type="button" class="btn primary" disabled={!file || busy || !!bad} onClick={() => setAsking(true)}>{t("upUpload")}</button>
          {bad && <p class="error small" role="alert">{bad}</p>}
        </div>
        <p class="muted small">{t("upUploadHint")}</p>
        <div class="row"><button type="button" class="btn" disabled>{t("upOnline")}</button><span class="muted small">{t("upOnlineLater")}</span></div>
      </section>
      <section class="panel">
        <h2>{t("upPackages")}</h2>
        <p class="muted small">{t("upPackagesHint")}</p>
        {(rel?.releases ?? []).length === 0 && <p class="muted small">{t("upNone")}</p>}
        <ul class="plain">
          {(rel?.releases ?? []).map((r) => (
            <li key={r.name} class="up-rel" data-release={r.name}>
              <b class="mono">{r.name}</b>{r.build ? <span class="small"> · {buildTag(r.build)}</span> : null}{r.note && <span class="muted small"> · {r.note}</span>}
              <div class="row wrap">
                {Object.keys(rel?.robots ?? {}).map((rid) => (
                  <span key={rid} class="up-robot">
                    <span class="small">{nameOf(rid)}:</span>
                    <button type="button" class="btn sm" onClick={() => void act(rid, { action: "install", name: r.name }, t("upInstalling", { id: nameOf(rid) }))}>{t("upInstall")}</button>
                    <button type="button" class="btn sm" onClick={() => void act(rid, { action: "activate", name: r.name }, t("upSwitching", { id: nameOf(rid) }))}>{t("upSwitchNow")}</button>
                    <button type="button" class="btn sm" onClick={() => void act(rid, { action: "activate", name: r.name, when: "charging" }, t("upQueued", { id: nameOf(rid) }))}>{t("upSwitchCharging")}</button>
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section class="panel">
        <h2>{t("clients")}</h2>
        <p class="muted small">{t("clientsHint")}</p>
        <ul class="plain">
          {(versions?.clients ?? []).length === 0 && <li class="muted small">{t("clientsNone")}</li>}
          {groupClients(versions?.clients ?? []).map((c, i) => (
            <li key={i} data-client={c.name}>
              <b>{c.name}</b> {c.kind === "web" ? t("clientWeb") : `${t("clientApp")} ${c.version ?? "?"}`}
              {c.platform && <span class="muted small"> · {platformName(c.platform)}</span>}
              {c.n > 1 && <span class="muted small" data-client-n={c.n}> · {t("clientLogins", { n: c.n })}</span>}
              {clientTooOld(c, versions?.site.min_app_level) && <span class="tag">{t("clientOld")}</span>}
              <span class="muted small mono"> {hm(c.last_used)}</span>
            </li>
          ))}
        </ul>
      </section>
      {asking && file && (
        <ConfirmPassword title={t("upUpload")} onClose={() => setAsking(false)} onConfirm={async (pw) => {
          setBusy(true);
          setUpPct(0);
          try {
            const d = await apiUpload<{ release: Release }>("/api/releases/upload", file, { "X-Nexwar-Confirm": pw },
              (f) => setUpPct(Math.min(100, Math.round(f * 100))));
            setAsking(false);
            say(t("upUploaded", { name: d.release?.name ?? "" }));
            reload();
          } catch (e) {
            // 第 3 轮 P1-77:包不对(签名、指纹、已登记)不是密码问题 —— 关掉密码框、单独说,不清空密码重来
            // 易用性 build 36 P2-3:原因留在按钮下面(红字),到重新选文件才清掉 —— 以前只闪一下提示条
            if (badPackage(e)) { const why = t("upBadPkg", { why: siteStr((e as ApiError).message) }); setAsking(false); setBad(why); say(why); return; }
            throw e;
          } finally {
            setBusy(false);
            setUpPct(null);
          }
        }}>
          {/* 易用性 build 36:传包有进度;传完了站点还要验签、登记,写「正在检查」 */}
          {upPct != null && <Bar kind="upload" pct={upPct}
            label={upPct >= 100 ? t("upProgChecking", { name: file.name }) : t("upProgUpload", { name: file.name })} />}
        </ConfirmPassword>
      )}
    </section>
  );
}


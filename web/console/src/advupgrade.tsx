// 高级 → 软件升级(W44 第四期,设计 §5.3「软件升级」):现在的版本(站点、每台机器人);上传公司给的升级包(再输一次密码,
// 站点照旧核签名和指纹);在线下载等站点联网(W45)。每台机器人:下载到机器人、换成这一版(现在 / 等它在充电、空闲时)、
// 退回上一版。谁还在用老 App 也在这一页。
import { pkgProblem } from "./pkgcheck";
import { useState } from "preact/hooks";
import { useLoad, clientTooOld, groupClients, type ClientRow } from "./admin";
import { api, apiUpload, ApiError, badPackage, enc } from "./api";
import { siteStr } from "./sitetext";
import { ConfirmPassword } from "./confirmpw";
import { Confirm } from "./dialogs";
import { hm, nameOf } from "./data";
import { t } from "./i18n";
import { AppPackages, SiteUpdate } from "./remoteops";

type Say = (s: string) => void;
interface Release { name: string; size?: number; note?: string; added_ms?: number }
interface Versions { site: { version: string; min_app_level?: number }; robots: { robot_id: string; verdict: string }[]; clients?: ClientRow[] }

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

export function UpgradePage({ say }: { say: Say }) {
  const [rel, reload] = useLoad<{ releases: Release[]; robots: Record<string, string | null>; rollback?: Record<string, boolean> }>("/api/releases");
  const [versions] = useLoad<Versions>("/api/versions");
  const [file, setFile] = useState<File | null>(null);
  const [bad, setBad] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [backing, setBacking] = useState<string | null>(null);

  const act = async (robot: string, body: Record<string, unknown>, msg: string) => {
    try {
      await api("POST", `/api/robots/${enc(robot)}/release`, body);
      say(msg);
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
        <div class="sys-row"><span class="muted">{t("upSite")}</span><b class="mono">{versions?.site.version ?? "—"}</b></div>
        {Object.entries(rel?.robots ?? {}).map(([rid, cur]) => (
          <div key={rid} class="sys-row" data-robot={rid}>
            {/* 第 2 轮 P1-78:没报版本时写为什么,不只是「—」 */}
            <span class="muted">{nameOf(rid)}</span>{cur ? <b class="mono">{cur}</b> : <span class="small muted" data-no-release="1">{t("upNoRelease")}</span>}
            {/* P1-78:先确认;站点说这台不能退(老代理)就不给按钮 */}
            {/* 第 3 轮 config N11:没报版本的不再接着说「软件太老、不能退回」 */}
            {!cur ? null : rel?.rollback?.[rid] !== false
              ? <button type="button" class="btn sm push" onClick={() => setBacking(rid)}>{t("upRollback")}</button>
              : <span class="muted small push">{t("upNoRollback")}</span>}
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
        {(rel?.releases ?? []).length === 0 && <p class="muted small">{t("upNone")}</p>}
        <ul class="plain">
          {(rel?.releases ?? []).map((r) => (
            <li key={r.name} class="up-rel" data-release={r.name}>
              <b class="mono">{r.name}</b>{r.note && <span class="muted small"> · {r.note}</span>}
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
          try {
            const d = await apiUpload<{ release: Release }>("/api/releases/upload", file, { "X-Nexwar-Confirm": pw });
            setAsking(false);
            say(t("upUploaded", { name: d.release?.name ?? "" }));
            reload();
          } catch (e) {
            // 第 3 轮 P1-77:包不对(签名、指纹、已登记)不是密码问题 —— 关掉密码框、单独说,不清空密码重来
            if (badPackage(e)) { setAsking(false); say(t("upBadPkg", { why: siteStr((e as ApiError).message) })); return; }
            throw e;
          } finally {
            setBusy(false);
          }
        }} />
      )}
    </section>
  );
}

/** 第 2 轮 config N10:平台名写成人认得的(Android、iOS),不是小写原样。 */
export function platformName(p: string): string {
  const k = p.toLowerCase();
  return k === "android" ? "Android" : k === "ios" ? "iOS" : k === "web" ? "Web" : k === "windows" ? "Windows"
    : k === "macos" ? "macOS" : k === "linux" ? "Linux" : p;
}

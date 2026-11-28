// 1.1-2 告警外发(设计 docs/1.1-2-告警外发-设计.md):「系统」页里的「告警渠道」—— 管理员把告警推到 WhatsApp /
// Telegram / 邮件 / webhook。令牌、口令只进不出(改的时候空着 = 不变)。读不到(没管理权限、老站点)整块不显示。
import { useEffect, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { hm } from "./data";
import { Confirm } from "./dialogs";
import { t, type Key } from "./i18n";

type Say = (s: string) => void;
export type NotifyKind = "telegram" | "whatsapp" | "email" | "webhook";
export interface Channel {
  id: number; kind: NotifyKind; name: string; targets: string[]; levels: string[]; lang: string;
  enabled: boolean; config: Record<string, string | number>; has_secret: boolean;
  last_ok_ms: number | null; last_error: string;
}
interface Sent { id: number; alert_key: string; tier: number; channel: string | null; created_ms: number; sent_ms: number | null; dropped: string; error: string }
interface View { channels: Channel[]; recent: Sent[]; sealed: boolean; hourly_cap: number }

const KINDS: NotifyKind[] = ["whatsapp", "telegram", "email", "webhook"];
const KIND_KEY: Record<NotifyKind, Key> = { telegram: "ntTelegram", whatsapp: "ntWhatsapp", email: "ntEmail", webhook: "ntWebhook" };
const TARGET_HINT: Record<NotifyKind, Key> = { telegram: "ntTargetsTg", whatsapp: "ntTargetsWa", email: "ntTargetsEmail", webhook: "ntTargetsHook" };
const SECRET_KEY: Record<NotifyKind, Key> = { telegram: "ntSecretTg", whatsapp: "ntSecretWa", email: "ntSecretEmail", webhook: "ntSecretHook" };

function errText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export function NotifyPanel({ say }: { say: Say }) {
  const [v, setV] = useState<View | null>(null);
  const [edit, setEdit] = useState<Channel | "new" | null>(null);
  const [removing, setRemoving] = useState<Channel | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api<View>("GET", "/api/notify").then(setV).catch(() => setV(null));
  useEffect(() => { void load(); }, []);
  if (v === null) return null;
  async function test(c: Channel) {
    setBusy(true);
    try {
      const r = await api<{ ok: boolean; error: string }>("POST", `/api/notify/${c.id}/test`, {});
      say(r.ok ? t("ntTestOk", { name: c.name }) : t("ntTestBad", { name: c.name, why: r.error }));
      void load();
    } catch (e) { say(errText(e)); } finally { setBusy(false); }
  }
  async function remove(c: Channel) {
    try {
      setV(await api<View>("POST", `/api/notify/${c.id}/remove`, {}));
      say(t("ntDeleted", { name: c.name }));
    } catch (e) { say(errText(e)); }
  }
  return (
    <section class="panel sys-notify" data-notify>
      <h2>{t("ntTitle")}</h2>
      <p class="muted small">{t("ntHint", { n: v.hourly_cap })}</p>
      {!v.sealed && <p class="muted small" data-why="sealed">{t("ntNoKey")}</p>}
      <table class="sp-table">
        <thead><tr><th>{t("ntColName")}</th><th>{t("ntColKind")}</th><th>{t("ntColTo")}</th><th>{t("ntColLevels")}</th><th>{t("ntColState")}</th><th /></tr></thead>
        <tbody>
          {v.channels.length === 0 && <tr><td colSpan={6} class="muted">{t("ntNone")}</td></tr>}
          {v.channels.map((c) => (
            <tr key={c.id} data-channel={c.name}>
              <td><b>{c.name}</b></td>
              <td>{t(KIND_KEY[c.kind])}</td>
              <td class="mono small">{c.targets.join(", ")}</td>
              <td class="mono">{c.levels.join(" ")}</td>
              <td class={c.last_error ? "bad small" : "small"}>
                {!c.enabled ? t("ntOff") : c.last_error ? t("ntLastErr", { why: c.last_error })
                  : c.last_ok_ms ? t("ntLastOk", { t: hm(c.last_ok_ms) }) : t("ntNever")}
              </td>
              <td class="row-wrap">
                <button type="button" class="btn" disabled={busy || !c.enabled} onClick={() => void test(c)}>{t("ntTest")}</button>
                <button type="button" class="btn" onClick={() => setEdit(c)}>{t("ntEdit")}</button>
                <button type="button" class="btn" onClick={() => setRemoving(c)}>{t("ntDelete")}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {edit === null && <button type="button" class="btn primary" onClick={() => setEdit("new")}>{t("ntAdd")}</button>}
      {edit !== null && (
        <ChannelForm key={edit === "new" ? "new" : edit.id} ch={edit === "new" ? null : edit} say={say}
          onDone={(name) => { setEdit(null); say(t("ntSaved", { name })); void load(); }} onCancel={() => setEdit(null)} />
      )}
      {v.recent.length > 0 && (
        <>
          <h3>{t("ntRecent")}</h3>
          <table class="sp-table" data-notify-recent>
            <thead><tr><th>{t("ntColWhen")}</th><th>{t("ntColName")}</th><th>{t("ntColAlert")}</th><th>{t("ntColState")}</th></tr></thead>
            <tbody>
              {v.recent.map((r) => (
                <tr key={r.id}>
                  <td class="mono">{hm(r.created_ms)}</td>
                  <td>{r.channel ?? "—"}</td>
                  <td class="mono small">{r.alert_key}{r.tier > 0 ? ` · ${t("ntAgain")}` : ""}</td>
                  <td class={r.error && !r.sent_ms ? "bad small" : "small"}>
                    {r.sent_ms ? t("ntSentAt", { t: hm(r.sent_ms) }) : r.dropped ? t("ntDropped", { why: r.dropped })
                      : r.error ? t("ntRetrying", { why: r.error }) : t("ntWaiting")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {removing && (
        <Confirm text={t("ntDeleteAsk", { name: removing.name })} yes={t("ntDelete")} danger
          onNo={() => setRemoving(null)} onYes={() => { const c = removing; setRemoving(null); void remove(c); }} />
      )}
    </section>
  );
}

function ChannelForm({ ch, say, onDone, onCancel }: { ch: Channel | null; say: Say; onDone: (name: string) => void; onCancel: () => void }) {
  const [kind, setKind] = useState<NotifyKind>(ch?.kind ?? "whatsapp");
  const [name, setName] = useState(ch?.name ?? "");
  const [targets, setTargets] = useState((ch?.targets ?? []).join(", "));
  const [levels, setLevels] = useState<string[]>(ch?.levels ?? ["P1"]);
  const [lang, setLang] = useState(ch?.lang ?? "en");
  const [enabled, setEnabled] = useState(ch?.enabled ?? true);
  const [cfg, setCfg] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(ch?.config ?? {}).map(([k, x]) => [k, String(x)])));
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: Event) => setCfg({ ...cfg, [k]: (e.currentTarget as HTMLInputElement).value });
  const field = (k: string, label: Key, ph = "") => (
    <label class="field">{t(label)}<input name={k} value={cfg[k] ?? ""} placeholder={ph} onInput={set(k)} /></label>
  );
  async function save(e: Event) {
    e.preventDefault();
    const config: Record<string, string | number> = { ...cfg };
    if (kind === "email") config.port = Number(cfg.port || 587);
    const body: Record<string, unknown> = { name, targets: targets.split(/[,;\s]+/).filter(Boolean), levels, lang, enabled, config };
    if (!ch) body.kind = kind;
    if (secret) body.secret = secret;
    setBusy(true);
    try {
      const r = await api<Channel>("POST", ch ? `/api/notify/${ch.id}` : "/api/notify", body);
      onDone(r.name);
    } catch (err) { say(errText(err)); } finally { setBusy(false); }
  }
  return (
    <form class="nt-form" data-notify-form onSubmit={(e) => void save(e)}>
      <h3>{ch ? t("ntEditTitle", { name: ch.name }) : t("ntAdd")}</h3>
      <div class="row-wrap">
        <label class="field">{t("ntColKind")}
          <select name="kind" value={kind} disabled={!!ch} onChange={(e) => setKind(e.currentTarget.value as NotifyKind)}>
            {KINDS.map((k) => <option key={k} value={k}>{t(KIND_KEY[k])}</option>)}
          </select>
        </label>
        <label class="field">{t("ntColName")}<input name="name" value={name} maxLength={60} onInput={(e) => setName(e.currentTarget.value)} /></label>
        <label class="field">{t("ntLang")}
          <select name="lang" value={lang} onChange={(e) => setLang(e.currentTarget.value)}>
            <option value="en">English</option><option value="zh">中文</option>
          </select>
        </label>
      </div>
      <label class="field">{t("ntColTo")}<input name="targets" value={targets} onInput={(e) => setTargets(e.currentTarget.value)} />
        <small class="muted">{t(TARGET_HINT[kind])}</small></label>
      {kind === "whatsapp" && (
        <div class="row-wrap">
          {field("phone_number_id", "ntWaPhoneId")}
          {field("template", "ntWaTemplate", "nexwar_alert")}
          {field("template_lang", "ntWaTemplateLang", "en")}
        </div>
      )}
      {kind === "whatsapp" && <p class="muted small">{t("ntWaHint")}</p>}
      {kind === "email" && (
        <div class="row-wrap">
          {field("host", "ntSmtpHost", "smtp.gmail.com")}
          {field("port", "ntSmtpPort", "587")}
          <label class="field">{t("ntSmtpSec")}
            <select name="security" value={cfg.security ?? "starttls"} onChange={set("security")}>
              <option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option><option value="none">{t("ntSmtpNone")}</option>
            </select>
          </label>
          {field("user", "ntSmtpUser")}
          {field("from", "ntSmtpFrom")}
        </div>
      )}
      <label class="field">{t(SECRET_KEY[kind])}
        <input name="secret" type="password" autoComplete="off" value={secret} placeholder={ch?.has_secret ? t("ntSecretKeep") : ""}
          onInput={(e) => setSecret(e.currentTarget.value)} />
      </label>
      <fieldset class="checks row-wrap">
        <legend>{t("ntColLevels")}</legend>
        {["P1", "P2"].map((l) => (
          <label key={l}><input type="checkbox" name={`level-${l}`} checked={levels.includes(l)}
            onChange={() => setLevels(levels.includes(l) ? levels.filter((x) => x !== l) : [...levels, l])} /> {l}</label>
        ))}
        <label><input type="checkbox" name="enabled" checked={enabled} onChange={() => setEnabled(!enabled)} /> {t("ntEnabled")}</label>
      </fieldset>
      <div class="row-wrap">
        <button type="submit" class="btn primary" disabled={busy || !name || !targets || levels.length === 0}>{t("ntSave")}</button>
        <button type="button" class="btn" onClick={onCancel}>{t("ntCancel")}</button>
      </div>
    </form>
  );
}

import { useState } from "preact/hooks";
import { api, ApiError } from "./api";
import type { Me } from "./app";
import { t, type Key } from "./i18n";
import { LangSwitch } from "./langswitch";

export function Login({ onIn, expired, note }: { onIn: (m: Me) => void; expired: boolean; note?: string | null }) {
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  // P2-05:记词条,不记译好的字(切语言跟着变)
  const [err, setErr] = useState<Key | "">("");
  const [show, setShow] = useState(false);

  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("POST", "/api/login", { name: name.trim(), password: pw, web: true });   // P2-06:首尾空格不算
      onIn(await api<Me>("GET", "/api/me"));
    } catch (x) {
      const s = x instanceof ApiError ? x.status : 0;
      setErr(s === 401 ? "badLogin" : s === 429 ? "lockedOut" : "siteUnreachable");
    } finally {
      setBusy(false);
      setPw("");
    }
  }

  return (
    <main class="login">
      <div class="login-top"><LangSwitch /></div>
      <form class="login-card" onSubmit={submit}>
        <div class="brand"><span class="mark">NW</span><span>{t("appName")}</span></div>
        <h1>{t("dutyConsole")}</h1>
        {note ? <p class="note" role="status">{note}</p> : expired && <p class="note" role="status">{t("sessionExpired")}</p>}
        <label>
          {t("account")}
          <input autocomplete="username" autoFocus value={name} onInput={(e) => setName(e.currentTarget.value)} required />
        </label>
        <label>
          {t("password")}
          <span class="pw-row">
            <input type={show ? "text" : "password"} autocomplete="current-password" value={pw}
              onInput={(e) => setPw(e.currentTarget.value)} required />
            <button type="button" class="btn sm pw-show" aria-pressed={show} onClick={() => setShow(!show)}>{t(show ? "pwHide" : "pwShow")}</button>
          </span>
        </label>
        {/* P2-04:错误那一行一直占着位置,出错时框不跳 */}
        <p class="error login-err" role="alert">{err ? t(err) : ""}</p>
        <button class="btn primary" type="submit" disabled={busy}>{busy ? t("signingIn") : t("signIn")}</button>
      </form>
    </main>
  );
}

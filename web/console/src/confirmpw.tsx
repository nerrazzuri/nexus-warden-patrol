// 「再输一次密码」(W44 第二期,设计 §5.2 第 4 条):开工程师账号、解绑机器人这类会出大事的操作。
// 站点判密码(跟登录同一个失败计数);不对写「密码不对」、锁了写「错太多次」,对话框不关,能再输。
import { useState } from "preact/hooks";
import { ApiError } from "./api";
import { Modal } from "./dialogs";
import { t } from "./i18n";

export function ConfirmPassword({ title, text, list, ack, onConfirm, onClose }: {
  title: string; text?: string;
  /** 易用性第 6 轮 W6-04:一起生效的东西点名列出来(发布时一起确认的禁行区)。 */
  list?: string[];
  /** 给了就要先勾上这一句才能确认。 */
  ack?: string;
  onConfirm: (pw: string) => Promise<void>; onClose: () => void;
}) {
  const [pw, setPw] = useState("");
  const [acked, setAcked] = useState(!ack);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await onConfirm(pw);
    } catch (x) {
      setErr(x instanceof ApiError && x.status === 403 ? t("pwWrong")
        : x instanceof ApiError && x.status === 429 ? t("pwLocked")
        : t("failed", { why: x instanceof ApiError ? x.message : String(x) }));
      setPw("");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal label={title} onClose={onClose}>
      <form class="form confirm-pw" onSubmit={submit}>
        {text && <p class="confirm-text">{text}</p>}
        {list && list.length > 0 && <ul class="plain small confirm-list">{list.map((x) => <li key={x}>{x}</li>)}</ul>}
        {ack && <label class="field-check"><input type="checkbox" checked={acked} onChange={(e) => setAcked(e.currentTarget.checked)} />{ack}</label>}
        <p class="muted small">{t("pwAgainHint")}</p>
        <label class="field">{t("pwAgain")}<input type="password" autoComplete="current-password" value={pw} required
          onInput={(e) => setPw(e.currentTarget.value)} /></label>
        {err && <p class="error" role="alert">{err}</p>}
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={busy || !pw || !acked}>{t("pwConfirm")}</button>
        </div>
      </form>
    </Modal>
  );
}

// 交班留言(redesign 第五期,记录与录像的第三个标签;原来在报警记录页上面一块):
// 左 写一条给下一班(保安、管理员、经理能写;只读账号只看);中 最近的留言(新的在前,谁、几点)。
// 只追加:写错了再写一条(站点 shift_notes 不改不删,交接说过什么要查得到)。值班页左栏仍显示最近一条。
import { useEffect, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { hm } from "./data";
import { t } from "./i18n";
import { dateInput } from "./recordings";
import { SubTabs } from "./shell";

interface Note { id: number; at_ms: number; author: string; text: string }
const SHOW = 50;

/** 能留话的(站点 HANDLE_ALERTS):管理员、保安、经理。 */
export function canNote(role: string): boolean {
  return role === "admin" || role === "engineer" || role === "guard" || role === "owner";
}

export function NotesPage(props: { role: string; me?: string }) {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const pull = () => api<{ recent?: Note[]; latest: Note | null }>("GET", `/api/shift-notes?recent=${SHOW}`)
    .then((d) => { setNotes(d.recent ?? (d.latest ? [d.latest] : [])); setFailed(false); })
    .catch(() => setFailed(true));
  useEffect(() => { void pull(); }, []);
  async function leave() {
    setErr("");
    setBusy(true);
    try {
      await api("POST", "/api/shift-notes", { text: draft });
      setDraft("");
      await pull();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const write = canNote(props.role);
  return (
    <div class="ev notes">
      <aside class="ev-left">
        <SubTabs page="notes" role={props.role} rail />
        {write ? (
          <div class="ev-f notes-write">
            <label for="notes-text">{t("notesWrite")}</label>
            <textarea id="notes-text" rows={6} maxLength={500} placeholder={t("alNoteHint")} value={draft}
              onInput={(e) => setDraft((e.target as HTMLTextAreaElement).value)} />
            <button type="button" class="btn primary" disabled={!draft.trim() || busy} onClick={() => void leave()}>{t("alNoteSave")}</button>
            {err && <p class="error" role="alert">{err}</p>}
          </div>
        ) : <p class="muted small">{t("notesReadOnly")}</p>}
      </aside>
      <section class="ev-main notes-main">
        <header class="ev-head">
          <div>
            <h1>{t("notesTitle")}</h1>
            <p class="muted small">{t("notesSub")}</p>
          </div>
        </header>
        {notes == null && <p class={failed ? "empty warn" : "empty"}>{t(failed ? "loadRetry" : "loading")}</p>}
        {notes != null && notes.length === 0 && <p class="empty">{t("notesNone")}</p>}
        {notes != null && notes.length > 0 && (
          <ol class="notes-list">
            {notes.map((n) => (
              <li key={n.id} data-note-id={n.id}>
                <header>
                  <b>{n.author}{n.author === props.me ? ` (${t("notesMine")})` : ""}</b>
                  <time class="mono">{dateInput(n.at_ms)} {hm(n.at_ms)}</time>
                </header>
                <p>{n.text}</p>
              </li>
            ))}
          </ol>
        )}
        {notes != null && notes.length >= SHOW && <p class="muted small">{t("notesMore", { n: SHOW })}</p>}
      </section>
    </div>
  );
}

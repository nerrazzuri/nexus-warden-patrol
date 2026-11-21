// 第四档 #44:路线列表上的「导出」「导入」。导出 = 这张图这一版上的路线存成一个文件下载;
// 导入 = 选文件 → 列出每条怎么办(新建 / 盖掉同名的 / 编号用过换一个)→ 一条条存,存不下的说原因。
import { useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { buildRouteFile, parseRouteFile, planImport, routeFileName, type ImportRow, type RouteFile } from "./routeio";
import type { Route, RouteView } from "./routes";
import { rt } from "./routes_i18n";
import { siteStr } from "./sitetext";

type Say = (msg: string) => void;
interface Result { id: string; ok: boolean; why?: string }

export function RouteIO({ sel, kind, routes, say, onDone }: {
  sel: { map_id: string; version: string }; kind: "patrol" | "guard"; routes: readonly Route[]; say: Say; onDone: () => void;
}) {
  const [file, setFile] = useState<RouteFile | null>(null);
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [pick, setPick] = useState<boolean[]>([]);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Result[] | null>(null);
  const [err, setErr] = useState("");

  function download() {
    const f = buildRouteFile(routes, sel, kind);
    const blob = new Blob([JSON.stringify(f, null, 2) + "\n"], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = routeFileName(f);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    say(rt("ioExported", { n: routes.length }));
  }

  async function choose(ev: Event) {
    const input = ev.currentTarget as HTMLInputElement;
    const f0 = input.files?.[0];
    input.value = "";
    setResults(null);
    setErr("");
    setFile(null);
    if (!f0) return;
    const got = parseRouteFile(await f0.text());
    if ("error" in got) { setErr(rt(`ioErr_${got.error}` as never)); return; }
    if (got.kind !== kind) { setErr(rt(got.kind === "guard" ? "ioErrGuardFile" : "ioErrPatrolFile")); return; }
    if (got.map_id !== sel.map_id) { setErr(rt("ioErrMap", { map: got.map_id, here: sel.map_id })); return; }
    try {
      // 编号全站唯一:别的图、别的版本上的,删掉过的都算用过
      const all = await api<RouteView>("GET", "/api/routes");
      const plan = planImport(got, routes, [...all.routes.map((r) => r.id), ...(all.retired_routes ?? [])]);
      setFile(got);
      setRows(plan);
      setPick(plan.map((r) => r.action !== "replace"));            // 盖掉现有的默认不勾
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function run() {
    if (!file) return;
    setBusy(true);
    const out: Result[] = [];
    for (let i = 0; i < rows.length; i++) {
      if (!pick[i]) continue;
      const r = rows[i];
      try {
        await api("POST", `/api/routes/${enc(r.id)}`, {
          map_id: sel.map_id, map_version: sel.version, waypoints: r.from.waypoints, policy: r.from.policy ?? {},
          base_revision: r.base, kind, ...(r.from.title ? { title: r.from.title } : {}),
        });
        out.push({ id: r.id, ok: true });
      } catch (e) {
        const errs = e instanceof ApiError ? (e.data as { errors?: { name: string; problem: string }[] } | undefined)?.errors : undefined;
        const why = Array.isArray(errs) && errs.length
          ? errs.slice(0, 3).map((x) => (x.name ? `${x.name}: ${siteStr(x.problem)}` : siteStr(x.problem))).join("; ")
          : e instanceof ApiError && e.status === 409 ? rt("ioConflict")
            : e instanceof ApiError ? siteStr(e.message) : String(e);
        out.push({ id: r.id, ok: false, why });
      }
    }
    setBusy(false);
    setResults(out);
    setFile(null);
    const ok = out.filter((x) => x.ok).length;
    say(rt("ioImported", { ok, n: out.length }));
    onDone();
  }

  const n = pick.filter(Boolean).length;
  return (
    <div class="routeio" data-routeio="1">
      <div class="routeio-btns">
        <button type="button" class="btn sm" data-route-export="1" onClick={download} disabled={routes.length === 0}
          title={routes.length === 0 ? rt("ioNothing") : undefined}>{rt("ioExport")}</button>
        <label class="btn sm routeio-pick">
          {rt("ioImport")}
          <input type="file" accept=".json,application/json" data-route-import="1" onChange={choose} />
        </label>
      </div>
      {err && <p class="error small" role="alert" data-routeio-err="1">{err}</p>}
      {file && (
        <div class="routeio-plan" data-routeio-plan="1">
          <p class="small">{rt("ioFrom", { map: `${file.map_id} · v${file.map_version}`, n: file.routes.length })}
            {file.map_version !== sel.version && <> {rt("ioOtherVersion", { v: sel.version })}</>}</p>
          <ul class="routeio-rows">
            {rows.map((r, i) => (
              <li key={i} data-import-row={r.from.id}>
                <label>
                  <input type="checkbox" checked={pick[i]} onChange={(e) => setPick(pick.map((x, j) => (j === i ? e.currentTarget.checked : x)))} />
                  <span class="routeio-name">{r.from.title || r.from.id}</span>
                  <span class="muted small">{rt("ioPoints", { n: r.from.waypoints.length })}</span>
                  <span class={`routeio-act ${r.action}`} data-action={r.action}>
                    {r.action === "new" ? rt("ioNew") : r.action === "replace" ? rt("ioReplace") : rt("ioRename", { id: r.id })}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div class="routeio-btns">
            <button type="button" class="btn primary sm" data-import-run="1" disabled={busy || n === 0} onClick={() => void run()}>
              {rt("ioRun", { n })}</button>
            <button type="button" class="btn sm" disabled={busy} onClick={() => setFile(null)}>{rt("ioCancel")}</button>
          </div>
        </div>
      )}
      {results && results.some((x) => !x.ok) && (
        <ul class="small routeio-failed" data-routeio-failed="1">
          {results.filter((x) => !x.ok).map((x) => <li key={x.id}><b>{x.id}</b>: {x.why}</li>)}
        </ul>
      )}
    </div>
  );
}

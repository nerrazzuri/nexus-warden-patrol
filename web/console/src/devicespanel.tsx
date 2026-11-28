// W73 第五期 外部设备（门磁、报警主机）按位置登记：站点按位置算查看点、所在防区；每台一个专属回调（自己的密钥）。
// 1.1-3：「先核实」（先派机器人去看，看见人才 P1）；不会签名的设备换接法：触发网址、报警主机 SIA DC-09、IO 模块干接点。
// 摄像头不在这里：在「布置 → 摄像头」放到图上就行（ONVIF 订阅，站点按它的位置、朝向算查看点）。
import { useEffect, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { lang, t, type Lang } from "./i18n";

export interface Link { via: "signed" | "url" | "sia" | "modbus"; account?: string; zone?: string; host?: string; port?: number; unit?: number; input?: number; nc?: boolean }
export interface Device { id: string; kind: string; map_id: string; map_version: string; x: number; y: number; yaw: number;
  view_x: number; view_y: number; zone: string; note: string; source: string; verify_first?: boolean; link?: Link }
interface DevStatus { last_ms?: number; error?: string; state?: string; what?: string }

const en = {
  dTitle: "Alarm devices by position",
  dLead: "Door contacts and alarm panels: put them on the map; the site works out where a robot should go and which zone it is in. Each device gets its own signed callback. Cameras: place them under Setup → Cameras.",
  dNone: "No devices yet.",
  dId: "Device ID", dKind: "Type", dMap: "Map", dVer: "Version", dX: "x (m)", dY: "y (m)",
  kContact: "Door contact", kAlarm: "Alarm panel", kOther: "Other",
  dAdd: "Add / update", dRemove: "Delete", dRotate: "New key",
  dView: "robot goes to ({x}, {y})", dZone: "zone {z}", dNoZone: "not in any zone (site-wide)",
  dSecret: "Callback for {id}: header X-Nexwar-Source: {src}, key (shown once): {key}",
  dVerify: "Verify first: send a robot to look; raise P1 only if it sees someone",
  dVerifyOn: "verify first", dVerifyOff: "alarm at once",
  dVia: "Connection", vSigned: "Signed callback", vUrl: "Trigger URL (no signing)", vSia: "Alarm panel (SIA DC-09)", vModbus: "Dry contact via I/O module (Modbus TCP)",
  dAcct: "Panel account", dPanelZone: "Panel zone (empty = all)", dHost: "I/O module address", dPort: "Port", dUnit: "Unit ID", dInput: "Input no.", dNc: "Normally closed (alarm when opened)",
  dNewUrl: "New URL",
  dUrl: "Trigger URL for {id} (shown once — the device calls it with GET or POST): {url}",
  dSiaPort: "Alarm panels report to this site on TCP port {p} (SIA DC-09, unencrypted).", dSiaOff: "Alarm-panel receiver is off (set alarm_receiver.sia_port in site.json).",
  dLast: "last trigger {t}", dErr: "not reachable: {why}",
};
type DKey = keyof typeof en;
const zh: Record<DKey, string> = {
  dTitle: "外部设备（按位置）",
  dLead: "门磁、报警主机：放到图上，站点自己算机器人去哪看、属于哪个防区；每台一个专属签名回调。摄像头在「布置 → 摄像头」放到图上就行。",
  dNone: "还没有登记设备。",
  dId: "设备编号", dKind: "类型", dMap: "地图", dVer: "版本", dX: "x（米）", dY: "y（米）",
  kContact: "门磁", kAlarm: "报警主机", kOther: "其他",
  dAdd: "登记 / 更新", dRemove: "删除", dRotate: "换密钥",
  dView: "机器人去（{x}，{y}）", dZone: "防区 {z}", dNoZone: "不在任何防区（按全站）",
  dSecret: "{id} 的回调：请求头 X-Nexwar-Source: {src}，密钥（只显示这一次）：{key}",
  dVerify: "先核实：先派机器人去看，看见人才报 P1",
  dVerifyOn: "先核实", dVerifyOff: "直接报警",
  dVia: "接入方式", vSigned: "签名回调", vUrl: "触发网址（不用签名）", vSia: "报警主机（SIA DC-09）", vModbus: "干接点接 IO 模块（Modbus TCP）",
  dAcct: "主机用户号", dPanelZone: "主机防区号（空着 = 全部）", dHost: "IO 模块地址", dPort: "端口", dUnit: "站号", dInput: "输入号", dNc: "常闭（断开算报警）",
  dNewUrl: "换网址",
  dUrl: "{id} 的触发网址（只显示这一次，设备用 GET 或 POST 调它）：{url}",
  dSiaPort: "报警主机报到本站点 TCP 端口 {p}（SIA DC-09，不加密）。", dSiaOff: "报警主机接收没开（在 site.json 里设 alarm_receiver.sia_port）。",
  dLast: "上次触发 {t}", dErr: "读不到：{why}",
};
const DICTS: Record<Lang, Record<DKey, string>> = { en, zh };
function dt(k: DKey, v?: Record<string, string | number>): string {
  let s = (DICTS[lang.value] ?? zh)[k];
  for (const [a, b] of Object.entries(v ?? {})) s = s.split(`{${a}}`).join(String(b));
  return s;
}

export function DevicesPanel({ canEdit, say }: { canEdit: boolean; say: (s: string) => void }) {
  const [list, setList] = useState<Device[] | null>(null);
  const [status, setStatus] = useState<Record<string, DevStatus>>({});
  const [siaPort, setSiaPort] = useState<number | null>(null);
  const [f, setF] = useState({ id: "", kind: "contact", map_id: "", map_version: "", x: "", y: "" });
  // 1.1-3:先核实、接入方式(门磁、报警主机默认先核实)
  const [verify, setVerify] = useState(true);
  const [via, setVia] = useState<Link["via"]>("signed");
  const [lk, setLk] = useState({ account: "", zone: "", host: "", port: "502", unit: "1", input: "0", nc: false });
  const [secret, setSecret] = useState<string>("");
  const load = () => api<{ devices: Device[]; status?: Record<string, DevStatus>; sia_port?: number | null }>("GET", "/api/devices")
    .then((d) => { setList(d.devices); setStatus(d.status ?? {}); setSiaPort(d.sia_port ?? null); }).catch(() => setList(null));
  useEffect(() => { void load(); }, []);
  if (list === null) return null;                        // 站点没开这一项
  const err = (e: unknown) => say(e instanceof ApiError ? e.message : String(e));
  async function add() {
    try {
      const link: Link = via === "sia" ? { via, account: lk.account, zone: lk.zone }
        : via === "modbus" ? { via, host: lk.host, port: Number(lk.port), unit: Number(lk.unit), input: Number(lk.input), nc: lk.nc } : { via };
      const r = await api<{ secret: string | null; source: string; token?: string | null }>("POST", "/api/devices",
        { id: f.id, kind: f.kind, map_id: f.map_id, map_version: f.map_version, x: Number(f.x), y: Number(f.y), verify_first: verify, link });
      setSecret(r.token ? dt("dUrl", { id: f.id, url: `${location.origin}/api/alarm-in/${r.token}` })
        : r.secret && via === "signed" ? dt("dSecret", { id: f.id, src: r.source, key: r.secret }) : "");
      await load();
    } catch (e) { err(e); }
  }
  async function newUrl(d: Device) {
    try {
      const r = await api<{ token?: string | null }>("POST", "/api/devices", { id: d.id, kind: d.kind, map_id: d.map_id, map_version: d.map_version,
        x: d.x, y: d.y, yaw: d.yaw, link: { via: "url", new_token: true } });
      setSecret(r.token ? dt("dUrl", { id: d.id, url: `${location.origin}/api/alarm-in/${r.token}` }) : "");
      await load();
    } catch (e) { err(e); }
  }
  async function act(id: string, what: "remove" | "rotate") {
    try {
      const r = await api<{ secret?: string; source?: string }>("POST", "/api/devices", { id, [what]: true });
      setSecret(r.secret ? dt("dSecret", { id, src: r.source ?? `dev-${id}`, key: r.secret }) : "");
      await load();
    } catch (e) { err(e); }
  }
  const kind = (k: string) => (k === "contact" ? dt("kContact") : k === "alarm" ? dt("kAlarm") : dt("kOther"));
  const viaText = (l?: Link) => {
    if (!l || l.via === "signed") return dt("vSigned");
    if (l.via === "url") return dt("vUrl");
    if (l.via === "sia") return `${dt("vSia")} #${l.account}${l.zone ? `/${l.zone}` : ""}`;
    return `${dt("vModbus")} ${l.host}:${l.port} #${l.input}${l.nc ? " NC" : ""}`;
  };
  const stText = (st?: DevStatus) => (!st ? "" : st.error ? dt("dErr", { why: st.error })
    : st.last_ms ? dt("dLast", { t: new Date(st.last_ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) }) : "");
  const lkIn = (k: "account" | "zone" | "host" | "port" | "unit" | "input", label: DKey, num = false) => (
    <label class="field">{dt(label)}<input name={`dev-${k}`} type={num ? "number" : "text"} value={lk[k]} onInput={(e) => setLk({ ...lk, [k]: e.currentTarget.value })} /></label>
  );
  return (
    <section class="card devices-panel">
      <h2>{dt("dTitle")}</h2>
      <p class="muted small">{dt("dLead")}</p>
      {/* 网页易用性 P1-61:只看不能改的要说为什么 */}
      {!canEdit && <p class="small readonly-note">{t("adminOnlyNote")}</p>}
      {list.length === 0 ? <p class="muted">{dt("dNone")}</p> : (
        <ul class="plain">
          {list.map((d) => (
            <li key={d.id} class="device-row">
              <b>{d.id}</b> · {kind(d.kind)} · {dt("dView", { x: d.view_x.toFixed(1), y: d.view_y.toFixed(1) })} · {d.zone ? dt("dZone", { z: d.zone }) : dt("dNoZone")}
              {" · "}<span data-verify={d.verify_first ? "on" : "off"}>{d.verify_first ? dt("dVerifyOn") : dt("dVerifyOff")}</span>
              {" · "}<span data-via={d.link?.via ?? "signed"}>{viaText(d.link)}</span>
              {stText(status[d.id]) && <span class={status[d.id]?.error ? "bad small" : "muted small"}> · {stText(status[d.id])}</span>}
              {canEdit && d.link?.via === "url" && <> <button type="button" class="btn sm" onClick={() => newUrl(d)}>{dt("dNewUrl")}</button></>}
              {canEdit && (d.link?.via ?? "signed") === "signed" && <> <button type="button" class="btn sm" onClick={() => act(d.id, "rotate")}>{dt("dRotate")}</button></>}
              {canEdit && <>
                <button class="btn sm danger" type="button" onClick={() => act(d.id, "remove")}>{dt("dRemove")}</button></>}
            </li>
          ))}
        </ul>
      )}
      {secret && <p class="device-secret" role="status">{secret}</p>}
      <p class="muted small" data-sia-port>{siaPort ? dt("dSiaPort", { p: siaPort }) : dt("dSiaOff")}</p>
      {canEdit && (
        <div class="device-form">
          {/* UIUX-026:每格一个看得见的标签(以前只有 placeholder,填了字就看不出这格是什么) */}
          <label class="field">{dt("dId")}<input name="dev-id" value={f.id} onInput={(e) => setF({ ...f, id: e.currentTarget.value })} /></label>
          <label class="field">{dt("dKind")}<select name="dev-kind" value={f.kind} onChange={(e) => { setF({ ...f, kind: e.currentTarget.value }); setVerify(e.currentTarget.value !== "other"); }}>
            <option value="contact">{dt("kContact")}</option><option value="alarm">{dt("kAlarm")}</option><option value="other">{dt("kOther")}</option>
          </select></label>
          <label class="field">{dt("dMap")}<input name="dev-map" value={f.map_id} onInput={(e) => setF({ ...f, map_id: e.currentTarget.value })} /></label>
          <label class="field">{dt("dVer")}<input name="dev-ver" value={f.map_version} onInput={(e) => setF({ ...f, map_version: e.currentTarget.value })} /></label>
          <label class="field">{dt("dX")}<input name="dev-x" type="number" step="0.1" value={f.x} onInput={(e) => setF({ ...f, x: e.currentTarget.value })} /></label>
          <label class="field">{dt("dY")}<input name="dev-y" type="number" step="0.1" value={f.y} onInput={(e) => setF({ ...f, y: e.currentTarget.value })} /></label>
          <label class="field">{dt("dVia")}<select name="dev-via" value={via} onChange={(e) => setVia(e.currentTarget.value as Link["via"])}>
            <option value="signed">{dt("vSigned")}</option><option value="url">{dt("vUrl")}</option>
            <option value="sia">{dt("vSia")}</option><option value="modbus">{dt("vModbus")}</option>
          </select></label>
          {via === "sia" && <>{lkIn("account", "dAcct")}{lkIn("zone", "dPanelZone")}</>}
          {via === "modbus" && <>{lkIn("host", "dHost")}{lkIn("port", "dPort", true)}{lkIn("unit", "dUnit", true)}{lkIn("input", "dInput", true)}
            <label class="check"><input type="checkbox" name="dev-nc" checked={lk.nc} onChange={() => setLk({ ...lk, nc: !lk.nc })} /> {dt("dNc")}</label></>}
          <label class="check"><input type="checkbox" name="dev-verify" checked={verify} onChange={() => setVerify(!verify)} /> {dt("dVerify")}</label>
          <button type="button" class="btn primary" onClick={add} disabled={!f.id || !f.map_id || !f.map_version || f.x === "" || f.y === ""}>{dt("dAdd")}</button>
        </div>
      )}
    </section>
  );
}

// 布置 → 待命点(W44 第三期,设计 §5.2):机器人没事时去哪待着。每台机器人的待命点画成图标(默认的实心);
// 拖图标改位置、拖箭头改朝向;选中一个以后点图也能把它挪过去(手机、触屏好用);「加一个待命点」点图放下,选哪台、起名;
// 选中能设成默认、删。充电桩只画出来看(改充电桩在机器人页 / 手机上)。外框「保存」一起存。
import { useEffect, useRef, useState } from "preact/hooks";
import { api } from "./api";
import { Confirm, Modal } from "./dialogs";
import { clickGuard, startDrag, swallowClick } from "./dragpt";
import { t } from "./i18n";
import { toMap, type StandbyPt, type TabProps } from "./layoutpage";
import { PoseMarker } from "./posemarker";
import { NAME_RE } from "./routepage";
import { clientToMap, handleAt, yawToward } from "./routes";

const key = (p: { robot_id: string; name: string }) => `${p.robot_id}/${p.name}`;
interface Carried { robot_id: string; name: string; x: number; y: number; yaw: number; default?: boolean }
interface Charger { robot_id: string; map_id: string; map_version: string; x: number; y: number }

export function StandbyTab(p: TabProps) {
  const [pts, setPts] = useState<StandbyPt[]>(p.data.standby);
  const [sel, setSel] = useState<string | null>(null);
  const [adding, setAdding] = useState<"pick" | { x: number; y: number } | null>(null);
  const [removing, setRemoving] = useState<StandbyPt | null>(null);
  const [chargers, setChargers] = useState<Charger[]>([]);
  const root = useRef<HTMLDivElement>(null);
  const guard = useRef(clickGuard());

  useEffect(() => {
    api<{ chargers: Charger[] }>("GET", "/api/chargers").then((d) => setChargers((d.chargers ?? [])
      .filter((c) => c.map_id === p.map.map_id && c.map_version === p.map.version))).catch(() => setChargers([]));
  }, []);
  // 第 4 轮 setup N1:站点的待命点后到(机器人列表晚到、重新取过),本地没改过就跟上,不当成「没保存」
  const seen = useRef(p.data.standby);
  useEffect(() => {
    if (JSON.stringify(pts) === JSON.stringify(seen.current)) setPts(p.data.standby);
    seen.current = p.data.standby;
  }, [p.data.standby]);
  const changed = JSON.stringify(pts) !== JSON.stringify(p.data.standby);
  useEffect(() => p.setDirty(changed), [changed]);
  useEffect(() => {
    p.registerSave(async () => {
      const now = new Map(pts.map((x) => [key(x), x]));
      for (const o of p.data.standby) {
        if (!now.has(key(o))) await api("POST", `/api/robots/${encodeURIComponent(o.robot_id)}/standby`, { name: o.name, remove: true });
      }
      const old = new Map(p.data.standby.map((x) => [key(x), x]));
      // 先存不是默认的,再存默认的(站点设默认时会把这台别的点的默认清掉)
      const order = [...pts].sort((a, b) => Number(!!a.default) - Number(!!b.default));
      for (const x of order) {
        if (JSON.stringify(old.get(key(x))) === JSON.stringify(x)) continue;
        await api("POST", `/api/robots/${encodeURIComponent(x.robot_id)}/standby`,
          { name: x.name, map_id: p.map.map_id, map_version: p.map.version, x: x.x, y: x.y, yaw: x.yaw, default: !!x.default });
      }
      await p.reload("standby");
    });
    return () => p.registerSave(null);
  }, [pts]);

  // 第 4 轮 maps N1 / setup P0-14:从上一版带过来的待命点(待核建议)列在这里,核过位置一个个留下或全留下,再保存
  const prop = p.data.nav?.proposal;
  const [dropped, setDropped] = useState<string[]>([]);
  const carried = ((prop?.standby ?? []) as Carried[])
    .filter((c) => p.data.robots.includes(c.robot_id) && !pts.some((x) => key(x) === key(c)) && !dropped.includes(key(c)));
  // minor #27:不要的带过来的待命点丢掉(只丢待命点,禁行区、拦截点的建议不动)
  const drop = async (cs: Carried[]) => {
    try {
      await api("POST", `${p.base}/zones/proposal`, { action: "drop_standby", standby: cs.map((c) => ({ robot_id: c.robot_id, name: c.name })) });
      setDropped((d) => [...d, ...cs.map(key)]);
      void p.reload("nav");
    } catch (e) {
      p.say(t("failed", { why: String((e as Error).message ?? e) }));
    }
  };
  const keep = (cs: Carried[]) => {
    const add = cs.map((c): StandbyPt => ({ robot_id: c.robot_id, name: c.name, x: c.x, y: c.y, yaw: c.yaw,
      map_id: p.map.map_id, map_version: p.map.version, default: !!c.default && !pts.some((x) => x.robot_id === c.robot_id && x.default) }));
    setPts([...pts, ...add]);
    if (add.length === 1) setSel(key(add[0]));
  };

  const patch = (k: string, f: Partial<StandbyPt>) => setPts((all) => all.map((x) => (key(x) === k ? { ...x, ...f } : x)));
  const cur = pts.find((x) => key(x) === sel) ?? null;

  function pick(px: number, py: number) {
    const [x, y] = toMap(p.meta, px, py);
    if (adding === "pick") setAdding({ x, y });
    else if (cur) patch(key(cur), { x, y });
  }
  const drag = (k: string, what: "move" | "turn") => (e: PointerEvent) => {
    setSel(k);
    startDrag(e, guard.current, (cx, cy) => {
      const m = clientToMap(root.current, p.meta, cx, cy);
      if (!m) return;
      setPts((all) => all.map((x) => {
        if (key(x) !== k) return x;
        if (what === "move") return { ...x, x: m[0], y: m[1] };
        const yaw = yawToward(x.x, x.y, m[0], m[1]);
        return yaw === null ? x : { ...x, yaw };
      }));
    });
  };

  return (
    <div class="ly-tab">
      <div ref={root} onClickCapture={(e) => swallowClick(guard.current, e)}>
        <p.Map
          legend={["standby"]}
          drawing={adding === "pick" || !!cur}
          onPick={adding === "pick" || cur ? pick : undefined}
          marks={(s) => <>
            {/* 第 5 轮 maps:带过来还没留下的点先淡着画出来,留不留之前看得到在哪 */}
            {carried.map((c) => {
              const h = handleAt(p.meta, s, c.x, c.y, c.yaw, 26);
              return (
                <PoseMarker key={`carried-${key(c)}`} x={h.x} y={h.y} hx={h.hx} hy={h.hy} r={10} label={c.name.slice(0, 2)} selected={false}
                  class="standby-pt carried" attrs={{ "data-carried-mark": key(c) } as Record<string, unknown>}>
                  <title>{`${c.robot_id} · ${c.name} · ${t("lyStandbyCarriedTip", { v: prop?.from_version ?? "" })}`}</title>
                </PoseMarker>
              );
            })}
            {chargers.map((c) => { const [x, y] = s.map(c.x, c.y); return <g key={`c-${c.robot_id}`} class="ly-charger"><circle cx={x} cy={y} r={7} /><title>{t("lyCharger", { id: c.robot_id })}</title></g>; })}
            {pts.map((x) => {
              const h = handleAt(p.meta, s, x.x, x.y, x.yaw, 26);
              const k = key(x);
              return (
                <PoseMarker key={k} x={h.x} y={h.y} hx={h.hx} hy={h.hy} r={10} label={x.name.slice(0, 2)} selected={k === sel}
                  class={`standby-pt${x.default ? " default" : ""}`}
                  attrs={{ "data-standby": k, onPointerDown: drag(k, "move"), onClick: (e: MouseEvent) => { e.stopPropagation(); setSel(k); } } as Record<string, unknown>}
                  handle={k === sel ? { data: k, onPointerDown: drag(k, "turn") } : undefined}>
                  <title>{`${x.robot_id} · ${x.name}`}</title>
                </PoseMarker>
              );
            })}
          </>} />
      </div>
      <div class="ly-side">
        <button type="button" class="btn primary" disabled={p.data.robots.length === 0} onClick={() => { setAdding("pick"); setSel(null); }}>{t("lyAddStandby")}</button>
        {p.data.robots.length === 0 && <span class="muted small" data-why-no-add="1">{t("lyStandbyNoRobots")}</span>}
        {adding === "pick" && <p class="muted small">{t("lyAddStandbyHint")} <button type="button" class="link" onClick={() => setAdding(null)}>{t("cancel")}</button></p>}
        <p class="muted small">{t("lyStandbyHint")}</p>
        {carried.length > 0 && (
          <section class="note warn ly-carried" data-carried-standby={carried.length}>
            <p>{t("lyStandbyCarried", { n: carried.length, v: prop?.from_version ?? "" })}</p>
            <p class="small muted">{t("lyStandbyCarriedHint")}</p>
            {/* 第 5 轮 r5-maps-N1:「留下」是挪不是抄(站点一台机器人一个名字只有一个待命点),先说清楚 */}
            <p class="small warn" data-carried-move="1">{t("lyStandbyCarriedMove", { from: prop?.from_version ?? "", v: p.map.version })}</p>
            <ul class="plain">
              {carried.map((c) => (
                <li key={key(c)} class="row">
                  <span>{c.robot_id} · {c.name}{c.default ? ` · ${t("lyDefault")}` : ""}</span>
                  <button type="button" class="btn sm push" data-keep={key(c)} onClick={() => keep([c])}>{t("lyKeep")}</button>
                  <button type="button" class="btn sm ghost" data-drop={key(c)} onClick={() => void drop([c])}>{t("lyDrop")}</button>
                </li>
              ))}
            </ul>
            {carried.length > 1 && <div class="row">
              <button type="button" class="btn sm" data-keep-all="1" onClick={() => keep(carried)}>{t("lyKeepAll")}</button>
              <button type="button" class="btn sm ghost" data-drop-all="1" onClick={() => void drop(carried)}>{t("lyDropAll")}</button>
            </div>}
          </section>
        )}
        <ul class="plain ly-list">
          {pts.length === 0 && <li class="muted small">{t("lyNoStandby")}</li>}
          {pts.map((x) => (
            <li key={key(x)}>
              <button type="button" class={key(x) === sel ? "linklike on" : "linklike"} onClick={() => setSel(key(x))}>{x.robot_id} · {x.name}</button>
              {x.default && <span class="tag">{t("lyDefault")}</span>}
            </li>
          ))}
        </ul>
        {cur && (
          <section class="panel ly-detail">
            <h3>{cur.robot_id} · {cur.name}</h3>
            <p class="muted small">{t("lyStandbyMoveHint")}</p>
            <label class="field-check"><input type="checkbox" name="default" checked={!!cur.default} onChange={(e) => {
              const on = e.currentTarget.checked;
              setPts((all) => all.map((x) => (x.robot_id !== cur.robot_id ? x : { ...x, default: key(x) === key(cur) ? on : on ? false : x.default })));
            }} />{t("lyStandbyDefault")}</label>
            <div class="row end"><button type="button" class="btn sm" onClick={() => setRemoving(cur)}>{t("remove")}</button></div>
          </section>
        )}
      </div>
      {adding && adding !== "pick" && (
        <AddStandby robots={p.data.robots} taken={pts} onClose={() => setAdding(null)} onSave={(robot, name) => {
          const n: StandbyPt = { robot_id: robot, name, x: adding.x, y: adding.y, yaw: 0, map_id: p.map.map_id, map_version: p.map.version,
            default: !pts.some((x) => x.robot_id === robot) };
          setPts([...pts, n]);
          setSel(key(n));
          setAdding(null);
        }} />
      )}
      {removing && (
        <Confirm text={t("lyStandbyRemove", { name: `${removing.robot_id} · ${removing.name}` })} yes={t("remove")} danger onNo={() => setRemoving(null)}
          onYes={() => { const r = removing; setRemoving(null); setSel(null); setPts(pts.filter((x) => key(x) !== key(r))); }} />
      )}
    </div>
  );
}

function AddStandby({ robots, taken, onClose, onSave }: { robots: string[]; taken: StandbyPt[]; onClose: () => void; onSave: (robot: string, name: string) => void }) {
  const [robot, setRobot] = useState(robots[0] ?? "");
  const [name, setName] = useState("");
  const dup = taken.some((x) => x.robot_id === robot && x.name === name.trim());
  // 第 2 轮 setup N13:名字不合规(中文、空格……)写出来,不只是「完成」变灰
  const badName = name.trim() !== "" && !NAME_RE.test(name.trim());
  const ok = !!robot && NAME_RE.test(name.trim()) && !dup;
  return (
    <Modal label={t("lyAddStandby")} onClose={onClose}>
      <form class="form" onSubmit={(e) => { e.preventDefault(); if (ok) onSave(robot, name.trim()); }}>
        <label class="field">{t("lyWhichRobot")}
          <select name="robot" value={robot} onChange={(e) => setRobot(e.currentTarget.value)}>
            {robots.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label class="field">{t("lyStandbyName")}<input name="name" value={name} maxLength={64} autoFocus
          aria-invalid={badName || dup || undefined} onInput={(e) => setName(e.currentTarget.value)} /></label>
        <p class={dup || badName ? "small bad" : "muted small"} role={dup || badName ? "alert" : undefined} data-sb-name-bad={badName || undefined}>
          {dup ? t("lyStandbyDup") : badName ? t("lyStandbyNameBad") : t("lyStandbyNameHint")}</p>
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={!ok}>{t("dlgApply")}</button>
        </div>
      </form>
    </Modal>
  );
}

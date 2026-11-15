// 同时几件事(redesign 第四期 G-multi):两件以上安全事件开着、保安还没点进哪一件时,中间先看全局 ——
// 地图(报警的防区标红)+ 一张表:每件谁管、哪台去 / 多远、看哪路画面、下一步(没人管的「接手」,其余「打开」)。
// 「请求支援(通知经理)」要后端新接口,第 8 期补;这里不放假按钮。
import type { ComponentChildren } from "preact";
import { alertHeadline } from "./alertinfo";
import { hm, nameOf } from "./data";
import { t } from "./i18n";
import type { UnitInfo } from "./live";
import type { Alert } from "./model";
import { Sign } from "./signs";
import { byText } from "./sitetext";
import { awayText, responder, type FixedCam } from "./incident";

export function MultiView(props: {
  events: Alert[];
  units: UnitInfo[];
  cams: FixedCam[];
  /** 能不能接手(保安、管理员;经理也能处理报警)。 */
  canTake: boolean;
  onOpen: (a: Alert) => void;
  onTake: (a: Alert) => void;
  /** 中间的地图(值班页给,跟平时同一张)。 */
  map: ComponentChildren;
}) {
  const first = props.events.length ? Math.min(...props.events.map((a) => a.first_ms)) : 0;
  const last = props.events.length ? Math.max(...props.events.map((a) => a.first_ms)) : 0;
  // 唯一的主按钮:最早那件没人管的
  const lead = props.canTake ? [...props.events].sort((x, y) => x.first_ms - y.first_ms).find((a) => a.acked_ms == null)?.key ?? null : null;
  return (
    <div class="multi">
      <header class="multi-head inc-head p1">
        <Sign kind="bad" />
        <div class="inc-head-text">
          <h1>{t("multiTitle", { n: props.events.length })}</h1>
          <p>{t("multiSub", { a: hm(first), b: hm(last) })}</p>
        </div>
      </header>
      <div class="multi-map">{props.map}</div>
      <table class="multi-table">
        <thead>
          <tr><th>{t("multiEvent")}</th><th>{t("multiOwner")}</th><th>{t("multiResponder")}</th><th>{t("multiVideo")}</th><th>{t("multiNext")}</th></tr>
        </thead>
        <tbody>
          {[...props.events].sort((x, y) => x.first_ms - y.first_ms).map((a) => {
            const r = responder(a, props.units);
            const zone = a.context?.zone ?? a.context?.where ?? "";
            const cam = props.cams.find((c) => zone && c.zone === zone);
            const video = [cam?.name, r ? `${nameOf(r.u.robot.robot_id)} ${t("front")}` : ""].filter(Boolean).join(" · ");
            const owner = a.acked_ms != null && a.acked_by ? byText(a.acked_by) : null;
            return (
              <tr key={a.key} class={owner ? "" : "unowned"} data-key={a.key}>
                <td><span class="multi-ev"><Sign kind={a.level === "P1" ? "bad" : "warn"} /><b>{alertHeadline(a)}</b></span>
                  <small>{[zone, hm(a.first_ms)].filter(Boolean).join(" · ")}</small></td>
                <td>{owner ?? <span class="multi-none">{t("monUnassigned")}</span>}</td>
                <td>{r ? [nameOf(r.u.robot.robot_id), awayText(r.dist, "")].filter(Boolean).join(" · ") : <span class="warn-text">{t("multiNoRobot")}</span>}</td>
                <td>{video || "—"}</td>
                <td class="multi-act">
                  {a.key === lead
                    ? <button type="button" class="btn primary" onClick={() => props.onTake(a)}>{t("incTake")}</button>
                    : <button type="button" class="btn" onClick={() => props.onOpen(a)}>{t("multiOpen")}</button>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// 高级 → 地图(W44 第四期,设计 §5.3「地图」):什么时候用 —— 家具挪动很多,或者机器人老是迷路。
// 列出所有地图和版本、在用的是哪张、哪几台在用、发布(再输密码)、退回、对比、删、清噪点、编辑(mapmgmt.tsx,外审过的那一页);
// 上面加「重新建图」的步骤(不自动动机器人:第 2 步在手机上遥控)。
import { useState } from "preact/hooks";
import { t, type Key } from "./i18n";
import { MapManagePage } from "./mapmgmt";
import { useStored } from "./stored";

const STEPS: Key[] = ["rbStep1", "rbStep2", "rbStep3", "rbStep4", "rbStep5"];

export function AdvMapsPage({ say }: { say: (s: string) => void }) {
  // P2-18:做到第几步记在这台浏览器上,刷新不丢;展开过的再来还是展开
  const [done, setDone] = useStored<number>("nexwar.rebuild.done", 0, (v): v is number => Number.isInteger(v) && (v as number) >= 0 && (v as number) <= STEPS.length);
  const [open, setOpen] = useState(done > 0);
  return (
    <section class="advmaps">
      <h1>{t("tabMapMgmt")}</h1>
      <p class="muted lead">{t("mapsWhen")}</p>
      <section class="panel rebuild">
        <button type="button" class="linklike" aria-expanded={open} onClick={() => setOpen(!open)}>{t("rbTitle")} {open ? "▾" : "▸"}</button>
        {open && (
          <ol class="rb-steps">
            {STEPS.map((k, i) => (
              <li key={k} class={i < done ? "done" : i === done ? "now" : undefined}>
                <span>{t(k)}</span>
                {i === done && <button type="button" class="btn sm" onClick={() => setDone(i + 1)}>{t(i === STEPS.length - 1 ? "rbFinish" : "rbDone")}</button>}
              </li>
            ))}
          </ol>
        )}
        {open && done >= STEPS.length && (
          <div class="row wrap rb-finished" role="status">
            <span class="ok-text">{t("rbAllDone")}</span>
            <button type="button" class="btn sm" onClick={() => setDone(0)}>{t("rbRestart")}</button>
          </div>
        )}
        {open && done > 0 && done < STEPS.length && (
          <button type="button" class="linklike small" onClick={() => setDone(0)}>{t("rbRestart")}</button>
        )}
      </section>
      <MapManagePage say={say} />
    </section>
  );
}

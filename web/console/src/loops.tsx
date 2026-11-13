// W76 循环巡逻:派巡逻时选跑几圈(1、2、3、5、10)或「一直巡逻」(0 = 一直跑,电量到站点设的线就回去补能、
// 这一趟结束;日程到点会停下它改跑日程)。路线页、机器人页的「派巡逻」共用。
import { t } from "./i18n";

export const LOOP_CHOICES = [1, 2, 3, 5, 10, 0] as const;

export function loopsText(n: number): string {
  return n === 0 ? t("loopsForever") : t("loopsN", { n });
}

/** 正在跑第几圈(站点概览的 ``lap``):共几圈的写「第 2 / 3 圈」,一直巡逻写「一直巡逻 · 第 5 圈」。 */
export function lapText(lap: { n: number; of: number } | null | undefined): string {
  if (!lap) return "";
  return lap.of === 0 ? t("lapForever", { n: lap.n }) : t("lapOf", { n: lap.n, of: lap.of });
}

export function LoopsSelect({ value, onChange, id }: { value: number; onChange: (n: number) => void; id?: string }) {
  return (
    <select name="loops" id={id} value={String(value)} onChange={(e) => onChange(Number(e.currentTarget.value))}>
      {LOOP_CHOICES.map((n) => <option key={n} value={String(n)}>{loopsText(n)}</option>)}
    </select>
  );
}

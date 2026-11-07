// 没存的改动(网页易用性第 1 轮 P0-12):设置页、布防时间页、地图编辑器有没存的改动时,切到别的页面先问,
// 关标签页 / 刷新由浏览器问。各页面用 useUnsaved 报自己脏不脏,路由(console.tsx)换页前查 anyUnsaved。
import { useEffect } from "preact/hooks";

const dirty = new Set<string>();

function warn(e: Event) {
  e.preventDefault();
  (e as BeforeUnloadEvent).returnValue = "";
}

/** 这一页(``id``)现在有没有没存的改动。页面卸掉时自动算干净。 */
export function useUnsaved(id: string, isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) return;
    dirty.add(id);
    window.addEventListener("beforeunload", warn);
    return () => {
      dirty.delete(id);
      window.removeEventListener("beforeunload", warn);
    };
  }, [id, isDirty]);
}

export function anyUnsaved(): boolean {
  return dirty.size > 0;
}

/** 人说了「不存,离开」:全部算干净(页面马上要卸掉)。 */
export function dropUnsaved(): void {
  dirty.clear();
}

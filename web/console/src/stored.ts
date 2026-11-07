// 页面上的小偏好(筛选条件、开关)记在这台浏览器上,刷新不丢(网页易用性第 1 轮 P2-08/09/10)。
// 读写都包 try:隐私模式、存储被禁时照常用默认值。
import { useState } from "preact/hooks";

export function useStored<T>(key: string, init: T, ok: (v: unknown) => v is T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw != null) {
        const p: unknown = JSON.parse(raw);
        if (ok(p)) return p;
      }
    } catch { /* 用默认 */ }
    return init;
  });
  const set = (n: T) => {
    setV(n);
    try { localStorage.setItem(key, JSON.stringify(n)); } catch { /* 不记 */ }
  };
  return [v, set];
}

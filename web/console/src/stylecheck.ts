// 网页易用性第 2 轮(P0-18 残留):同一台电脑开很多会话时,样式表那条连接偶尔被站点关掉,
// 整页成了没有样式的 HTML。页面载完以后看一眼:哪张样式表没载上(sheet 是空的)就换个地址重新载,
// 最多 2 次;还不行在页面顶上说一句「刷新一下」。

const TRIES = 2;

/** 没载上的样式表(``loaded`` 默认看 ``link.sheet``;测试里换掉)。 */
export function failedSheets(doc: Document, loaded: (l: HTMLLinkElement) => boolean = (l) => !!l.sheet): HTMLLinkElement[] {
  return Array.from(doc.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')).filter((l) => !loaded(l));
}

/** 换个地址重新载这张样式表;回新的那个 ``<link>``。 */
export function reloadSheet(l: HTMLLinkElement, attempt: number): HTMLLinkElement {
  const n = l.cloneNode() as HTMLLinkElement;
  const u = new URL(l.href, l.ownerDocument.baseURI);
  u.searchParams.set("retry", String(attempt));
  n.href = u.pathname + u.search;
  l.replaceWith(n);
  return n;
}

function notice(doc: Document): void {
  if (doc.getElementById("style-failed")) return;
  const p = doc.createElement("p");
  p.id = "style-failed";
  p.setAttribute("role", "alert");
  // 样式表正是没载上的那张:用 CSSOM 直接设(CSP 只拦 HTML 里写的 style 属性,不拦脚本设的)
  p.style.cssText = "margin:0;padding:12px 16px;background:#B42318;color:#fff;font:16px/1.4 system-ui,sans-serif";
  p.textContent = (doc.documentElement.lang || "").startsWith("zh")
    ? "页面样式没有载入完整(站点忙或网络断了一下)。请刷新页面。"
    : "The page styles did not load fully (the site was busy or the network dropped). Please reload the page.";
  doc.body.prepend(p);
}

export function installStyleCheck(win: Window = window, attempt = 1): void {
  const doc = win.document;
  const check = () => {
    const bad = failedSheets(doc);
    if (bad.length === 0) return;
    if (attempt > TRIES) {
      notice(doc);
      return;
    }
    let left = bad.length;
    for (const l of bad) {
      const n = reloadSheet(l, attempt);
      const done = () => { if (--left === 0) installStyleCheck(win, attempt + 1); };
      n.addEventListener("load", done, { once: true });
      n.addEventListener("error", done, { once: true });
    }
  };
  if (doc.readyState === "complete") check();
  else win.addEventListener("load", check, { once: true });
}

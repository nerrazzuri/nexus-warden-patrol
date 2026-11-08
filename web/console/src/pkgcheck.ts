// 网页易用性 P1-77:选了升级包先在浏览器里看一眼(后缀、gzip 文件头),明显不对就当场说,不用先输密码。
// 第 2 轮:再解开看目录里有没有「顶层文件夹/release.json」(升级说明);没有就当场说不是升级包,
// 不先弹密码框(原来要先输密码,再在密码框里报错,人会以为是密码错了)。浏览器解不了就交给站点核。
import { t } from "./i18n";

export async function pkgProblem(f: File): Promise<string | null> {
  if (!/\.(tar\.gz|tgz)$/i.test(f.name)) return t("pkgNotTarGz");
  try {
    const b = new Uint8Array(await f.slice(0, 2).arrayBuffer());
    if (b.length < 2 || b[0] !== 0x1f || b[1] !== 0x8b) return t("pkgNotTarGz");
  } catch {
    return null;                  // 读不了就交给站点核
  }
  const has = await hasRelease(f);
  if (has === false) return t("pkgNoRelease");
  return null;
}

/** 包里有没有「顶层文件夹/release.json」:有 true、没有 false、解不了(浏览器不支持、坏包)null。 */
export async function hasRelease(f: Blob): Promise<boolean | null> {
  const DS = (globalThis as { DecompressionStream?: new (fmt: string) => TransformStream<Uint8Array, Uint8Array> }).DecompressionStream;
  if (!DS || typeof f.stream !== "function") return null;
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  try {
    reader = (f.stream() as ReadableStream<Uint8Array>).pipeThrough(new DS("gzip")).getReader();
    const tar = new TarScan();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const r = tar.push(value);
      if (r !== null) return r;
    }
    return tar.ended ? false : null;
  } catch {
    return null;
  } finally {
    try { await reader?.cancel(); } catch { /* 已经读完 */ }
  }
}

const dec = new TextDecoder();
const str = (b: Uint8Array) => { const z = b.indexOf(0); return dec.decode(z < 0 ? b : b.subarray(0, z)); };

/** 一块一块喂 tar 流,只看文件名(ustar 名字 + 前缀、GNU 长名 L、pax 的 path)。 */
class TarScan {
  private buf = new Uint8Array(0);
  private skip = 0;               // 还要跳过的数据字节(含补齐到 512)
  private grab: { kind: "L" | "x"; left: number; parts: Uint8Array[] } | null = null;
  private longName: string | null = null;
  ended = false;

  push(chunk: Uint8Array): boolean | null {
    const all = new Uint8Array(this.buf.length + chunk.length);
    all.set(this.buf);
    all.set(chunk, this.buf.length);
    let at = 0;
    while (at < all.length) {
      if (this.skip > 0) {
        const n = Math.min(this.skip, all.length - at);
        if (this.grab) {
          const take = Math.min(this.grab.left, n);
          this.grab.parts.push(all.subarray(at, at + take));
          this.grab.left -= take;
        }
        this.skip -= n;
        at += n;
        if (this.skip === 0 && this.grab) this.finishGrab();
        continue;
      }
      if (all.length - at < 512) break;
      const h = all.subarray(at, at + 512);
      at += 512;
      if (h.every((x) => x === 0)) { this.ended = true; return false; }
      const size = parseInt(str(h.subarray(124, 136)).trim() || "0", 8) || 0;
      const type = String.fromCharCode(h[156] || 48);
      const padded = Math.ceil(size / 512) * 512;
      if (type === "L" || type === "x") {
        this.grab = { kind: type, left: size, parts: [] };
        this.skip = padded;
        if (padded === 0) this.finishGrab();
        continue;
      }
      const prefix = str(h.subarray(345, 500));
      let name = str(h.subarray(0, 100));
      if (prefix) name = `${prefix}/${name}`;
      if (this.longName) { name = this.longName; this.longName = null; }
      if (isTopRelease(name)) return true;
      this.skip = padded;
    }
    this.buf = all.slice(at);
    return null;
  }

  private finishGrab(): void {
    const g = this.grab!;
    this.grab = null;
    const n = g.parts.reduce((a, p) => a + p.length, 0);
    const data = new Uint8Array(n);
    let o = 0;
    for (const p of g.parts) { data.set(p, o); o += p.length; }
    if (g.kind === "L") this.longName = str(data);
    else {
      const m = /(?:^|\n)\d+ path=([^\n]*)\n/.exec(dec.decode(data));
      if (m) this.longName = m[1];
    }
  }
}

/** 「某个顶层文件夹/release.json」(站点核的也是这个:目录第二层)。 */
function isTopRelease(name: string): boolean {
  const parts = name.replace(/^\.\//, "").split("/").filter(Boolean);
  return parts.length === 2 && parts[1] === "release.json";
}

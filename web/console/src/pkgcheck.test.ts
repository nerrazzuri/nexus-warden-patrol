// @vitest-environment happy-dom
import { beforeEach, expect, it } from "vitest";
import { lang } from "./i18n";
import { pkgProblem } from "./pkgcheck";

beforeEach(() => { lang.value = "zh"; });

it("网页易用性 P1-77:后缀、文件头不对当场说;对的不拦", async () => {
  expect(await pkgProblem(new File(["hello"], "notes.txt"))).toContain(".tar.gz");
  expect(await pkgProblem(new File(["hello"], "fake.tar.gz"))).toContain(".tar.gz");
  expect(await pkgProblem(new File([new Uint8Array([0x1f, 0x8b, 8, 0])], "r.tar.gz"))).toBeNull();
});

// 第 2 轮 P1-77:解开看有没有「顶层文件夹/release.json」,没有就当场说(不先要密码)
import { Blob as NodeBlob } from "node:buffer";
import { gzipSync } from "node:zlib";
import { hasRelease } from "./pkgcheck";

function tar(files: [string, string][]): Uint8Array {
  const blocks: Uint8Array[] = [];
  for (const [name, body] of files) {
    const h = new Uint8Array(512);
    h.set(new TextEncoder().encode(name).subarray(0, 100), 0);
    const data = new TextEncoder().encode(body);
    h.set(new TextEncoder().encode(data.length.toString(8).padStart(11, "0") + "\0"), 124);
    h[156] = 48;
    blocks.push(h);
    const d = new Uint8Array(Math.ceil(data.length / 512) * 512);
    d.set(data);
    blocks.push(d);
  }
  blocks.push(new Uint8Array(1024));
  const out = new Uint8Array(blocks.reduce((a, b) => a + b.length, 0));
  let o = 0;
  for (const b of blocks) { out.set(b, o); o += b.length; }
  return out;
}
const gz = (files: [string, string][]) => new NodeBlob([gzipSync(tar(files))]) as unknown as Blob;

it("第 2 轮 P1-77:有顶层文件夹/release.json 认;没有就说不是升级包", async () => {
  expect(await hasRelease(gz([["pkg-1/", ""], ["pkg-1/release.json", "{}"], ["pkg-1/a.whl", "x".repeat(3000)]]))).toBe(true);
  expect(await hasRelease(gz([["notes/readme.txt", "hi"], ["notes/b.txt", "x".repeat(600)]]))).toBe(false);
  expect(await hasRelease(gz([["release.json", "{}"]]))).toBe(false);          // 不在顶层文件夹里
  expect(await hasRelease(new NodeBlob([new Uint8Array([0x1f, 0x8b, 8, 0, 1, 2, 3])]) as unknown as Blob)).toBeNull();   // 坏包交给站点
});

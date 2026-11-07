// 网页易用性 P1-77:选了升级包先在浏览器里看一眼(后缀、gzip 文件头),明显不对就当场说,不用先输密码。
// 包里到底是站点包还是机器人包由站点核(它在核密码之前先看)。
import { t } from "./i18n";

export async function pkgProblem(f: File): Promise<string | null> {
  if (!/\.(tar\.gz|tgz)$/i.test(f.name)) return t("pkgNotTarGz");
  try {
    const b = new Uint8Array(await f.slice(0, 2).arrayBuffer());
    if (b.length < 2 || b[0] !== 0x1f || b[1] !== 0x8b) return t("pkgNotTarGz");
  } catch {
    return null;                  // 读不了就交给站点核
  }
  return null;
}

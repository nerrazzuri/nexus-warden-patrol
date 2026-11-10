// @vitest-environment happy-dom
// 第 5 轮 P1-01:系统页上露着的站点原文。
import { afterEach, describe, expect, it } from "vitest";
import { lang } from "./i18n";
import { siteText } from "./sitetext";

const EV = "机器人上没有站点的证据公钥(/etc/nexwar/evidence-pub.key):照片、截图、录像明文存在机器人上;人脸补拍不开(拍了也删)。从证书包拷过去、重启代理";
afterEach(() => { lang.value = "en"; });

describe("第 5 轮 P1-01", () => {
  for (const l of ["zh", "en"] as const) {
    it(`${l}:不露文件路径、「原文:」、「账号 xx」`, () => {
      lang.value = l;
      for (const src of [EV, "账号 wangxm", "把机器人开到原点前标原点;原文:起飞前检查未通过: home(地图没有原点)"]) {
        const v = siteText(src).text;
        expect(v).not.toContain("/etc/nexwar");
        expect(v).not.toContain("原文");
        expect(v).not.toMatch(/^账号 /);
        expect(v).not.toBe("");
        if (src === EV) expect(v).not.toContain("see details");
      }
    });
  }
});

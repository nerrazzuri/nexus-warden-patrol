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

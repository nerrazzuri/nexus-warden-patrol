// 网页易用性第 1 轮 P2-30:浏览器自带的「Please fill out this field」跟着浏览器语言走,不跟页面。
// 在捕获阶段接住 invalid,换成页面当前语言的说法;一改输入就清掉,让浏览器重新判断。
import { t } from "./i18n";

export function validityText(v: ValidityState): string {
  if (v.valueMissing) return t("vMissing");
  if (v.typeMismatch || v.patternMismatch || v.badInput) return t("vFormat");
  if (v.rangeUnderflow || v.rangeOverflow || v.stepMismatch) return t("vRange");
  if (v.tooLong || v.tooShort) return t("vLength");
  return "";
}

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

export function installValidity(doc: Document = document): void {
  doc.addEventListener("invalid", (e) => {
    const el = e.target as Field;
    if (!el || typeof el.setCustomValidity !== "function") return;
    el.setCustomValidity("");               // 先清掉,拿到浏览器自己的判断
    if (el.checkValidity()) return;
    el.setCustomValidity(validityText(el.validity));
  }, true);
  doc.addEventListener("input", (e) => {
    const el = e.target as Field;
    if (el && typeof el.setCustomValidity === "function") el.setCustomValidity("");
  }, true);
}

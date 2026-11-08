// 网页易用性第 2 轮 P1-01(复测 N1 / N3 / N5 / N8):英文界面不夹站点、机器人生成的中文原文。
// 站点能给英文的(体检项的 detail_en、报错的 reason_en)直接用;别的(机器人报的失败原因、站点拼的路线名、
// 版本备注、拒绝原因……)按下面的规则翻。认不出的那一段不显示中文,写「见详情」,原文放悬停 / 技术详情。
// 中文界面一律原样。
import { lang, t } from "./i18n";

const CJK = /[㐀-鿿]/;
/** 认不出的那一段先换成它,最后再换成英文的「见详情」。 */
const UNK = "\u0000";
const FALLBACK = "Site message in Chinese — see details";

/** 出发前检查的各项(狗上 engine/preflight.py 的名字)。 */
const PREFLIGHT: Record<string, string> = {
  home: "the map has no origin yet",
  localized: "localization is not settled",
  device_ready: "the robot is not ready (control or emergency stop)",
  nav_ready: "navigation is not ready",
  battery: "battery too low to start",
  storage: "robot storage is full",
  removable: "robot storage has a problem",
};

/** 路径规划失败的原因码(contract planning/astar.py 的 PlanError.reason)。 */
const PLAN: Record<string, string> = {
  goal_blocked: "no path — the destination is inside or too close to an obstacle or no-go area",
  start_blocked: "no path — the robot's own spot is blocked by an obstacle",
  outside: "the point is outside the map",
  no_path: "no path to the destination",
  timeout: "path planning took too long",
  worker: "the path planner failed",
};

const lc = (s: string): string => (s && /^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
const plural = (n: string, one: string, many: string): string => (n === "1" ? one : many);

function preflightList(s: string): string {
  const names = [...new Set([...s.matchAll(/([a-z_]+)[(（]/g)].map((m) => m[1]))];
  const known = names.map((n) => PREFLIGHT[n]).filter(Boolean);
  return known.length ? known.join("; ") : UNK;
}

type Rule = [RegExp, (m: RegExpMatchArray) => string];

const RULES: Rule[] = [
  // 机器人的巡逻失败原因(robot-agent tasks/patrol.py、engine/machine.py、导航桥)
  [/^跳过 (\d+) 个点[(（]([^)）]*)[)）][:：]\s*([\s\S]*)$/, (m) => `Skipped ${m[1]} ${plural(m[1], "point", "points")} (${m[2]}): ${lc(tr(m[3]))}`],
  [/^导航拒了[:：]\s*([\s\S]*)$/, (m) => `Navigation refused: ${lc(tr(m[1]))}`],
  [/^\w+ 被设备拒绝[:：]\s*([\s\S]*)$/, (m) => tr(m[1])],
  [/^重?规划失败[(（](\w+)[)）][\s\S]*$/, (m) => PLAN[m[1]] ?? `no path (${m[1]})`],
  [/^重规划失败[:：]\s*([\s\S]*)$/, (m) => `Re-planning failed: ${lc(tr(m[1]))}`],
  [/^起飞前检查未通过[:：]\s*([\s\S]*)$/, (m) => `Pre-departure check failed: ${preflightList(m[1])}`],
  [/^返航失败[:：]\s*未标原点[(（]返航起因[:：]\s*([\s\S]*)[)）]$/, (m) => `Could not return: the map has no origin (it was returning because: ${lc(tr(m[1]))})`],
  [/^电量\s*([\d.]+)%\s*低于中止线/, (m) => `Battery ${m[1]}% is below the turn-back level`],
  // 站点系统状态卡:「该做什么;原文:机器人原话」→ 只说该做什么
  [/^([\s\S]*?)[;；]原文[:：][\s\S]*$/, (m) => tr(m[1])],
  [/在这儿标原点/, () => "Localize the robot on this map, then press “Mark origin here” on the Localization page (or in the phone app)."],
  [/帮它重新定位/, () => "Help it find its position on the Localization page, then send it again."],
  [/急停是否按下/, () => "Check that the emergency stop is released and the site has control."],
  [/等一分钟再派/, () => "Wait a minute and send it again; if it stays like this, check navigation on the Diagnostics page."],
  [/先去充电或换电池/, () => "Charge it or swap the battery first."],
  [/到诊断页清理空间/, () => "Free up space on the Diagnostics page."],
  [/到诊断页看存储/, () => "Check storage on the Diagnostics page."],
  // 站点拼的名字、说明
  [/^临时路线 (\d+) 个点$/, (m) => `One-off route (${m[1]} ${plural(m[1], "point", "points")})`],
  [/^临时巡逻不进日程$/, () => "One-off patrol (not in the schedule)"],
  [/^新登记[:：]确认之前只许手动派$/, () => "Newly registered: manual dispatch only until confirmed"],
  [/^从 (\S+) 清了 (\d+) 处零星噪点[(（](\d+) 格[)）]$/, (m) => `Noise cleanup of version ${m[1]}: removed ${m[2]} specks (${m[3]} cells)`],
  [/^从 (\S+) 编辑[:：]擦了 ([\d.]+) 平方米、画了 ([\d.]+) 平方米障碍$/, (m) => `Edited from version ${m[1]}: erased ${m[2]} m², drew ${m[3]} m² of obstacles`],
  [/^(\S+) 离建图时走过的地方 ([\d.]+) m[(（]超过 ([\d.]+) m[)）][,，]那里定位不可靠[:：]先把那里建进图$/,
    (m) => `${m[1]} is ${m[2]} m from where the robot went while mapping (limit ${m[3]} m), so it cannot locate itself there reliably. Map that area first.`],
  [/^(\S+) 在图上不是可通行的地方/, (m) => `${m[1]} is not a walkable spot on the map (wall, obstacle or not scanned).`],
  // 特殊地面自动生成的限速区名字(site map_display.TERRAIN_LABEL)
  [/^(楼梯|台阶|斜坡|草地|碎石路)(\s*\d*)$/, (m) => ({ 楼梯: "Stairs", 台阶: "Steps", 斜坡: "Slope", 草地: "Grass", 碎石路: "Gravel path" } as Record<string, string>)[m[1]] + m[2]],
  [/^地图 '([^']+)' 未标原点/, (m) => `map “${m[1]}” has no origin yet`],
  // 站点的拒绝原因
  [/^(?:账号 )?(\S+) 已存在$/, (m) => `“${m[1]}” already exists.`],
  [/^账号 (\S+)$/, (m) => `Account ${m[1]}`],
  [/当前地图上还没有原点/, () => "This map has no origin yet. Stand the robot at the origin and press “Mark origin here” on the Localization page."],
  [/^(\S+) 没有默认待命点$/, (m) => `${m[1]} has no default standby point. Add one under Setup → Standby points.`],
  [/^此站点未安装 VPN/, () => "Remote engineer access (VPN) is not set up on this site, so engineers can only connect on the site's local network."],
  [/^清单里的文件名错误$/, () => "A file name in the package list is wrong."],
];

/** 一段原文 → 英文;认不出的段落换成 UNK。 */
function tr(s: string): string {
  const x = s.trim();
  if (!CJK.test(x)) return x;
  for (const [re, f] of RULES) {
    const m = x.match(re);
    if (m) return f(m);
  }
  return UNK;
}

export interface SiteText { text: string; raw?: string }

/** 站点 / 机器人生成的一段话按界面语言给出。英文界面认不出的部分不显示中文,``raw`` 是原文。 */
export function siteText(s: string | null | undefined): SiteText {
  const src = s ?? "";
  if (lang.value !== "en") return { text: src };
  return siteTextEn(src);
}

/** 不看界面语言,一律翻成英文(报错那边自己判断过语言)。 */
export function siteTextEn(src: string): SiteText {
  if (!CJK.test(src)) return { text: src };
  const out = tr(src);
  if (!out.includes(UNK)) return { text: out };
  return { text: out === UNK ? FALLBACK : out.split(UNK).join("see details"), raw: src };
}

/** 只要文字(悬停用不上的地方,比如 toast)。 */
export function siteStr(s: string | null | undefined): string {
  return siteText(s).text;
}

/** 人也可能写的(路线名、版本备注、区域名、手动派的说明):英文界面只翻认得的站点自动文字,
 *  认不得的原样(人写的中文不能被换成「见详情」)。 */
export function siteKnown(s: string | null | undefined): string {
  const src = s ?? "";
  if (lang.value !== "en" || !CJK.test(src)) return src;
  const out = tr(src);
  return out.includes(UNK) ? src : out;
}

/** 站点体检那一项的说明:英文界面用站点给的 detail_en,没有就翻。 */
export function checkText(c: { ok: boolean; detail?: string; detail_en?: string }): string {
  if (lang.value === "en") return c.detail_en || siteStr(c.detail);
  return c.detail ?? "";
}

/** 显示一段站点原文:英文界面翻不出的,原文放悬停。 */
export function SiteSpan({ s, class: cls }: { s: string | null | undefined; class?: string }) {
  const v = siteText(s);
  return <span class={cls} title={v.raw}>{v.text}</span>;
}

/** 处理人:站点自己关的(``site:xxx``)说「系统自动」,不露内部代码(复测 duty N3、admin N1)。 */
export function byText(by: string | null | undefined): string {
  if (!by) return "";
  return by.startsWith("site:") ? t("bySystem") : by;
}

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
  // 第 3 轮 admin N3:按每一项括号里的原因翻,不只看名字(battery 不一定是电量低:可能是没原点算不出出发线)
  const items = [...s.matchAll(/([a-z_]+)[(（]([^)）]*)[)）]?/g)];
  const seen = new Set<string>();
  const known: string[] = [];
  for (const [, n, why] of items) {
    if (seen.has(n)) continue;
    seen.add(n);
    const txt = n === "battery" && /原点|出发线/.test(why ?? "") && !/低于/.test(why ?? "")
      ? "the turn-back battery level cannot be worked out (the map has no usable origin)" : PREFLIGHT[n];
    if (txt) known.push(txt);
  }
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
  // 防区自动选点、路线落点检查(site guard_plan.py、routes.py)
  [/^这个点在地图外面$/, () => "the point is outside the map"],
  [/^这个点在墙、障碍、禁行区里/, () => "the point is in or too close to a wall, obstacle or no-go area (no room for the robot)"],
  [/^这个点不在地图上最大的那片可走区域里/, () => "the point is not in the main walkable area of the map (no standby point set yet)"],
  [/^这个点从待命点、原点走不到$/, () => "the robot cannot get to the point from its standby point or the origin"],
  [/^这张地图还不能自动选点/, () => "this map cannot pick points automatically yet; click the route points on the map yourself"],
  [/^防区里没有机器人站得下的地方$/, () => "there is no spot in the zone where the robot fits (the zone may be outside the scanned area)"],
  [/^机器人走不到这个防区[:：]还没设待命点/, () => "the robot cannot reach this zone because no standby point is set. Set one under Standby points, or draw the zone where the robot can go"],
  [/^机器人从待命点、原点都走不到这个防区里/, () => "the robot cannot reach this zone from its standby point or the origin; draw the zone where the robot can go"],
  [/^防区里站得下的地方离建图时走过的路都太远/, () => "every spot in the zone is too far from where the robot went while mapping (it would not locate itself reliably)"],
  [/^(\S+) 到 (\S+) 走不通[(（]被墙或禁行区隔开[)）]$/, (m) => `No way from ${m[1]} to ${m[2]} (a wall or no-go area is in between)`],
  [/^点要有数字的 x、y/, () => "each point needs numeric x and y (and optionally yaw)"],
  [/^摄像头 (\S+)[(（]防区 ([^)）]*)[)）]连不上,这一路的入侵现在收不到[;；]看看摄像头的电源和网线$/,
    (m) => `Camera ${m[1]} (zone ${m[2]}) cannot be reached, so intrusions from it are not received now. Check its power and network cable.`],
  // 第 4 轮 r2-duty-N7:点位没到 —— 跳过一次只记一笔、连续几趟才报 P1,两种分开说
  [/^点位 (\S+) 连续 (\d+) 趟未到达[:：]路可能被堵住了$/, (m) => `Waypoint ${m[1]} not reached ${m[2]} runs in a row: the way may be blocked`],
  [/^点位 (\S+) 未到达,已跳过$/, (m) => `Waypoint ${m[1]} not reached, skipped`],
  [/^([\s\S]*?)[;；]?巡逻继续,只做记录$/, (m) => `${m[1] ? `${tr(m[1])}. ` : ""}The patrol went on; this is only a record.`],
  [/^([\s\S]*?)[;；]?到达一次后自动解除$/, (m) => `${m[1] ? `${trParts(m[1])}. ` : ""}Clears itself once the point is reached.`],
  [/^到场看看,或者改路线$/, () => "Go and look, or change the route"],
  [/^第 (\d+) 个点[:：]\s*([\s\S]*)$/, (m) => `Point ${m[1]}: ${tr(m[2])}`],
  [/^(\S+) 从现在的位置走不到这个点/, (m) => `${m[1]} cannot get to this point from where it is now (a wall or no-go area is in between)`],
  // 第 3 轮 admin N4:诊断页、活动日志、报警里常见的几句
  [/^(?:站点盘)?(?:还|只)?剩\s*([\d.]+)\s*(GB|MB|%)$/, (m) => `${m[1]}${m[2] === "%" ? "%" : ` ${m[2]}`} free`],
  [/^没有登记过 (\S+)$/, (m) => `${m[1]} is not registered on this site`],
  [/^摄像头 (\S+) 无法连接[(（]防区 ([^)）]+)[)）]$/, (m) => `Camera ${m[1]} cannot be reached (zone ${m[2]})`],
  [/^(\S+) 无法连接[:：]/, (m) => `${m[1]} cannot be reached`],
  // 站点的拒绝原因
  [/^(?:账号 )?(\S+) 已存在$/, (m) => `“${m[1]}” already exists.`],
  [/^账号 (\S+)$/, (m) => `Account ${m[1]}`],
  [/当前地图上还没有原点/, () => "This map has no origin yet. Stand the robot at the origin and press “Mark origin here” on the Localization page."],
  [/^(\S+) 没有默认待命点$/, (m) => `${m[1]} has no default standby point. Add one under Setup → Standby points.`],
  [/^此站点未安装 VPN/, () => "Remote engineer access (VPN) is not set up on this site, so engineers can only connect on the site's local network."],
  [/^清单里的文件名错误$/, () => "A file name in the package list is wrong."],
  // 第 4 轮 admin P1-01:活动日志里还是兜底文字的三类
  [/^(\S+) 已登记且未吊销/, (m) => `${m[1]} already exists. Unbind it first to add it again.`],
  // 第 4 轮 P1-77:升级包被拒的几种原因(原来翻成通用句「Check what you entered」,人又回去查密码)
  [/^升级包的签名不匹配/, () => "The package's signature does not match: it was not released by us. Ask us for the correct upgrade file."],
  [/^升级包已损坏/, () => "The package is damaged (its files do not match its list). Download it again."],
  [/^此版本已存在/, () => "This version is already on the site."],
  [/^(\d+) 处不能用$/, (m) => `${m[1]} point${m[1] === "1" ? "" : "s"} cannot be used`],
  [/^(\S+) 的钟差未知/, (m) => `${m[1]} has not reported its clock recently (just connected, or no telemetry in the last minute). Wait a moment and try again.`],
  [/^(\S+) 的钟差 ([+-]?\d+) 秒/, (m) => `${m[1]}'s clock is ${m[2]} s off from the site. Sync its time with the site host first.`],
];

/** 一段原文 → 英文;认不出的段落换成 UNK。 */
/** 「原因;建议」两段分开翻(各自认得的才翻)。 */
function trParts(s: string): string {
  return s.split(/[;；]/).map((p) => tr(p)).join(". ");
}

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
/** 第 3 轮 zh N9:站点、机器人给的中文多用半角「( , : ;」;中文界面显示时挨着汉字的换成全角
 *  (时间 10:30、地址 http://、地图 home:3 这类两边不是汉字的不动)。 */
export function zhPunct(src: string): string {
  if (!CJK.test(src)) return src;
  const H = "[\\u3400-\\u9fff「」（）]";
  return src
    .replace(new RegExp(`(${H}) ?\\(`, "g"), "$1（").replace(new RegExp(`\\((?=${H})`, "g"), "（")
    .replace(/（([^()（）]*)\)/g, "（$1）")
    .replace(new RegExp(`(${H}|）),\\s?`, "g"), "$1，")
    .replace(new RegExp(`(${H}|）):\\s?(?!//)`, "g"), "$1：")
    .replace(new RegExp(`(${H}|）);\\s?`, "g"), "$1；");
}

export function siteText(s: string | null | undefined): SiteText {
  const src = s ?? "";
  if (lang.value !== "en") return { text: zhPunct(src) };
  return siteTextEn(src);
}

/** 不看界面语言,一律翻成英文(报错那边自己判断过语言)。 */
export function siteTextEn(src: string): SiteText {
  if (!CJK.test(src)) return { text: src };
  const out = tr(src);
  if (!out.includes(UNK)) return { text: out };
  return { text: out === UNK ? FALLBACK : out.split(UNK).join("see details"), raw: src };
}

/** 只要文字(悬停用不上的地方,比如 toast、活动日志)。第 3 轮 admin N4:这里没有悬停,不写「see details」
 *  (点不开,是死路),写清是中文原文、换成中文界面能看。 */
export function siteStr(s: string | null | undefined): string {
  const v = siteText(s);
  if (!v.raw) return v.text;
  return v.text === FALLBACK ? NO_HOVER : v.text.split("see details").join("(in Chinese)");
}
const NO_HOVER = "Site message in Chinese (switch the language to 中文 to read it)";

/** 人也可能写的(路线名、版本备注、区域名、手动派的说明):英文界面只翻认得的站点自动文字,
 *  认不得的原样(人写的中文不能被换成「见详情」)。 */
export function siteKnown(s: string | null | undefined): string {
  const src = s ?? "";
  if (lang.value !== "en") return zhPunct(src);
  if (!CJK.test(src)) return src;
  const out = tr(src);
  return out.includes(UNK) ? src : out;
}

/** 站点体检那一项的说明:英文界面用站点给的 detail_en,没有就翻。 */
export function checkText(c: { ok: boolean; detail?: string; detail_en?: string }): string {
  if (lang.value === "en") return c.detail_en || siteStr(c.detail);
  return zhPunct(zhPlain(c.detail ?? ""));
}

/** 第 3 轮 zh N10 / N11:体检说明里的开发者口吻、内部名字换成人话(站点原文给手机 App、测试用,不改)。 */
const KEY_NAME: Record<string, string> = { secrets: "密码加密密钥", backup: "备份加密密钥", evidence: "证据加密密钥" };
const PLAIN: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^库能写$/, () => "数据库正常"],
  [/^库无法写入[:：](.*)$/, (m) => `数据库写不进去：${m[1]}`],
  [/^事件循环 ([\d.]+) 秒前转过[:：]卡住$/, (m) => `站点程序卡住了（${m[1]} 秒没响应）`],
  [/^事件循环 ([\d.]+) 秒前转过$/, () => "站点程序运行正常"],
  [/^后台道都在转$/, () => "后台任务都在运行"],
  [/^卡住[:：](.*)$/, (m) => `后台任务卡住：${m[1]}`],
  [/^证书最近的还有 (\d+) 天到期$/, (m) => `证书有效，最早的还有 ${m[1]} 天到期`],
  [/^连着 MQTT$/, () => "机器人通信正常"],
  [/^MQTT 已断开$/, () => "机器人通信断了"],
  [/^未配置推送[(（]site\.json 的 push[)）]$/, () => "还没设置手机推送"],
  [/^未接入[(（]命令行[)）]$/, () => "这里查不了"],
];
export function zhPlain(src: string): string {
  for (const [re, f] of PLAIN) {
    const m = src.match(re);
    if (m) return f(m);
  }
  // 「secrets:没有这把密钥;backup:…」:密钥名换成人话
  if (/^(secrets|backup|evidence):/.test(src)) {
    return src.split(";").map((x) => x.replace(/^(secrets|backup|evidence):/, (_, k: string) => `${KEY_NAME[k]}：`)).join("；");
  }
  return src;
}

/** 显示一段站点原文:英文界面翻不出的,原文放悬停。 */
export function SiteSpan({ s, class: cls }: { s: string | null | undefined; class?: string }) {
  const v = siteText(s);
  return <span class={cls} title={v.raw}>{v.text}</span>;
}

/** 处理人:站点自己关的(``site:xxx``)说「系统自动」,不露内部代码(复测 duty N3、admin N1)。 */
export function byText(by: string | null | undefined): string {
  if (!by) return "";
  // 第 4 轮 admin P1-01:「站点:…」开头的也是系统自动处理
  return /^(site|站点)[:：]/.test(by) ? t("bySystem") : by;
}

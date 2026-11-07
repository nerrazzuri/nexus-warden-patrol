// 网页易用性第 1 轮 P1-01:英文界面不夹站点的中文原话。站点回的错是中文时,按常见的几种翻成英文;
// 认不出的按错误类型说一句英文,后面括号里带站点原话(里面常有该怎么办,丢了反而更难办)。
// 站点带了 reason_en / reason=forbidden 的,api.ts 先用那个。
const CJK = /[㐀-鿿]/;

/** 有西文细节(机器人回的英文原因)就接在后面;是中文就不接。 */
const tail = (s: string | undefined): string => (s && !CJK.test(s) ? `: ${s.trim()}` : "");

const PATTERNS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/已被修改|已经被改过|已经被别人改|请刷新/, () => "Someone else changed this first. Reload the page and try again."],
  [/密码不对|口令不对|密码错误|密码不正确/, () => "Wrong password."],
  [/未安装特权执行器/, () => "This needs the site's system helper, which is not installed. Do it on the site computer, or ask your installer."],
  [/没登录|请先登录|登录已过期/, () => "Please sign in again."],
  [/还有机器人在用[(（]([^)）]*)[)）]/, (m) => `Robots are still using this map version (${m[1]}). Move them to another version first.`],
  [/要人现场监护/, () => "This robot needs someone supervising on site. Turn on supervision in the phone app first."],
  [/地址里不要带账号口令/, () => "Don't put the account or password in the address. Use the Account and Password fields."],
  [/在你看过之后换了|你看到的是第/, () => "This changed after you opened it. Reload the page and try again."],
  [/禁行区尚未确认/, () => "The no-go areas on this map are not confirmed yet. Confirm them under Setup → No-go areas."],
  [/没有能派的机器人/, () => "No robot on this map can be sent right now."],
  [/机器人不存在|没有登记过/, () => "That robot is not registered on this site."],
  [/摄像头不存在/, () => "That camera does not exist."],
  [/不在线/, () => "The robot is offline."],
  [/不能自动找位置/, () => "This robot cannot find its position by itself (it needs newer robot software)."],
  [/没有任务在跑/, () => "This robot has no task running."],
  [/不在这一条的授权时间里/, () => "This is outside the authorised time of the rule."],
  [/此版本已存在/, () => "This version already exists."],
  [/升级包(过|太)大/, () => "The package is too large (max 500 MB)."],
  [/底图最大/, () => "The image is too large (max 8 MB)."],
  [/未收到文件|文件未传完/, () => "The file did not upload completely. Try again."],
  [/处不能用/, () => "Some points cannot be used. See the marked points."],
  [/名字只许|路线名只许/, () => "Names may only use letters, digits and . _ -"],
  [/机器人未执行[:：]\s*(.*)$/, (m) => `The robot did not do it${tail(m[1])}.`],
  [/机器人未检查[:：]\s*(.*)$/, (m) => `The robot did not run the check${tail(m[1])}.`],
  [/机器人没换姿势[:：]\s*(.*)$/, (m) => `The robot did not change posture${tail(m[1])}.`],
  [/机器人未提供[:：]\s*(.*)$/, (m) => `The robot did not provide it${tail(m[1])}.`],
  [/机器人标记失败[:：]\s*(.*)$/, (m) => `The robot could not mark it${tail(m[1])}.`],
  [/一分钟内报得太多/, () => "Too many reports in one minute; the extra ones were dropped."],
  [/此站点未(启用|接入|配置)/, () => "This feature is not set up on this site."],
  [/只支持|只收 |此接口只能|此接口不能/, () => "This action is not available here."],
];

const BY_STATUS: Record<number, string> = {
  400: "The site could not accept this. Check what you entered.",
  403: "Your account is not allowed to do this.",
  404: "Not found on the site.",
  409: "The site refused this right now.",
  413: "This is too large.",
  429: "Too many requests. Wait a moment and try again.",
};

/** 英文界面:站点的中文错误原话 → 英文。不是中文的原样返回。 */
export function englishError(status: number, msg: string): string {
  if (!CJK.test(msg)) return msg;
  for (const [re, f] of PATTERNS) {
    const m = msg.match(re);
    if (m) return f(m);
  }
  const base = status >= 500 ? "The site hit an error. Try again; if it keeps happening, download a support bundle under Diagnostics."
    : BY_STATUS[status] ?? "The site refused this.";
  return `${base} (site message: ${msg})`;
}

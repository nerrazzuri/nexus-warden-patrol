// 网页易用性第 2 轮 P1-01(N1 / N3 / N5 / N8):英文界面不夹站点、机器人生成的中文原文。
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { lang } from "./i18n";
import { checkText, siteKnown, siteStr, siteText } from "./sitetext";

const CJK = /[㐀-鿿]/;
beforeEach(() => { lang.value = "en"; });
afterEach(() => { lang.value = "zh"; });

describe("站点原文翻成英文", () => {
  it("巡逻跳点 + 导航被拒 + 规划失败(goal_blocked):整句都是英文", () => {
    const s = siteText("跳过 1 个点(P2):导航拒了: goto 被设备拒绝: 规划失败(goal_blocked):终点在障碍、禁行区里或贴得太近");
    expect(s.text).toBe("Skipped 1 point (P2): navigation refused: no path — the destination is inside or too close to an obstacle or no-go area");
    expect(s.raw).toBeUndefined();
  });

  it("临时路线名、临时巡逻、账号、新登记、版本备注", () => {
    expect(siteText("临时路线 2 个点").text).toBe("One-off route (2 points)");
    expect(siteText("临时巡逻不进日程").text).toBe("One-off patrol (not in the schedule)");
    expect(siteText("账号 wangxm").text).toBe("Account wangxm");
    expect(siteText("新登记:确认之前只许手动派").text).toBe("Newly registered: manual dispatch only until confirmed");
    expect(siteText("从 9 编辑:擦了 0.09 平方米、画了 0 平方米障碍").text).toBe("Edited from version 9: erased 0.09 m², drew 0 m² of obstacles");
  });

  it("起飞前检查:按检查项说人话", () => {
    expect(siteText("起飞前检查未通过: home(地图 'estate-1' 未标原点,先去标一个换电位); battery(算不出)").text)
      .toBe("Pre-departure check failed: the map has no origin yet; battery too low to start");
  });

  it("第 3 轮 admin N3:battery 那一项按原因翻:没原点算不出出发线 ≠ 电量低", () => {
    expect(siteText("起飞前检查未通过: home(地图 'm' 未标原点); battery(电量 98.8%,但算不出出发线:此地图的原点不可用)").text)
      .toBe("Pre-departure check failed: the map has no origin yet; the turn-back battery level cannot be worked out (the map has no usable origin)");
    expect(siteText("起飞前检查未通过: battery(电量 12% 低于出发线 30%)").text).toBe("Pre-departure check failed: battery too low to start");
  });

  it("系统状态卡:「该做什么;原文:…」只留该做什么", () => {
    const s = siteText("让机器人在这张地图上定好位,在手机或网页的定位页点「在这儿标原点」;原文:起飞前检查未通过: home(x)");
    expect(s.text).not.toMatch(CJK);
    expect(s.text).toContain("Mark origin here");
  });

  it("落点检查、回家、待命点、账号已存在、VPN、清单", () => {
    expect(siteText("P3 离建图时走过的地方 7.3 m(超过 5 m),那里定位不可靠:先把那里建进图").text)
      .toBe("P3 is 7.3 m from where the robot went while mapping (limit 5 m), so it cannot locate itself there reliably. Map that area first.");
    expect(siteText("当前地图上还没有原点:在原点位置点“设为原点”").text).toMatch(/no origin/);
    expect(siteText("A 没有默认待命点").text).toBe("A has no default standby point. Add one under Setup → Standby points.");
    expect(siteText("账号 gina 已存在").text).toBe("“gina” already exists.");
    expect(siteText("此站点未安装 VPN(nexwar_site vpn init),工程师只能在现场局域网里连").text).not.toMatch(/nexwar_site|CJK/);
    expect(siteText("清单里的文件名错误").text).toBe("A file name in the package list is wrong.");
  });

  it("认不出的:不显示中文,换一句英文,原文留着(悬停 / 技术详情看)", () => {
    const s = siteText("某个没见过的中文原因");
    expect(s.text).not.toMatch(CJK);
    expect(s.raw).toBe("某个没见过的中文原因");
  });

  it("中文界面原样;本来就是英文的原样", () => {
    expect(siteText("Battery 12%").text).toBe("Battery 12%");
    lang.value = "zh";
    expect(siteText("临时路线 2 个点").text).toBe("临时路线 2 个点");
  });

  it("体检项:英文界面用站点给的英文说明,没有就翻", () => {
    expect(checkText({ ok: true, detail: "库能写", detail_en: "Database is writable" })).toBe("Database is writable");
    expect(checkText({ ok: true, detail: "账号 x" })).toBe("Account x");
    lang.value = "zh";
    expect(checkText({ ok: true, detail: "库能写", detail_en: "Database is writable" })).toBe("数据库正常");
  });
});

describe("人也可能写的字段(siteKnown)", () => {
  it("认得的站点自动文字翻;人写的中文原样,不换成「见详情」", () => {
    expect(siteKnown("临时路线 3 个点")).toBe("One-off route (3 points)");
    expect(siteKnown("斜坡")).toBe("Slope");
    expect(siteKnown("东区巡逻")).toBe("东区巡逻");
  });
});

describe("清噪点的版本备注", () => {
  it("翻成英文", () => {
    expect(siteKnown("从 7 清了 332 处零星噪点(746 格)")).toBe("Noise cleanup of version 7: removed 332 specks (746 cells)");
  });
});

describe("第 3 轮 admin N4", () => {
  it("常见几句翻出来;没悬停的地方不写 see details", () => {
    expect(siteText("剩 64 GB").text).toBe("64 GB free");
    expect(siteText("没有登记过 T31").text).toBe("T31 is not registered on this site");
    expect(siteText("摄像头 gate 无法连接(防区 北区)").text).toBe("Camera gate cannot be reached (zone 北区)");
    expect(siteStr("某个没见过的中文原因")).not.toMatch(/see details/);
    expect(siteText("某个没见过的中文原因").text).toMatch(/see details/);
  });
});

describe("第 3 轮 zh N9", () => {
  it("中文界面:挨着汉字的半角标点换全角;时间、地址、地图号不动", async () => {
    const { zhPunct } = await import("./sitetext");
    expect(zhPunct("未配置备份:站点主机损坏将导致数据丢失")).toBe("未配置备份：站点主机损坏将导致数据丢失");
    expect(zhPunct("新登记:确认之前只许手动派")).toBe("新登记：确认之前只许手动派");
    expect(zhPunct("区域 0 (0 禁行, 0 限速)")).toBe("区域 0 (0 禁行，0 限速)");
    expect(zhPunct("不能派(地图 home:3 没确认),10:30 再试")).toBe("不能派（地图 home:3 没确认），10:30 再试");
    expect(zhPunct("见 http://a.b")).toBe("见 http://a.b");
    expect(zhPunct("Battery 12%")).toBe("Battery 12%");
  });
});

describe("第 3 轮 zh N10 / N11 体检说人话", () => {
  it("开发者口吻、密钥名换掉", async () => {
    const { checkText } = await import("./sitetext");
    lang.value = "zh";
    expect(checkText({ ok: true, detail: "库能写" })).toBe("数据库正常");
    expect(checkText({ ok: true, detail: "事件循环 0.6 秒前转过" })).toBe("站点程序运行正常");
    expect(checkText({ ok: true, detail: "后台道都在转" })).toBe("后台任务都在运行");
    expect(checkText({ ok: false, detail: "secrets:没有这把密钥;backup:权限太宽" })).toBe("密码加密密钥：没有这把密钥；备份加密密钥：权限太宽");
    expect(checkText({ ok: false, detail: "未配置推送(site.json 的 push)" })).toBe("还没设置手机推送");
  });
});

describe("第 4 轮 P1-77 升级包被拒", () => {
  it("签名不对、损坏、已存在各说各的", () => {
    expect(siteText("升级包的签名不匹配,不是公司发的(x:签名错误)").text).toMatch(/signature does not match/);
    expect(siteText("升级包已损坏(文件与清单不匹配)").text).toMatch(/damaged/);
    expect(siteText("此版本已存在").text).toBe("This version is already on the site.");
  });
});

describe("第 4 轮 r3-duty-N3 派单时站点拒", () => {
  it("第 1 个点走不到", () => {
    expect(siteText("第 1 个点:B 从现在的位置走不到这个点(被墙或禁行区隔开)").text)
      .toBe("Point 1: B cannot get to this point from where it is now (a wall or no-go area is in between)");
  });
});

describe("第 4 轮 r3-duty-N7 摄像头掉线详情", () => {
  it("写摄像头名、防区、怎么办", () => {
    expect(siteText("摄像头 gate(防区 东区)连不上,这一路的入侵现在收不到;看看摄像头的电源和网线").text)
      .toBe("Camera gate (zone 东区) cannot be reached, so intrusions from it are not received now. Check its power and network cable.");
  });
});

describe("第 4 轮 r2-duty-N7 点位没到", () => {
  it("跳过一次和连续几趟分开说;详情翻出建议", async () => {
    const { alertTitle } = await import("./i18n");
    expect(alertTitle("en", "stuck", "点位 P2 连续 3 趟未到达:路可能被堵住了")).toBe("Waypoint P2 not reached 3 runs in a row");
    expect(alertTitle("en", "stuck", "点位 P2 未到达,已跳过")).toBe("Waypoint P2 skipped");
    expect(siteText("到场看看,或者改路线;到达一次后自动解除").text).toBe("Go and look, or change the route. Clears itself once the point is reached.");
    expect(siteText("巡逻继续,只做记录").text).toBe("The patrol went on; this is only a record.");
  });
});

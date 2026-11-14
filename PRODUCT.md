# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Guard (保安, role `guard`)**: on shift in a guard room, often at night under low light, watching for a long time. Job: notice alarms, decide and act fast (take over, dispatch a robot, stop all), watch live video and the map, hand over to the next shift.
- **Manager / owner (经理, `manager`)**: daytime, office light. Job: set up zones, patrol routes, arming schedules, access grants; read reports.
- **Admin (管理员, `admin`)** and site engineer: robots, users, maps, localization, diagnostics, upgrades, system.
- **Viewer (只读)**: reads only.
- Self-service customers: the console must teach itself; no trainer on site.

## Product Purpose
Nexus Warden is the site console for D1 Max legged security robots that patrol an estate or facility. The web console is where the site runs its security operation: robots patrol, detect people/events, raise alarms; people respond. Success: a guard never misses or misreads a P1, and an admin can configure a site without an engineer.

## Positioning
One console for a fleet of autonomous patrol robots: live video from every robot, alarm handling with escalation, and the full site setup (map, zones, routes, schedules) in the same place. Runs offline on the site's own server.

## Operating Context
- Guard pages: 总览 (duty overview), 实况 (live video wall), 地图, 报警记录, 录像. Admin pages: 机器人, 布置 (zones, no-go, guard, routes, road net, standby, cameras), 布防时间, 授权和临时撤防, 用户, 报表, 活动日志, 系统状态, and advanced (地图管理, 定位, 诊断, 升级, 系统).
- Desktop browsers 1024–1920 wide; also usable on tablets and phones (touch).
- Chinese first, English available. Shift handover note between guards.
- A phone app (Flutter) serves the same users; until 2026-11-14 web and phone shared `design/mobile.json` (decision 64). On branch `redesign/console-v2` the user allowed the web look to diverge (experiment, to be compared).

## Capabilities and Constraints
- Preact + plain CSS, Vite build into the site package; site CSP `style-src 'self'`, no inline styles/scripts; must run fully offline (self-hosted fonts only, no CDN).
- Colour meaning is fixed (user decision 2026-10-14): red only for P1, e-stop, offline, destructive actions; orange only for P2 and low battery; green for normal; brand blue only for selection, focus, primary action. Priority is always colour + shape + text; only unacknowledged P1 flashes.
- Say 机器人 / robot, never 狗 / dog.
- E-stop (全部叫停) always reachable from every page.
- Redesign scope allowed on this branch (user 2026-11-14): look, page layout and structure may change; functions, API and behaviour stay; existing tests must pass (update a test only where the structure it pins was deliberately changed).

## Brand Commitments
- Name: NEXUS WARDEN. "Professional, not pretty" (user, 2026-10-11).
- Must not feel like: a consumer app (rounded, decorative, lots of motion); a developer tool (mono-heavy, terminal feel); and must not show less information per screen than today.
- Guard pages dark (night guard room); admin pages may be light (daytime office) — user 2026-11-14, matching the original W44 intent.

## Evidence on Hand
- Live site with simulated robots: https://192.168.5.12:8520 (accounts demo / gina / olga / vic).
- Read-only UI/UX audit 2026-11-14: `wt-webux/audit/uiux/` (27 issues, CONSOLIDATED_ISSUES.json; 250 screenshots).
- No customer testimonials, benchmarks or prices; do not invent any.

## Product Principles
1. The alarm wins: a P1 is the most visible thing on any screen it appears on, and acting on it is one step away.
2. Density is a feature: operators scan; never trade information for whitespace.
3. One fact, one wording, one number, everywhere.
4. Calm by default: colour and motion are reserved for state, so state is never ambiguous.
5. Self-explaining: every disabled control says why; every setting says what it does.

## Accessibility & Inclusion
WCAG 2.2 AA: text contrast ≥ 4.5:1, focus visible and returned after dialogs, visible labels, keyboard reachable, reduced motion honoured; touch targets ≥ 44px under coarse pointers.

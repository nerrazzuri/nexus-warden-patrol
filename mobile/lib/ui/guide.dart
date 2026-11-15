/// 上手向导（W53 §8，用户 2026-10-31：只买设备、没买交付服务的客户要能自己学会用）。
///
/// - **上手导览**：这个账号没看过当前版本（站点记在账号上，换手机不用再看），进了值守页就开始。在真页面上
///   挡一层半透明、圈出一块，旁边一两句，「下一步」往下走，随时「跳过」。按角色各一套。
/// - **报警练习**（保安、能处理报警的）：导览最后弹一条「演练」报警，照着点 去处理 → 我来处理 → 误报。
///   **只在 App 里模拟**：不发给站点、不进报警记录、别人看不到（设计 D11）。
/// - **常见问题**：按角色挑几条，每条三四句话。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_button.dart';
import 'nw/nw_p2_duty.dart';
import 'nw/nw_p4_admin.dart' show nwGap8, NwListView;
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'site_duty_page.dart';

/// 导览的版本：内容大改了加一，大家再看一遍。
const int kTourVersion = 1;

const Key tourCardKey = Key('tour-card');
const Key tourNextKey = Key('tour-next');
const Key tourSkipKey = Key('tour-skip');

class TourStep {
  final GlobalKey? target;
  final String title;
  final String body;
  const TourStep(this.target, this.title, this.body);
}

/// 按角色的导览步骤（值守页上圈的那几块）。
List<TourStep> tourSteps(String role, DutyTargets t) {
  final mode = TourStep(
      t.mode,
      tr('Arming and weather', '布防和天气'),
      role == 'guard'
          ? tr('Arming status and weather. You can switch to Armed; disarming is done by the manager.',
              '布防状态与天气。可切换为「布防」；撤防需经理操作。')
          : tr('Whether the site is armed, and the weather. Tap Change to arm or disarm (disarming asks you to confirm).',
              '布防状态和天气。点「切换」布防、撤防（撤防要确认）。'));
  final robots = TourStep(t.chips, tr('Robots', '机器人'),
      tr('Your robots: tap a name to switch, or swipe on the video.', '机器人列表：点名称切换，或在画面上左右滑动。'));
  final video = TourStep(t.video, tr('Live video', '实时画面'),
      tr('Tap ▶ to watch live; tap ✕ to stop (saves data on 4G).', '点 ▶ 查看实时画面，✕ 关闭（使用 4G 时可节省流量）。'));
  final status = TourStep(t.status, tr('Current status', '当前状态'),
      tr('Current task, estimated finish time and battery.', '显示当前任务、预计完成时间和电量。'));
  final today = TourStep(t.today, tr("Today's patrols", '今天的巡逻'),
      tr('All patrols today. Tap an unfinished one to see why.',
          '今日全部巡逻。点开未完成项可查看原因。'));
  return switch (role) {
    'guard' => [
        mode,
        robots,
        video,
        status,
        TourStep(t.actions, tr('Patrol, drive, stop', '派巡逻、遥控、叫停'),
            tr('Patrol: pick a route; if it clashes with the schedule it runs afterwards and the manager is notified. Drive: manual control. Stop: the robot stops where it is.',
                '派巡逻：选择路线，与日程冲突时排在日程之后并通知经理。遥控：手动控制。叫停：机器人原地停止。')),
        today,
        TourStep(null, tr('When an alarm comes in', '有报警的时候'),
            tr('A P1 alarm rings and shows a red bar at the top; tap Respond. Start a practice run below.',
                'P1 报警会响铃并在顶部显示红条，点「去处理」进入。下面进行一次演练。')),
      ],
    'owner' => [
        mode,
        robots,
        TourStep(t.actions, tr('Patrol and stop', '派巡逻、叫停'),
            tr('Send a one-off patrol, or stop a robot right away.', '临时派一趟巡逻，或者马上叫停。')),
        today,
        TourStep(null, tr('Schedule', '日程'),
            tr('Schedule tab: when each route runs and on which robot.', '「日程」页：各路线的执行时间和机器人。')),
      ],
    'viewer' => [
        robots,
        video,
        today,
      ],
    _ => [
        mode,
        robots,
        video,
        today,
        TourStep(null, tr('Admin', '管理'),
            tr('The Admin tab starts with pending items and the site setup checklist; complete them in order. Add robots: Robots → Add. Confirm no-go zones: Map. Approve accounts: Admin → Accounts.',
                '「管理」页顶部是待处理事项和开站清单，请逐项完成。添加机器人：机器人 → 添加；确认禁行区：地图；审批账号：管理 → 账号。')),
      ],
  };
}

bool _running = false;

/// 进站点后值守页建好了调：这个账号没看过当前版本就开始。
Future<void> maybeStartTour(BuildContext context, SiteApi api, DutyTargets t) async {
  if (_running) return;
  int seen;
  try {
    final me = await api.me();
    final g = me['guide'];
    seen = g is Map && g['tour'] is num ? (g['tour'] as num).toInt() : kTourVersion; // 老站点不带：不打扰
  } on SiteError {
    return;
  } on FormatException {
    return;
  }
  if (seen >= kTourVersion || !context.mounted) return;
  await runTour(context, api, t);
}

/// 外壳登记的「切回值守页、再走一遍导览」（「使用教程」从别的栏点进来：那一栏切走就拆了，导览要在外壳上跑）。
Future<void> Function()? replayTour;

/// 「使用教程」：回到值守页再走一遍（外壳没登记就只讲文字）。
Future<void> restartTour(BuildContext context, SiteApi api) async {
  final again = replayTour;
  if (again != null) return again();
  await runTour(context, api, DutyTargets());
}

Future<void> runTour(BuildContext context, SiteApi api, DutyTargets t) async {
  if (_running) return;
  _running = true;
  try {
    final role = api.session?.role ?? '';
    final steps = tourSteps(role, t);
    var finished = true;
    for (var i = 0; i < steps.length; i++) {
      if (!context.mounted) return;
      final s = steps[i];
      final ctx = s.target?.currentContext;
      if (ctx != null && ctx.mounted) {
        await Scrollable.ensureVisible(ctx, duration: const Duration(milliseconds: 200), alignment: 0.3);
      }
      if (!context.mounted) return;
      final go = await _showStep(context, s, i, steps.length);
      if (go != true) {
        finished = false;
        break;
      }
    }
    try {
      await api.setGuide(<String, dynamic>{'tour': kTourVersion});
    } on SiteError {
      // 记不上：下次再看一遍，不要紧
    }
    _running = false;
    // 练习页开着的时候导览已经算走完了（不挡下一次「使用教程」）
    if (finished && (api.session?.canHandleAlerts ?? false) && role != 'owner' && context.mounted) {
      unawaited(Navigator.push(context, MaterialPageRoute<void>(builder: (_) => const PracticeAlarmPage())));
    }
  } finally {
    _running = false;
  }
}

Rect? _rectOf(GlobalKey? k) {
  final ro = k?.currentContext?.findRenderObject();
  if (ro is! RenderBox || !ro.attached || !ro.hasSize) return null;
  final o = ro.localToGlobal(Offset.zero);
  return o & ro.size;
}

Future<bool?> _showStep(BuildContext context, TourStep s, int i, int n) => showGeneralDialog<bool>(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.transparent,
      pageBuilder: (c, _, _) {
        final rect = _rectOf(s.target);
        final size = MediaQuery.sizeOf(c);
        final below = rect == null || rect.center.dy < size.height / 2;
        final nw = Nw.of(c);
        final card = Material(
          key: tourCardKey,
          color: nw.surface,
          elevation: 6,
          borderRadius: BorderRadius.circular(Nw.r12),
          child: Padding(
            padding: const EdgeInsets.all(Nw.s16),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text('${i + 1} / $n · ${s.title}',
                  style: NwText.titleSmall.copyWith(color: nw.text, fontWeight: FontWeight.w700)),
              const SizedBox(height: Nw.s8),
              Text(s.body, style: NwText.bodyMedium.copyWith(color: nw.text)),
              const SizedBox(height: Nw.s8),
              Row(children: [
                TextButton(
                    key: tourSkipKey, onPressed: () => Navigator.pop(c, false), child: Text(tr('Skip', '跳过'))),
                const Spacer(),
                NwButton(
                    buttonKey: tourNextKey,
                    label: i + 1 == n ? tr('Done', '完成') : tr('Next', '下一步'),
                    onPressed: () => Navigator.pop(c, true)),
              ]),
            ]),
          ),
        );
        return Stack(children: [
          Positioned.fill(child: SizedBox.expand(child: CustomPaint(size: size, painter: _Dim(rect, nw.primary)))),
          Positioned(
              left: Nw.s16,
              right: Nw.s16,
              top: below ? ((rect?.bottom ?? size.height / 3) + Nw.s8).clamp(0, size.height - 220) : null,
              bottom: below ? null : (size.height - rect.top + Nw.s8).clamp(0, size.height - 220),
              child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 480), child: card))),
        ]);
      },
    );

class _Dim extends CustomPainter {
  final Rect? hole;
  final Color ring;
  _Dim(this.hole, this.ring);

  @override
  void paint(Canvas canvas, Size size) {
    final all = Offset.zero & size;
    final h = hole?.inflate(4);
    // 整屏压暗，再把要看的那一块挖空（单独一层里清掉）
    canvas.saveLayer(all, Paint());
    canvas.drawRect(all, Paint()..color = const Color(0x99000000));
    if (h != null) {
      canvas.drawRRect(RRect.fromRectAndRadius(h, const Radius.circular(Nw.r8)), Paint()..blendMode = BlendMode.clear);
    }
    canvas.restore();
    if (h != null) {
      canvas.drawRRect(RRect.fromRectAndRadius(h, const Radius.circular(Nw.r8)),
          Paint()
            ..color = ring
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2);
    }
  }

  @override
  bool shouldRepaint(_Dim old) => old.hole != hole || old.ring != ring;
}

// ------------------------------------------------------------ 报警练习

/// 一条假的 P1 报警，照着点一遍。**什么都不发给站点。**
class PracticeAlarmPage extends StatefulWidget {
  const PracticeAlarmPage({super.key});

  static const Key respondKey = Key('practice-respond');
  static const Key takeKey = Key('practice-take');
  static Key outcomeKey(String o) => Key('practice-$o');
  static const Key doneKey = Key('practice-done');
  static const Key realKey = Key('practice-real-advice');

  @override
  State<PracticeAlarmPage> createState() => _PracticeAlarmPageState();
}

class _PracticeAlarmPageState extends State<PracticeAlarmPage> {
  int _step = 0;
  String? _outcome;

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final steps = <Widget>[
      // 0：值守页最上面的红条
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(tr('During an alarm, the top of the duty page looks like this:', '报警时，值守页顶部显示如下：'),
            style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
        nwGap8,
        NwCard(
          tone: NwTone.error,
          child: Row(children: [
            const NwLevelBox(level: 'P1'),
            const SizedBox(width: Nw.s8),
            Expanded(
                child: Text(tr('PRACTICE · A sees a person in the North area', '演练 · A 在北区看见人'),
                    style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700))),
            NwButton(
                buttonKey: PracticeAlarmPage.respondKey,
                size: NwButtonSize.small,
                variant: NwButtonVariant.destructive,
                label: tr('Respond', '去处理'),
                onPressed: () => setState(() => _step = 1)),
          ]),
        ),
        nwGap8,
        Text(tr('Tap Respond.', '点「去处理」。'), style: NwText.bodyMedium.copyWith(color: c.text)),
      ]),
      // 1：报警页
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        AspectRatio(
            aspectRatio: 16 / 9,
            child: Container(
                decoration: BoxDecoration(color: Colors.black87, borderRadius: BorderRadius.circular(Nw.r8)),
                alignment: Alignment.center,
                child: Text(tr('Snapshot from the robot (practice)', '机器人抓拍（演练）'),
                    style: NwText.bodySmall.copyWith(color: Colors.white70)))),
        nwGap8,
        Text(
            tr('The alarm page shows the snapshot, live video and map location. Tap "Take ownership" so others see someone is responding.',
                '报警页显示抓拍、实时画面和地图位置。点「我来处理」，其他人会看到已有人处理。'),
            style: NwText.bodyMedium.copyWith(color: c.text)),
        nwGap8,
        NwButton(
            buttonKey: PracticeAlarmPage.takeKey,
            label: tr('Take ownership', '我来处理'),
            onPressed: () => setState(() => _step = 2)),
      ]),
      // 2：写结论
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(
            tr('After checking the video or the site, record the outcome:', '查看画面或到现场核实后，记录结论：'),
            style: NwText.bodyMedium.copyWith(color: c.text)),
        nwGap8,
        Wrap(spacing: Nw.s8, runSpacing: Nw.s8, children: [
          for (final (o, label) in [
            ('real', tr('Real person', '真有人')),
            ('false', tr('False alarm', '误报')),
            ('handled', tr('Resolved', '已处理')),
          ])
            NwButton(
                buttonKey: PracticeAlarmPage.outcomeKey(o),
                variant: NwButtonVariant.outline,
                label: label,
                onPressed: () => setState(() {
                      _outcome = o;
                      _step = 3;
                    })),
        ]),
      ]),
      // 3：好了
      Column(key: PracticeAlarmPage.doneKey, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Icon(Icons.check_circle_rounded, size: 48, color: c.success),
        nwGap8,
        Text(tr("Practice complete. Handle real alarms the same way.", '演练完成。实际报警按同样步骤处理。'),
            textAlign: TextAlign.center, style: NwText.titleSmall.copyWith(color: c.text)),
        // 手机 App 测试 M24：选了「真有人」要教真有人时怎么办
        if (_outcome == 'real') ...[
          nwGap8,
          Text(
              tr('If someone is really there: keep yourself safe, do not confront them alone. Call the police or your security team, '
                      'keep the live video open, and tell them where the robot saw the person.',
                  '真有人时：先顾自己安全，别一个人去拦。打报警电话或通知安保队，开着实时画面，告诉他们机器人在哪儿看到的人。'),
              key: PracticeAlarmPage.realKey,
              style: NwText.bodyMedium.copyWith(color: c.text)),
        ],
        nwGap8,
        NwButton(label: tr('Back', '返回'), onPressed: () => Navigator.pop(context)),
      ]),
    ];
    return Scaffold(
      appBar: AppBar(title: Text(tr('Practice alarm', '报警练习'))),
      body: NwListView(children: [
        NwNotice(
            tone: NwTone.info,
            text: tr('Practice mode: nothing is sent to the site or recorded.', '演练模式：操作不会发送到站点，也不会记录。')),
        const SizedBox(height: Nw.s16),
        steps[_step],
      ]),
    );
  }
}

// ------------------------------------------------------------ 常见问题

class _Faq {
  final Set<String>? roles; // null = 谁都看
  final String q;
  final String a;
  const _Faq(this.roles, this.q, this.a);
}

const _handlers = {'guard', 'owner', 'admin', 'engineer'};
const _admins = {'admin', 'engineer'};

/// 「怎么做」（稿 S-help 中段）：一件事一行，点开就地展开。
List<_Faq> _howTo() => [
      // 手机 App 测试 M15：按角色写（只读账号处理不了报警、经理不能恢复）
      _Faq({'viewer'}, tr('What can I do with an alarm?', '收到报警我能做什么'),
          tr('A view-only account can watch the snapshot, live video and map, but cannot respond. Call the guard on duty.',
              '只读账号能看抓拍、实时画面和地图，处理不了报警。请联系值班保安。')),
      _Faq(_handlers, tr('Respond to an alarm', '收到报警如何处理'),
          tr('On Now, tap the red bar → check the snapshot and live video → tap Take ownership. If someone is there, go with a colleague or call the police; then record Confirmed intrusion / False alarm / Resolved and close the incident.',
              '在「现在」页点红框 → 看抓拍和实时画面 → 点「我来处理」。确认有人时叫上同事到现场或报警；处理完选结论（确认有人 / 误报 / 已处理）再结案。')),
      _Faq(_handlers, tr('Dispatch patrols, remote control, E-STOP', '派巡逻、遥控、急停'),
          tr('On Now, tap a robot → Dispatch patrol, Stop here, Return to standby, or Remote (landscape only; the robot stops when you leave). E-STOP ALL (bottom right on Now, top right elsewhere) stops every robot until someone resets it. The emergency stop button on the robot always works.',
              '在「现在」页点一台机器人 → 派巡逻、原地停下、回待命点，或遥控（只能横屏，离开遥控页机器人就停）。「全部急停」（「现在」页右下、别的页右上）让所有机器人原地停住，直到有人恢复。机器人身上的急停按钮随时可用。')),
      _Faq(null, tr('Find recordings', '如何查看录像'),
          tr('Site → Recordings: one-minute segments per robot, kept 30 days. Photos of each patrol are under Site → Patrol log.',
              '「现场 → 录像」：每台机器人一分钟一段，留 30 天。每趟巡逻拍的照片在「现场 → 巡逻记录」。')),
      _Faq(_admins, tr('Add accounts', '如何添加账号'),
          tr('Applicants tap Request account on the sign-in page; an administrator approves under Site → Users and picks the role (View only by default). New accounts with a set role are added on the web console.',
              '申请人在登录页点「申请账号」；管理员在「现场 → 人员」批准并选权限（默认只看）。直接建账号、改权限在网页上做。')),
      _Faq(_admins, tr('Getting started with a new site', '新站点从哪里开始'),
          tr('Site → Overview → Site setup. Complete it in order; each item opens the page where it is done.',
              '「现场 → 概况」里的开站清单，按顺序做，每项点进去就是要做的那一页。')),
    ];

/// 常见问题（稿 S-help 下段）。
List<_Faq> _faqs() => [
      _Faq({'guard', 'owner'}, tr('Why is my patrol queued?', '巡逻为何排队'),
          tr('Scheduled patrols take priority. A one-off patrol that clashes with the schedule starts after it, and you are notified when it starts. To check right away, use Remote.',
              '日程巡逻优先。临时巡逻与日程冲突时，在日程巡逻结束后开始，开始时会通知你。需要立即查看请用「遥控」。')),
      _Faq(_handlers.difference({'owner'}), tr("Robot can't be dispatched", '机器人无法派出'),
          tr('An amber note at the top of the robot page says why and offers a fix. Common causes: no-go zones not confirmed (contact the administrator), robot not localized (set its position), robot E-stopped (reset), offline or charging.',
              '机器人页顶上琥珀一条会说原因并给处理按钮。常见原因：禁行区未确认（联系管理员）、机器人未定位（设位置）、已急停（恢复）、离线或正在充电。')),
      _Faq({'owner'}, tr("Robot can't be dispatched", '机器人无法派出'),
          tr('An amber note says why. Common causes: robot E-stopped (a guard or administrator resets it), no-go zones not confirmed (contact the administrator), offline or charging.',
              '琥珀一条会说原因。常见原因：已急停（要保安或管理员恢复）、禁行区未确认（联系管理员）、离线或正在充电。')),
      _Faq(null, tr('What if a robot goes offline?', '机器人离线怎么办'),
          tr('Check the robot is powered on and the Wi-Fi works. If the Wi-Fi changed, an administrator reconfigures it under the robot\'s Settings → Network.',
              '检查机器人是否开机、Wi-Fi 是否正常。如更换过 Wi-Fi，请管理员在这台机器人的「设置 → 网络」里重新配置。')),
      _Faq(null, tr('False alarm vs Confirmed intrusion', '误报和确认有人有什么区别'),
          tr('Confirmed intrusion: you saw a person who should not be there. False alarm: nobody, or someone allowed (staff, a resident). Resolved: something real that was dealt with (a gate left open). The outcome is kept in the alarm log and the shift report.',
              '确认有人：看到了不该在的人。误报：没人，或是允许的人（员工、住户）。已处理：确有其事、已经处理好（比如门没关）。结论记在报警记录和交班报告里。')),
      _Faq(null, tr('How arming and weather affect patrols', '布防和天气怎么影响巡逻'),
          tr('Patrol schedules run whether the site is armed or not; arming decides which detections raise alarms. In rain or strong wind the site can hold scheduled patrols; Site → Arming & patrols shows the current weather rule.',
              '巡逻日程不管布防没布防都照跑；布防决定哪些检测会报警。下雨、大风时站点可以暂停日程巡逻；「现场 → 布防与巡逻」里能看到现在的天气规则。')),
    ];

/// 使用教程与常见问题（App V2 稿 S-help）：入门（值守导览、报警演练）、怎么做、常见问题。一行一件，点开就地展开。
class HelpPage extends StatelessWidget {
  final String role;

  /// 给了才有「值守导览」（要站点连接）。
  final SiteApi? api;
  const HelpPage({super.key, required this.role, this.api});

  static const Key tourKey = Key('help-tour');
  static const Key drillKey = Key('help-drill');

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final api = this.api;
    final can = _handlers.contains(role);
    Widget label(String t) => Padding(
        padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s24, Nw.s16, Nw.s8),
        child: Text(t, style: NwText.labelMedium.copyWith(color: c.textSecondary, fontWeight: FontWeight.w700)));
    Widget link(Key key, IconData icon, String title, String sub, VoidCallback on) => Material(
        color: c.surface,
        child: InkWell(
            key: key,
            onTap: on,
            child: Container(
                padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: 12),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
                child: Row(children: [
                  Icon(icon, size: 22, color: c.text),
                  const SizedBox(width: Nw.s16),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(title, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                    Text(sub, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  ])),
                  Icon(Icons.chevron_right_rounded, color: c.textSecondary),
                ]))));
    var n = 0;
    Widget faq(_Faq f) => Material(
        key: Key('faq-${n++}'),
        color: c.surface,
        shape: Border(bottom: BorderSide(color: c.outline)),
        child: ExpansionTile(
            shape: const Border(),
            collapsedShape: const Border(),
            title: Text(f.q, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            childrenPadding: const EdgeInsets.fromLTRB(Nw.s16, 0, Nw.s16, Nw.s16),
            expandedAlignment: Alignment.centerLeft,
            children: [Text(f.a, style: NwText.bodyMedium.copyWith(color: c.text))]));
    bool mine(_Faq f) => f.roles == null || f.roles!.contains(role);
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(title: Text(tr('Guides & FAQ', '使用教程与常见问题'))),
      body: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
        if (api != null || can) ...[
          label(tr('Getting started', '入门')),
          if (api != null)
            link(tourKey, Icons.play_arrow_rounded, tr('Monitoring tour', '值守导览'),
                tr('A walkthrough on the live screens: Now, incident, E-STOP', '在真页面上走一遍：现在、这件事、急停'),
                () => restartTour(context, api)),
          if (can)
            link(drillKey, Icons.notifications_none_rounded, tr('Alarm drill', '报警演练'),
                tr('A simulated alarm visible only to you; practise the response. Nothing is sent to the site.',
                    '模拟报警，只有你看得到，练一遍处理步骤；不发到站点。'),
                () => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => const PracticeAlarmPage()))),
        ],
        label(tr('How to', '怎么做')),
        for (final f in _howTo()) if (mine(f)) faq(f),
        label(tr('FAQ', '常见问题')),
        for (final f in _faqs()) if (mine(f)) faq(f),
      ]),
    );
  }
}

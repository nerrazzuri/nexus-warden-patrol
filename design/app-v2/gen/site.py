# 「现场」层（浅色）+ 进入的几页（深色）
from ac import *
L = LIGHT
D = DARK


def stopmini():
    return f'<button type="button" aria-label="全部急停" style="height:40px;padding:0 10px;border:0;border-radius:2px;background:#D42F33;color:#fff;font:700 14px {F};display:inline-flex;align-items:center;gap:6px;flex:none">{ic("oct",18,"#fff")}急停</button>'


def lbar(title, sub='', right=''):
    return appbar(title, sub, light=True, right=right + stopmini())


def item(icon, title, sub='', right='', sign=''):
    return f'''<a href="#" class="li">{ic(icon,22,L['sec']) if icon else ''}<div class="b"><div style="font-weight:600;display:flex;align-items:center;gap:8px">{sign}{title}</div>{f'<div class="s">{sub}</div>' if sub else ''}</div>{right}{ic('chev',18,L['mut'])}</a>'''


def grp(title, rows):
    return f'<section style="margin-top:8px"><div class="lbl" style="padding:14px 16px 6px">{title}</div><div style="background:{L["surf"]};border-top:1px solid {L["rule"]}">{rows}</div></section>'


def body_l(inner):
    return f'<div style="flex:1;min-height:0;background:{L["bg"]}">{inner}</div>'


def lsec(title, inner, right=''):
    return f'''<section style="background:{L['surf']};border-bottom:1px solid {L['rule']};padding:14px 16px;margin-top:8px">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><h2 class="h2" style="flex:1">{title}</h2>{right}</div>{inner}</section>'''


def acct(name, role):
    return f'''<section style="margin-top:8px;background:{L['surf']};border-top:1px solid {L['rule']}">
  <div class="li">{ic('person',22,L['sec'])}<div class="b"><b>{name}</b><div class="s">{role} · estate-1</div></div></div>
  {item(None,'改密码')}{item(None,'退出站点','回到站点列表；这台手机不再收这个站点的推送')}</section>'''


APP = lambda: grp('本机', item('gear', '设置', '语言、外观、报警声音、后台值守、到点提醒、关于与更新') + item('help', '使用教程与常见问题', '值班页导览、怎么处理报警、报警演练') + item('doc', '报问题', '写一句出了什么事，日志发给工程师'))
REC = lambda: grp('记录', item('bell', '报警记录', '本班 14 条 · 1 条没关') + item('cam', '录像', '每台机器人一分钟一段，留 30 天') + item('route', '巡逻记录', '每一趟的照片和判读') + item('note', '交班留言', '最近一条：olga 19:05'))


def site_dir(name, title, role, who, groups, h=844):
    body = topbar(layer='site', stop_small=True, clock='10:20', arm='撤防 · 19:00 布防', armsign='none') + body_l(groups + acct(who, role)) + (fold(light=True) if h > 844 else '')
    return board(name, title, body, light=True, h=h)


def s_admin():
    g = grp('日常', item('home', '概况', '待处理 2 · 开站清单 5/7', sign='<span class="discb"></span>') + item('robot', '机器人', '2 台 · 1 台请求加入') + item('person', '人员', '6 个账号 · 1 个待批准')) + \
        grp('现场', item('map', '地图与布置', '防区、禁行区、巡逻路线、待命点、摄像头、拦截点') + item('shield', '布防与巡逻', '布防模式、临时撤防、布防时间、巡逻日程、天气')) + \
        REC() + grp('高级', item('map', '地图管理与建图', '每张图的版本、下发、退回、新建') + item('chart', '站点体检', '各项检查、版本、诊断包') + item('cloud', '软件升级', '站点、机器人、App 的版本')) + APP()
    return site_dir('App-S-admin', 'App · 管理员 · 现场（目录）', '管理员', 'demo', g, h=1500)


def s_guard():
    return site_dir('App-S-guard', 'App · 保安 · 现场（目录）', '保安', 'gina', REC() + APP(), h=900)


def s_mgr():
    g = grp('日常', item('home', '概况', '只读 · 24 小时报警和处理结果') + item('robot', '机器人', '看状态、派巡逻')) + grp('现场', item('shield', '布防与巡逻', '布防模式、临时撤防、布防时间、巡逻日程')) + REC() + APP()
    return site_dir('App-S-mgr', 'App · 经理 · 现场（目录）', '经理', 'olga', g, h=1130)


def s_viewer():
    return site_dir('App-S-viewer', 'App · 只读 · 现场（目录）', '只读', 'vic', grp('记录', item('bell', '报警记录', '只看') + item('cam', '录像', '只看') + item('route', '巡逻记录', '只看')) + APP(), h=844)


# ---------- 概况（管理员） ----------
def s_home():
    need = lambda t, s, b: f'<div style="display:flex;gap:10px;align-items:flex-start;padding:12px 0;border-top:1px solid {L["rule"]}"><span class="discb" style="margin-top:5px"></span><div style="flex:1"><b>{t}</b><div class="note">{s}</div></div>{B(b, "pri", sm=True)}</div>'
    chk = lambda ok, t: f'<div style="display:flex;align-items:center;gap:10px;min-height:40px;border-top:1px solid {L["rule"]}">{"<span class=sq></span>" if ok else "<span class=p3></span>"}<span style="flex:1;{"color:"+L["sec"] if ok else "font-weight:600"}">{t}</span>{"" if ok else ic("chev",16,L["mut"])}</div>'
    inner = lsec('待处理 2', need('C40388 请求加入', 'olga 的手机 · 09:41 · 核对码 482 913', '核对后批准') + need('vic 申请账号', '只读 · 08:12', '去审批')) + \
        lsec('开站清单 5/7', ''.join(chk(o, t) for o, t in [(True, '添加机器人'), (True, '建第一张图'), (True, '标原点和待命点'), (False, '确认禁行区'), (True, '画巡逻路线'), (True, '排巡逻日程'), (False, '至少一部手机能收到 P1 推送')])) + \
        lsec('今天', f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:{L["rule"]};border:1px solid {L["rule"]}">' + ''.join(f'<div style="background:{L["surf"]};padding:8px 10px"><b style="font-size:22px">{a}</b><div class="note">{b}</div></div>' for a, b in [('14', '报警（1 条没关）'), ('6', '巡逻走完'), ('0', '误报以外')]) + '</div><div class="note" style="margin-top:8px">19:00 布防 · 巡逻 19:00 / 22:00 / 01:00 / 04:00</div>') + \
        lsec('机器人', f'<div style="display:flex;gap:10px;align-items:center;min-height:36px"><span class="sq"></span><b>A</b><span style="flex:1">待命 · 充电桩 1</span><b>96%</b></div><div style="display:flex;gap:10px;align-items:center;min-height:36px"><span class="tri"></span><b>B</b><span style="flex:1">换网待批</span><b style="color:{L["ambt"]}">54%</b></div>')
    return board('App-S-home', 'App · 管理员 · 概况', lbar('概况', '待处理 2 · 开站清单 5/7') + body_l(inner) + fold(light=True), light=True, h=1400)


def s_home_m():
    rows = [('23:47', 'ring', '北门有人翻越', 'gina · 确认有人 · 已报警'), ('23:31', 'ring', 'B 等待换电', 'olga · 已处理'), ('22:05', 'p3', '停车场车辆滞留', 'gina · 误报'), ('21:40', 'ring', '南墙有人靠近', 'gina · 确认有人')]
    r = ''.join(f'<div style="display:grid;grid-template-columns:48px 16px 1fr;gap:8px;align-items:center;padding:8px 0;border-top:1px solid {L["rule"]}"><span class="mut">{a}</span><span class="{s}"></span><div><b>{t}</b><div class="note">{w}</div></div></div>' for a, s, t, w in rows)
    inner = lsec('24 小时报警 4', r) + lsec('管理员在处理', '<div class="note">只看状态。</div>' + f'<div style="display:flex;gap:10px;padding:10px 0;border-top:1px solid {L["rule"]};margin-top:8px"><span class="discb" style="margin-top:5px"></span><div><b>C40388 请求加入</b><div class="note">等管理员批准</div></div></div>') + \
        lsec('值班人员', '<div style="display:grid;grid-template-columns:80px 1fr;gap:6px"><span class="mut">今晚</span><b>gina（保安）19:00 → 07:00</b><span class="mut">交班留言</span><span>停车场有施工车辆进出，22:00 前算正常。</span></div>') + \
        lsec('今天的安排', '<div class="note">19:00 布防 · 巡逻 19:00 / 22:00 / 01:00 / 04:00</div>')
    return board('App-S-home-m', 'App · 经理 · 概况（只读）', lbar('概况', '只读') + body_l(inner) + fold(light=True), light=True, h=1200)


# ---------- 记录 ----------
def s_alarms():
    f = f'<div style="display:flex;gap:6px;padding:10px 16px;overflow:hidden;background:{L["surf"]};border-bottom:1px solid {L["rule"]}">' + ''.join(f'<span class="chip {"c-n" if not on else ""}" style="height:32px;{"background:"+L["blue"]+";color:#fff" if on else ""}">{t}</span>' for t, on in [('本班', True), ('没关 1', False), ('P1 3', False), ('机器人', False), ('筛选…', False)]) + '</div>'
    rows = [('ring', '北门有人翻越', '23:47 · 摄像头 3 · gina 处理中', '没关'), ('ring', 'B 等待换电', '23:31 · 充电桩 1 · olga', '已处理'), ('tri', 'A 电量低于 30%', '23:12 · 巡逻中', '已处理'), ('p3', '停车场车辆滞留', '22:05 · gina', '误报'), ('ring', '南墙有人靠近', '21:40 · gina', '确认有人'), ('tri', 'A 卡住，已脱困', '20:52', '已处理'), ('off', 'B 离线 2 分钟', '19:30', '已处理')]
    li = ''.join(f'<a href="#" class="li" style="background:{L["surf"]}"><span class="{s}"></span><div class="b"><b>{t}</b><div class="s">{m}</div></div><span class="chip {"c-bad" if st=="没关" else "c-n"}">{st}</span></a>' for s, t, m, st in rows)
    inner = f + li + f'<div style="padding:12px 16px">{btnrow([B("导出表格", sm=True), B("更早的", sm=True)])}</div>'
    return board('App-S-alarms', 'App · 记录 · 报警', lbar('报警记录', '本班 19:00 → 07:00 · 14 条') + body_l(inner), light=True)


def s_alarm_rec():
    v = f'<div style="padding:0">{video(210, cap="A · 前摄像头 · 23:49:31", tabs=None, live=False)}</div>'
    ctl = f'<div style="padding:10px 16px;background:{L["surf"]};border-bottom:1px solid {L["rule"]}">' + btnrow([B('−10 秒', sm=True), B('播放', sm=True, kind='pri'), B('+10 秒', sm=True), B('1×', sm=True)], 4) + '<div style="height:8px"></div>' + btnrow([B('截图', sm=True), B('导出片段', sm=True), B('保留这段', sm=True)], 3) + '</div>'
    inner = f'''<div style="padding:12px 16px;background:{L['surf']};border-bottom:1px solid {L['rule']}"><div style="display:flex;gap:10px"><span class="ring lg"></span><div><b style="font-size:19px">南墙有人靠近</b><div class="note">21:40 · B 前摄像头 · 南区</div><div style="margin-top:4px"><span class="chip c-n">确认有人</span> <span class="note">gina 21:52 结案</span></div></div></div></div>''' + v + ctl + \
        lsec('经过', ''.join(f'<div style="display:grid;grid-template-columns:64px 1fr;gap:8px;min-height:30px"><span class="mut">{a}</span><span>{b}</span></div>' for a, b in [('21:40:05', 'B 发现有人靠近南墙'), ('21:40:30', 'gina 接手'), ('21:41:10', 'B 喊话：请离开'), ('21:44:02', '人离开'), ('21:52:18', 'gina 结案：确认有人。备注：外卖员找错门')])) + \
        lsec('怎么回事', '<div class="note">机器人看到有人进了布防的南区。该做什么：看画面确认，必要时喊话、到场。</div>') + \
        f'<div style="padding:12px 16px">{btnrow([B("重新打开（22:02 前）")], 1)}</div>'
    return board('App-S-alarm-rec', 'App · 记录 · 一条报警', lbar('报警', '21:40 · 已结案') + body_l(inner) + fold(light=True), light=True, h=1250)


KEEP = '<span class="chip c-n">留着</span>'


def s_video():
    segs = ''.join(f'<a href="#" class="li" style="background:{L["surf"]}"><span style="width:64px;height:40px;background:#000;flex:none"></span><div class="b"><b>{t}</b><div class="s">{s}</div></div>{KEEP if k else ""}</a>' for t, s, k in [('23:49 – 23:50', 'A 前 · 北门 · 有报警', True), ('23:48 – 23:49', 'A 前 · 往北门', False), ('23:47 – 23:48', 'A 前 · 2 号楼北侧', False), ('23:46 – 23:47', 'A 前', False)])
    inner = f'''<div style="padding:10px 16px;background:{L['surf']};border-bottom:1px solid {L['rule']};display:grid;gap:8px">
  <div class="seg" style="grid-template-columns:1fr 1fr"><button class="on" type="button">A · C40221</button><button type="button">B · C40011</button></div>
  <div class="row" style="grid-template-columns:1fr 1fr 1fr">{B('11-15', sm=True)}{B('前', sm=True)}{B('跳到 23:47', sm=True)}</div></div>
  <div style="padding:10px 16px;background:{L['surf']};border-bottom:1px solid {L['rule']}"><div class="lbl" style="margin-bottom:6px">23:00 – 00:00</div><div style="position:relative;height:28px;background:{L['raised']}"><div style="position:absolute;left:78%;width:3%;top:0;bottom:0;background:{L['redt']}"></div><div style="position:absolute;left:0;width:96%;bottom:0;height:6px;background:{L['blue']};opacity:.5"></div></div><div class="note" style="margin-top:4px;display:flex;justify-content:space-between"><span>23:00</span><span>23:30</span><span>00:00</span></div></div>
  {segs}<div style="padding:12px 16px">{btnrow([B('← 30 分钟', sm=True), B('30 分钟 →', sm=True)])}</div>
  <div class="note" style="padding:0 16px">录像在站点留 30 天；标了「留着」的不删。解绑了的机器人也能在这里看。</div>'''
    return board('App-S-video', 'App · 记录 · 录像', lbar('录像', '一分钟一段 · 点一段播放') + body_l(inner), light=True)


def s_runs():
    rows = ''.join(f'<a href="#" class="li" style="background:{L["surf"]}"><span class="{s}"></span><div class="b"><b>{t}</b><div class="s">{m}</div></div><span class="note">{p}</span></a>' for s, t, m, p in [('sq', '22:00 guard-1 · A', '走完 · 31 分钟 · 0 处异常', '24 张'), ('tri', '19:00 guard-1 · A', '走完 · 1 处异常：东门没锁', '22 张'), ('ring', '昨天 04:00 guard-1 · B', '没走完：电量不足回充', '9 张'), ('sq', '昨天 01:00 guard-1 · A', '走完', '24 张')])
    photo = f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px">' + ''.join(f'<div style="aspect-ratio:4/3;background:#000;position:relative"><span style="position:absolute;left:4px;bottom:2px;font-size:11px;color:#fff">{n}</span></div>' for n in ['北门', '2 号楼北', '东门 ⚠', '停车场', '南墙', '充电桩'][:6]).replace('⚠', '') + '</div>'
    inner = f'<div style="padding:10px 16px;background:{L["surf"]};border-bottom:1px solid {L["rule"]}">' + f'<div class="seg" style="grid-template-columns:1fr 1fr 1fr"><button class="on" type="button">今天 4</button><button type="button">有异常 1</button><button type="button">全部</button></div></div>' + rows + \
        lsec('19:00 这一趟 · 东门', photo + f'<div style="display:flex;gap:10px;align-items:flex-start;margin-top:10px"><span class="tri" style="margin-top:4px"></span><div><b>东门没锁</b><div class="note">判读：异常 · 复核：还没复核</div></div></div><div style="height:10px"></div>' + btnrow([B('确认异常', sm=True), B('其实正常', sm=True), B('看不清', sm=True)], 3))
    return board('App-S-runs', 'App · 记录 · 巡逻', lbar('巡逻记录', '每一趟的照片、判读和复核') + body_l(inner) + fold(light=True), light=True, h=1080)


def s_notes():
    n = lambda who, tm, t: f'<div style="background:{L["surf"]};border-bottom:1px solid {L["rule"]};padding:12px 16px"><div style="display:flex"><b style="flex:1">{who}</b><span class="note">{tm}</span></div><p style="margin:4px 0 0">{t}</p></div>'
    inner = f'''<div style="padding:12px 16px;background:{L['surf']};border-bottom:1px solid {L['rule']}"><div class="inp" style="height:88px;align-items:flex-start;padding-top:10px;color:{L['mut']}">给下一班留言…</div><div style="height:8px"></div>{btnrow([B('发出', 'pri')], 1)}</div>''' + \
        n('olga · 经理', '今天 19:05', '停车场有施工车辆进出，22:00 前算正常。') + n('gina · 保安', '今天 07:02', 'B 夜里离线 2 分钟，自己回来了。南墙 21:40 有人靠近，是外卖员。') + n('olga · 经理', '昨天 19:00', '东门门禁坏了，巡逻到东门多看一眼。')
    return board('App-S-notes', 'App · 记录 · 交班留言', lbar('交班留言', '最近 20 条') + body_l(inner), light=True)


# ---------- 机器人 ----------
def s_robots():
    r = lambda s, n, c, st, pct, pc='': f'<a href="#" class="li" style="background:{L["surf"]}"><span class="{s}"></span><div class="b"><b style="font-size:17px">{n} <span class="mut" style="font-weight:400;font-size:14px">{c}</span></b><div class="s">{st}</div></div><b style="{pc}">{pct}</b>{ic("chev",18,L["mut"])}</a>'
    inner = r('sq', 'A', 'C40221', '待命 · 充电桩 1 · 版本 2.8.1', '96%') + r('tri', 'B', 'C40011', '换网待批 · 版本 2.8.1', '54%', 'color:' + L['ambt']) + \
        lsec('请求加入 1', f'<div style="display:flex;gap:10px"><span class="discb" style="margin-top:5px"></span><div><b>C40388</b><div class="note">olga 的手机 · 09:41</div><div style="margin-top:4px">核对码 <b style="letter-spacing:.08em">482 913</b></div></div></div><div class="note" style="margin:8px 0">到机器人旁边，核对机身屏上的码一样再批准。</div>' + btnrow([B('核对后批准', 'pri'), B('拒绝')])) + \
        f'<div style="padding:12px 16px">{btnrow([B("添加机器人", icon="plus")], 1)}</div>'
    return board('App-S-robots', 'App · 管理员 · 机器人', lbar('机器人', '2 台 · 1 台请求加入') + body_l(inner), light=True)


def s_robot_set():
    kv = lambda k, v, b='': f'<div style="display:flex;align-items:center;gap:10px;min-height:48px;border-top:1px solid {L["rule"]}"><span class="mut" style="width:92px;flex:none">{k}</span><span style="flex:1;min-width:0">{v}</span>{b}</div>'
    inner = f'<div style="padding:10px 16px;background:{L["surf"]};border-bottom:1px solid {L["rule"]}"><div class="seg" style="grid-template-columns:1fr 1fr"><button type="button">操作</button><button class="on" type="button">设置</button></div></div>' + \
        lsec('基本', kv('名字', 'A', B('改', sm=True)) + kv('派单方式', '日程和手动都能派', B('改', sm=True)) + kv('网络', 'WiFi estate-iot · 信号好', B('换 WiFi', sm=True)) + kv('上装', '警灯、警笛、喇叭、热像')) + \
        lsec('位置', kv('原点', '充电桩 1 · 已标', B('在这儿标', sm=True)) + kv('待命点', '充电桩 1（默认）', B('改', sm=True)) + kv('设位置', '定位不准时在地图上点它在哪', B('去地图', sm=True))) + \
        lsec('检查单', ''.join(f'<div style="display:flex;align-items:center;gap:10px;min-height:40px;border-top:1px solid {L["rule"]}">{"<span class=sq></span>" if o else "<span class=tri></span>"}<span style="flex:1">{t}</span></div>' for o, t in [(True, '证书 · 到 2027-05-02'), (True, '时间同步'), (False, '存储 81%，建议清理'), (True, '版本和站点配套')])) + \
        lsec('排查与维护', item('wrench', '远程运维', '诊断快照、日志、重启、对时、续证书、参数').replace('class="li"', 'class="li" style="padding:8px 0"') + item('doc', '建图日志', '录包、重建的日志').replace('class="li"', 'class="li" style="padding:8px 0"') + f'<div style="height:10px"></div>' + btnrow([B('开始录包', sm=True), B('标原点', sm=True)])) + \
        lsec('解绑', '<div class="note" style="margin-bottom:10px">解绑后这台机器人离开站点，要再输一次你的密码。录像还留着。</div>' + btnrow([B('解绑 A…', 'danger')], 1))
    return board('App-S-robot-set', 'App · 管理员 · 机器人 A 设置', lbar('A · C40221', '待命 · 96%') + body_l(inner) + fold(light=True), light=True, h=1640)


def s_ops():
    kv = lambda k, v, s='sq': f'<div style="display:flex;align-items:center;gap:10px;min-height:40px;border-top:1px solid {L["rule"]}"><span class="{s}"></span><span style="flex:1">{k}</span><b>{v}</b></div>'
    inner = lsec('诊断快照 · 10:18', kv('运行时间', '3 天 4 小时') + kv('温度', '主板 52 °C') + kv('内存可用', '2.1 GB') + kv('存储', '81%', 'tri') + kv('时间同步', '已同步') + kv('证书到期', '2027-05-02') + '<div style="height:10px"></div>' + btnrow([B('对时', sm=True), B('续证书', sm=True), B('复制', sm=True)], 3)) + \
        lsec('服务和日志', ''.join(f'<div style="display:flex;align-items:center;gap:10px;min-height:48px;border-top:1px solid {L["rule"]}"><span class="sq"></span><span style="flex:1">{n}</span>{B("看日志", sm=True)}{B("重启", sm=True)}</div>' for n in ['巡逻程序', '定位', '人员检测', '上装'])) + \
        lsec('详细日志', f'<div style="display:flex;align-items:center;gap:10px"><span style="flex:1">开 1 小时详细日志</span><span class="sw"></span></div>') + \
        lsec('参数', f'<div style="display:grid;grid-template-columns:1fr 120px;gap:8px;align-items:center"><span>前进限速</span><div class="inp">1.0 m/s</div><span>越障许可</span><div class="inp">关</div></div><div style="height:10px"></div>' + btnrow([B('保存参数', 'pri')], 1)) + \
        lsec('重启', '<div class="note" style="margin-bottom:10px">只在空闲时能重启；要再输一次你的密码。</div>' + btnrow([B('重启机器人…', 'danger')], 1))
    return board('App-S-ops', 'App · 管理员 · 远程运维', lbar('远程运维 · A', '机器人报了诊断才有') + body_l(inner) + fold(light=True), light=True, h=1500)


def s_add():
    st = lambda n, t, s, cur=False, done=False: f'<div style="display:flex;gap:12px;padding:12px 0;border-top:1px solid {L["rule"]}"><span style="width:26px;height:26px;flex:none;display:flex;align-items:center;justify-content:center;font-weight:700;border-radius:50%;{"background:"+L["blue"]+";color:#fff" if cur else ("background:"+L["grnsoft"]+";color:"+L["grn"] if done else "border:1.5px solid "+L["mut"]+";color:"+L["sec"])}">{n}</span><div style="flex:1"><b>{t}</b><div class="note">{s}</div></div></div>'
    inner = lsec('添加机器人', st(1, '扫机身贴纸', 'C40388 · 已扫到', done=True) + st(2, '连机器人的热点', '手机会暂时离开现在的网络', cur=True) + st(3, '选机器人要用的 WiFi', '') + st(4, '等它加入站点', '管理员核对码后批准')) + \
        f'''<section style="background:{L['surf']};padding:14px 16px;margin-top:8px;border-bottom:1px solid {L['rule']}"><h2 class="h2">连机器人的热点</h2><div class="note" style="margin:4px 0 12px">在系统弹出的提示里点「连接」。连上后这里会自动往下走。</div>
  <div style="display:flex;gap:10px;align-items:center;padding:10px;border:1px solid {L['rule']};background:{L['bg']}">{ic('wifi',22,L['sec'])}<div style="flex:1"><b>NW-C40388</b><div class="note">正在连接…</div></div></div>
  <div style="height:12px"></div>{btnrow([B('打开系统 WiFi 设置'), B('重扫贴纸')])}</section>
  <div class="note" style="padding:12px 16px">也可以：贴开通码、或者在机器人上用命令行加入（见使用教程）。</div>'''
    return board('App-S-add', 'App · 管理员 · 添加机器人', lbar('添加机器人', '第 2 步，共 4 步') + body_l(inner), light=True)


# ---------- 地图与布置 ----------
def s_layout():
    inner = f'<div style="background:{L["surf"]}">{sitemap(390, 238, light=True)}</div>' + grp('图层', item('shield', '防区', '3 个 · 北区、南区、停车场') + item('close', '禁行区、限速区、虚拟墙', '2 个禁行区 · 已确认', sign='') + item('route', '巡逻路线', 'guard-1、停车场一圈、外围全线') + item('pin', '待命点与原点', '充电桩 1（默认）· 原点已标') + item('cam', '固定摄像头', '3 台 · 都连着') + item('person', '拦截点', '2 个 · 连着 3 个防区')) + \
        grp('地图', item('map', '地图管理与建图', 'estate-1 第 8 版 · A、B 在用') + item('clock', '历史版本', '退回、谁同时在改'))
    return board('App-S-layout', 'App · 管理员 · 地图与布置', lbar('地图与布置', 'estate-1 · 第 8 版') + body_l(inner) + fold(light=True), light=True, h=1080)


def s_routes():
    pts = [(40, 100), (140, 100), (140, 124), (268, 124), (268, 30), (320, 30), (320, 170), (40, 170)]
    ex = ''.join(f'<circle cx="{x}" cy="{y}" r="8" fill="#0B5FA5" stroke="#fff" stroke-width="2"/><text x="{x}" y="{y+3.5}" text-anchor="middle" font-size="9" font-weight="700" fill="#fff" font-family="Barlow">{i+1}</text>' for i, (x, y) in enumerate(pts))
    rows = ''.join(f'<div style="display:grid;grid-template-columns:28px 1fr auto;gap:8px;align-items:center;min-height:48px;border-top:1px solid {L["rule"]}"><b>{i}</b><div><b>{n}</b><div class="note">{d}</div></div>{ic("more",18,L["mut"])}</div>' for i, n, d in [(1, '北门内', '停 10 秒 · 拍前、后'), (2, '2 号楼北', '经过'), (3, '东通道', '经过'), (4, '东门', '停 15 秒 · 看门锁')])
    inner = f'<div style="background:{L["surf"]};position:relative">{sitemap(390, 238, light=True, route=False, path="40,100 140,100 140,124 268,124 268,30 320,30 320,170 40,170 40,100", extra=ex, robots=())}</div>' + \
        lsec('guard-1 · 8 个点', f'<div class="note" style="margin-bottom:6px">点地图加点；拖点换位置；每个点能设停多久、拍哪个摄像头、朝向。</div>' + rows + '<div class="note" style="padding-top:8px">…还有 4 个点</div>') + \
        f'<div style="padding:12px 16px">{btnrow([B("保存路线", "pri"), B("派机器人走一趟")])}<div style="height:8px"></div>{btnrow([B("删除路线", "danger", sm=True)], 1)}</div>'
    return board('App-S-routes', 'App · 管理员 · 巡逻路线', lbar('巡逻路线', 'estate-1 第 8 版', right=B('新建', sm=True)) + body_l(inner) + fold(light=True), light=True, h=1060)


def s_zones():
    ex = f'<rect x="200" y="140" width="70" height="40" fill="rgba(200,16,46,.12)" stroke="#C8102E" stroke-width="1.5"/><text x="235" y="164" text-anchor="middle" font-size="10" fill="#C8102E" font-family="Barlow">禁行 · 配电房</text><polygon points="40,180 80,180 80,196 40,196" fill="none" stroke="#0B5FA5" stroke-width="2" stroke-dasharray="4 2"/>'
    inner = f'<div style="background:{L["surf"]}">{sitemap(390, 238, light=True, route=False, extra=ex, robots=())}</div>' + \
        f'<div style="padding:10px 16px;background:{L["surf"]};border-bottom:1px solid {L["rule"]}"><div class="seg" style="grid-template-columns:repeat(4,1fr)"><button class="on" type="button">禁行区</button><button type="button">限速区</button><button type="button">虚拟墙</button><button type="button">抹掉</button></div></div>' + \
        lsec('正在画：禁行区', '<div class="note" style="margin-bottom:10px">在地图上点顶点，回到第一点结束。</div>' + btnrow([B('撤销上一点', sm=True), B('画完', 'pri', sm=True), B('取消', sm=True)], 3)) + \
        lsec('禁行区 2', f'<div style="display:flex;align-items:center;gap:10px;min-height:44px"><span style="width:14px;height:14px;border:1.5px dashed {L["redt"]}"></span><span style="flex:1">配电房</span><span class="note">一直有效</span></div><div style="display:flex;align-items:center;gap:10px;min-height:44px;border-top:1px solid {L["rule"]}"><span style="width:14px;height:14px;border:1.5px dashed {L["redt"]}"></span><span style="flex:1">施工区</span><span class="note">到 11-20</span></div>') + \
        lsec('确认', f'<div style="display:flex;gap:10px;align-items:center"><span class="sq"></span><span>禁行区已确认 · demo 11-12</span></div><div class="note" style="margin-top:6px">没确认禁行区的图，机器人不会自己出去。</div>')
    return board('App-S-zones', 'App · 管理员 · 禁行区等', lbar('禁行区、限速区、虚拟墙', 'estate-1 第 8 版') + body_l(inner), light=True, h=900)


def s_points():
    inner = lsec('原点', '<div class="note" style="margin-bottom:8px">安全返航、回充用，每张图一个。</div><div style="display:flex;gap:10px;align-items:center;min-height:44px"><span class="sq"></span><span style="flex:1">充电桩 1 前</span>' + B('机器人在这儿就标这儿', sm=True) + '</div>') + \
        lsec('待命点 2', ''.join(f'<div style="display:flex;gap:10px;align-items:center;min-height:52px;border-top:1px solid {L["rule"]}">{ic("pin",20,L["sec"])}<div style="flex:1"><b>{n}</b><div class="note">{d}</div></div>{B(b, sm=True)}</div>' for n, d, b in [('充电桩 1', '默认 · 巡逻完回这里', '改'), ('东门岗亭', '', '设成默认')]) + '<div style="height:10px"></div>' + btnrow([B('在机器人位置加待命点', sm=True)], 1)) + \
        lsec('拦截点 2', ''.join(f'<div style="display:flex;gap:10px;align-items:center;min-height:52px;border-top:1px solid {L["rule"]}">{ic("person",20,L["sec"])}<div style="flex:1"><b>{n}</b><div class="note">{d}</div></div>{B("连防区", sm=True)}</div>' for n, d in [('北门内', '北区、停车场'), ('南墙中段', '南区')])) + \
        lsec('固定摄像头 3', ''.join(f'<div style="display:flex;gap:10px;align-items:center;min-height:44px;border-top:1px solid {L["rule"]}"><span class="sq"></span><span style="flex:1">{n}</span><span class="note">{d}</span></div>' for n, d in [('摄像头 1 · 大门', '最近：21:02 有人'), ('摄像头 2 · 停车场', '最近：无'), ('摄像头 3 · 北门', '最近：23:47 有人')]))
    return board('App-S-points', 'App · 管理员 · 待命点、拦截点、摄像头', lbar('待命点、拦截点、摄像头', 'estate-1 第 8 版') + body_l(inner) + fold(light=True), light=True, h=1200)


def s_maps():
    v = lambda n, s, b, cur=False: f'<div style="display:flex;gap:10px;align-items:center;min-height:56px;border-top:1px solid {L["rule"]}">{"<span class=sq></span>" if cur else "<span class=p3></span>"}<div style="flex:1"><b>{n}</b><div class="note">{s}</div></div>{b}</div>'
    inner = lsec('estate-1', v('第 8 版 · 11-12', '建图结论：能用 · A、B 在用', B('下发到…', sm=True), True) + v('第 7 版 · 11-02', '能用 · 没人用', B('删除', sm=True)) + v('第 6 版 · 10-28', '有问题：玻璃多', B('删除', sm=True)) + '<div style="height:10px"></div>' + btnrow([B('建新版本', 'pri'), B('看图')])) + \
        lsec('哪台用哪版', '<div style="display:grid;grid-template-columns:40px 1fr auto;gap:8px;align-items:center;min-height:44px"><b>A</b><span>第 8 版</span>' + B('退回上一版', sm=True) + f'</div><div style="display:grid;grid-template-columns:40px 1fr auto;gap:8px;align-items:center;min-height:44px;border-top:1px solid {L["rule"]}"><b>B</b><span>第 8 版</span>' + B('退回上一版', sm=True) + '</div>') + \
        grp('工程师', item('doc', '建图录包', '录包、拿录包重建'))
    return board('App-S-maps', 'App · 管理员 · 地图管理', lbar('地图管理', '每张图的版本') + body_l(inner), light=True)


def s_wizard():
    stepper = '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:3px">' + ''.join(f'<div style="height:4px;background:{L["blue"] if i<3 else L["rule"]}"></div>' for i in range(7)) + '</div>'
    inner = f'''<div style="padding:12px 16px;background:{L['surf']};border-bottom:1px solid {L['rule']}">{stepper}<div class="note" style="margin-top:6px">准备 · 怎么开 · <b style="color:{L['tx']}">走一圈</b> · 建图 · 看结果 · 标原点 · 禁行区</div></div>
  <div style="background:#0E1013">{sitemap(390, 260, route=False, robots=(('A', 150, 120, True),), path='300,180 300,120 220,120 150,120')}</div>
  <div style="display:flex;align-items:center;gap:10px;padding:10px 16px;background:{L['surf']};border-bottom:1px solid {L['rule']}"><span class="sq"></span><span style="flex:1">在录 · 6 分 12 秒 · 走了 214 米</span><b>A 71%</b></div>''' + \
        lsec('走一圈', '<div class="note">用遥控器低速档，把要巡逻的地方都走到，最后回到起点让图闭合。</div><div style="display:flex;gap:10px;align-items:center;margin-top:10px"><span class="p3"></span><span>还没回到起点</span></div><div style="height:12px"></div>' + btnrow([B('走完了', 'pri'), B('暂停')]) + '<div style="height:8px"></div>' + btnrow([B('用手机遥控', sm=True), B('放弃建图', 'danger', sm=True)]))
    return board('App-S-wizard', 'App · 管理员 · 建图向导', lbar('建图', '第 3 步，共 7 步') + body_l(inner), light=True)


# ---------- 布防与巡逻 ----------
def s_arming():
    inner = lsec('现在', f'<div class="seg" style="grid-template-columns:repeat(3,1fr)"><button type="button">布防</button><button type="button">留守</button><button class="on" type="button">撤防</button></div><div class="note" style="margin-top:8px">撤防 · 19:00 按时间表自动布防。入侵来了：撤防时只记录，不派机器人、不响。</div>') + \
        lsec('临时撤防', '<div class="note" style="margin-bottom:10px">某个防区先撤防一段时间，到点自己恢复。</div>' + btnrow([B('按防区临时撤防…')], 1)) + \
        lsec('布防时间表', ''.join(f'<div style="display:flex;gap:10px;align-items:center;min-height:44px;border-top:1px solid {L["rule"]}"><span style="flex:1">{d}</span><b>{t}</b></div>' for d, t in [('周一至周五', '19:00 → 07:00'), ('周六、周日', '全天'), ('例外 · 11-20', '施工，22:00 才布防')]) + '<div style="height:10px"></div>' + btnrow([B('改时间表', sm=True), B('加例外', sm=True)])) + \
        lsec('天气', '<div style="display:flex;gap:10px;align-items:center"><span class="sq"></span><span style="flex:1">正常 · 自动</span>' + B('手动设', sm=True) + '</div><div class="note" style="margin-top:6px">下雨照常巡逻；雷暴时日程巡逻暂停。</div>') + \
        grp('巡逻', item('clock', '巡逻日程', '每晚 4 轮 · guard-1') + item('shield', '布防时巡逻', '布防时每 3 小时一轮') + item('bell', '报警演练', '试一次报警，看手机响不响'))
    return board('App-S-arming', 'App · 布防与巡逻', lbar('布防与巡逻', '撤防 · 19:00 布防') + body_l(inner) + fold(light=True), light=True, h=1200)


def s_schedule():
    days = '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px">' + ''.join(f'<span style="height:32px;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:13px;{"background:"+L["blue"]+";color:#fff" if on else "border:1px solid "+L["line"]}">{d}</span>' for d, on in zip('一二三四五六日', [1, 1, 1, 1, 1, 0, 0])) + '</div>'
    row = lambda t, r, rb, d: f'<div style="display:flex;gap:10px;align-items:center;min-height:56px;border-top:1px solid {L["rule"]}"><b style="width:52px">{t}</b><div style="flex:1"><b>{r}</b><div class="note">{rb} · {d}</div></div>{ic("chev",18,L["mut"])}</div>'
    inner = f'<div style="padding:10px 16px;background:{L["surf"]};border-bottom:1px solid {L["rule"]}"><div class="seg" style="grid-template-columns:1fr 1fr"><button type="button">今天</button><button class="on" type="button">每周</button></div></div>' + \
        lsec('夜巡', row('19:00', 'guard-1', 'A', '每天') + row('22:00', 'guard-1', 'A', '每天') + row('01:00', 'guard-1', '哪台空就哪台', '每天') + row('04:00', 'guard-1', 'A', '每天')) + \
        lsec('编辑：01:00 夜巡', '<div style="display:grid;gap:10px"><div><div class="lbl" style="margin-bottom:4px">几点</div><div class="inp">01:00</div></div><div><div class="lbl" style="margin-bottom:4px">哪几天</div>' + days + '</div><div><div class="lbl" style="margin-bottom:4px">路线 · 机器人</div><div class="row" style="grid-template-columns:1fr 1fr"><div class="inp">guard-1</div><div class="inp">哪台空就哪台</div></div></div><div class="note">每趟约 14 分钟（含返回）。</div></div><div style="height:12px"></div>' + btnrow([B('保存', 'pri'), B('删除', 'danger')])) + \
        f'<div style="padding:12px 16px">{btnrow([B("添加日程", icon="plus")], 1)}</div>'
    return board('App-S-schedule', 'App · 巡逻日程', lbar('巡逻日程', '每晚 4 轮') + body_l(inner) + fold(light=True), light=True, h=1150)


# ---------- 人员、体检、升级、设置、报问题、帮助 ----------
def s_people():
    u = lambda n, r, s: f'<a href="#" class="li" style="background:{L["surf"]}">{ic("person",20,L["sec"])}<div class="b"><b>{n}</b><div class="s">{r}</div></div><span class="note">{s}</span>{ic("chev",18,L["mut"])}</a>'
    inner = lsec('等批准 1', '<div style="display:flex;gap:10px"><span class="discb" style="margin-top:5px"></span><div style="flex:1"><b>vic</b><div class="note">申请只读 · 08:12 · 从手机 App 申请</div></div></div><div style="height:10px"></div>' + btnrow([B('批准', 'pri'), B('拒绝')])) + \
        '<div class="lbl" style="padding:14px 16px 6px">全部账号 6</div>' + u('demo', '管理员', '这台手机') + u('olga', '经理', '2 部手机') + u('gina', '保安', '1 部手机') + u('ali', '保安', '已停用') + u('eng-temp', '工程师（临时）', '到 11-16 18:00') + \
        f'<div style="padding:12px 16px">{btnrow([B("添加账号", icon="plus"), B("工程师临时账号…")])}</div>'
    return board('App-S-people', 'App · 管理员 · 人员', lbar('人员', '6 个账号 · 1 个待批准') + body_l(inner), light=True)


def s_health():
    c = lambda s, n, v: f'<div style="display:flex;gap:10px;align-items:center;min-height:40px;border-top:1px solid {L["rule"]}"><span class="{s}"></span><span style="flex:1">{n}</span><span class="note">{v}</span></div>'
    inner = lsec('站点', '<div style="display:flex;gap:10px;align-items:center;margin-bottom:6px"><span class="tri"></span><b>有 1 项要看</b></div>' + c('sq', '数据库', '正常') + c('sq', '磁盘', '41%') + c('tri', '备份', '上次 3 天前') + c('sq', '证书', '到 2027-05') + c('sq', '推送', '3 部手机能收') + c('sq', '网页控制台', '正常')) + \
        lsec('版本是否配套', c('sq', '站点', '2.8.1') + c('sq', 'A', '2.8.1') + c('sq', 'B', '2.8.1') + c('tri', 'olga 的手机 App', '2.7.9，比站点旧')) + \
        lsec('诊断包', '<div class="note" style="margin-bottom:10px">打包站点和机器人的日志，存到手机或分享给厂家。</div>' + btnrow([B('存诊断包'), B('分享…')]))
    return board('App-S-health', 'App · 管理员 · 站点体检', lbar('站点体检', '有 1 项要看', right=B('刷新', sm=True)) + body_l(inner) + fold(light=True), light=True, h=1000)


def s_updates():
    inner = lsec('站点上的版本', ''.join(f'<div style="display:flex;gap:10px;align-items:center;min-height:56px;border-top:1px solid {L["rule"]}">{"<span class=sq></span>" if cur else "<span class=discb></span>"}<div style="flex:1"><b>{v}</b><div class="note">{s}</div></div>{b}</div>' for v, s, b, cur in [('2.8.2', '11-14 上传 · 包完整 · 还没装', B('装到机器人…', 'pri', sm=True), False), ('2.8.1', 'A、B 在跑', '', True), ('2.8.0', '', B('退回到这版', sm=True), True)])) + \
        lsec('每台在跑', '<div style="display:grid;grid-template-columns:40px 1fr auto;gap:8px;align-items:center;min-height:40px"><b>A</b><span>2.8.1</span><span class="note">空闲才能装</span></div>' + f'<div style="display:grid;grid-template-columns:40px 1fr auto;gap:8px;align-items:center;min-height:40px;border-top:1px solid {L["rule"]}"><b>B</b><span>2.8.1</span><span class="note">充电中</span></div>') + \
        lsec('手机 App', '<div style="display:flex;gap:10px;align-items:center"><span class="sq"></span><span style="flex:1">这台手机 2.8.1 · 已是最新</span>' + B('检查更新', sm=True) + '</div>')
    return board('App-S-updates', 'App · 管理员 · 软件升级', lbar('软件升级', '有 1 个新版本') + body_l(inner), light=True)


def s_settings():
    sw = lambda t, s, on: f'<div style="display:flex;gap:10px;align-items:center;min-height:56px;border-top:1px solid {L["rule"]}"><div style="flex:1"><b>{t}</b>{f"<div class=note>{s}</div>" if s else ""}</div><span class="sw {"on" if on else ""}"></span></div>'
    inner = lsec('通用', f'<div class="lbl" style="margin-bottom:6px">语言</div><div class="seg" style="grid-template-columns:1fr 1fr"><button class="on" type="button">English</button><button type="button">中文</button></div><div class="lbl" style="margin:12px 0 6px">外观</div><div class="seg" style="grid-template-columns:repeat(3,1fr)"><button class="on" type="button">按页面</button><button type="button">深色</button><button type="button">浅色</button></div><div class="note" style="margin-top:6px">按页面：「现在」深色，设置类浅色。</div>') + \
        lsec('通知与值守', sw('后台值守', 'App 退到后台、被划掉也连着站点，P1 一直响到有人处理', True) + sw('P1 推送', '已就绪 · 这台手机能收', True) + f'<div style="display:flex;gap:10px;align-items:center;min-height:56px;border-top:1px solid {L["rule"]}"><div style="flex:1"><b>报警声音</b><div class="note">闹钟声 · 跟着系统音量</div></div>{B("试听", sm=True)}</div>' + sw('巡逻到点提醒', '现场测试用，App 重启就关', False)) + \
        lsec('关于与更新', f'<div style="display:flex;gap:10px;align-items:center;min-height:44px"><span style="flex:1">App 版本 2.8.1（构建 21）</span>{B("检查更新", sm=True)}</div>' + item(None, '开源许可').replace('class="li"', 'class="li" style="padding:8px 0"')) + \
        lsec('工程师工具', item(None, '用解绑令解绑机器人', '给安装工程师用').replace('class="li"', 'class="li" style="padding:8px 0"'))
    return board('App-S-settings', 'App · 设置', lbar('设置') + body_l(inner) + fold(light=True), light=True, h=1080)


def s_report():
    inner = lsec('报问题', f'<div class="lbl" style="margin-bottom:6px">出了什么事</div><div class="inp" style="height:100px;align-items:flex-start;padding-top:10px">B 回桩后没开始充电，指示灯一直闪。</div><div class="lbl" style="margin:12px 0 6px">哪台机器人（可不选）</div><div class="seg" style="grid-template-columns:repeat(3,1fr)"><button type="button">A</button><button class="on" type="button">B</button><button type="button">不是机器人</button></div><div class="note" style="margin-top:10px">会把这台手机的 App 日志、型号、版本一起发给站点，开一张问题单。</div><div style="height:12px"></div>' + btnrow([B('发送', 'pri')], 1)) + \
        lsec('站点连不上时', '<div class="note" style="margin-bottom:10px">用手机分享日志文件给工程师。</div>' + btnrow([B('分享日志…', sm=True), B('只发 App 日志', sm=True)]))
    return board('App-S-report', 'App · 报问题', lbar('报问题', '登录页也能进') + body_l(inner), light=True)


def s_help():
    inner = grp('上手', item('play', '值班页导览', '在真页面上走一遍：现在、这件事、急停') + item('bell', '报警演练', '试一次报警，看手机响不响、怎么处理')) + \
        grp('怎么做', item(None, '收到报警怎么处理') + item(None, '怎么派巡逻、遥控、急停') + item(None, '怎么找录像') + item(None, '怎么加账号')) + \
        grp('常见问题', item(None, '为什么我的巡逻在排队？') + item(None, '机器人离线了怎么办？') + item(None, '误报和确认有人有什么区别？') + item(None, '布防和天气怎么影响巡逻？'))
    return board('App-S-help', 'App · 使用教程与常见问题', lbar('使用教程与常见问题') + body_l(inner), light=True, h=900)


# ---------- 进入（深色） ----------
def e_sites():
    card = lambda n, a, u, s: f'<a href="#" style="display:block;padding:14px 16px;border:1px solid {D["rule"]};background:{D["surf"]};color:{D["tx"]};text-decoration:none;margin-bottom:10px"><div style="display:flex;align-items:center;gap:8px"><b style="font-size:18px;flex:1">{n}</b>{s}{ic("chev",18,D["mut"])}</div><div class="note">{a}</div><div class="note">{u}</div></a>'
    body = f'''<header style="padding:24px 16px 12px;display:flex;align-items:flex-end;gap:10px"><div style="flex:1"><div style="font-size:12px;letter-spacing:.14em;font-weight:700;color:{D['sec']}">NEXUS WARDEN</div><h1 class="h1" style="font-size:26px;line-height:32px">选站点</h1></div><button class="btn sm" type="button" aria-label="设置" style="width:44px;padding:0">{ic('gear',20)}</button></header>
<div style="flex:1;padding:8px 16px">{card('estate-1', 'gina · 保安', 'https://192.168.5.12:8520', '<span class="chip c-bad"><span class="ring" style="width:10px;height:10px;border-width:2px"></span>1</span>')}{card('东门花园', 'olga · 经理', 'https://10.0.8.20:8520', '')}
<div class="note" style="margin-top:8px">口令不存在手机上，每次登录输。</div></div>
<div style="padding:16px">{btnrow([B('扫码添加站点', 'pri', icon='scan'), B('报问题')])}</div>'''
    return board('App-E-sites', 'App · 进入 · 选站点', body)


def e_login():
    body = appbar('estate-1', 'https://192.168.5.12:8520') + f'''<div style="flex:1;padding:24px 16px;display:flex;flex-direction:column;gap:14px">
  <div><div class="lbl" style="margin-bottom:6px">账号</div><div class="inp">gina</div></div>
  <div><div class="lbl" style="margin-bottom:6px">密码</div><div class="inp">••••••••••</div></div>
  {btnrow([B('登录', 'pri')], 1)}
  <div style="display:flex;gap:10px;align-items:flex-start;padding:10px;border:1px solid {D['amb']};background:{D['ambsoft']}"><span class="tri" style="margin-top:4px"></span><span style="font-size:14px">站点证书换了。确认是你们的站点再扫新码，否则别登录。</span></div>
  {btnrow([B('扫新码', sm=True), B('站点的其他地址…', sm=True)])}
  <div style="flex:1"></div>
  {btnrow([B('申请账号', sm=True), B('报问题', sm=True)])}</div>'''
    return board('App-E-login', 'App · 进入 · 登录', body)


def e_add():
    body = appbar('添加站点', '扫值班台「维护 → 站点」上的二维码') + f'''<div style="flex:1;padding:16px;display:flex;flex-direction:column;gap:12px">
  <div style="position:relative;height:300px;background:#000"><div style="position:absolute;left:70px;right:70px;top:40px;bottom:40px;border:3px solid #ECEDEA"></div><div class="note" style="position:absolute;left:0;right:0;bottom:10px;text-align:center">对准二维码</div></div>
  {btnrow([B('贴配对码', sm=True), B('手动填地址', sm=True)])}
  <div class="lbl">扫到以后</div>
  <div style="display:grid;grid-template-columns:80px 1fr;gap:6px"><span class="mut">站点</span><b>estate-1</b><span class="mut">地址</span><span>https://192.168.5.12:8520</span><span class="mut">证书指纹</span><span>ab:3f:…:91 · 已核对</span></div>
  <div><div class="lbl" style="margin-bottom:6px">账号</div><div class="inp">gina</div></div>
  {btnrow([B('保存并登录', 'pri')], 1)}</div>'''
    return board('App-E-add', 'App · 进入 · 添加站点', body)


def e_register():
    body = appbar('申请账号', 'estate-1') + f'''<div style="flex:1;padding:16px;display:flex;flex-direction:column;gap:14px">
  <div class="note">管理员批准后才能登录。批准前这台手机收不到报警。</div>
  <div><div class="lbl" style="margin-bottom:6px">账号名（字母、数字）</div><div class="inp">vic</div></div>
  <div><div class="lbl" style="margin-bottom:6px">密码</div><div class="inp">••••••••••</div></div>
  <div><div class="lbl" style="margin-bottom:6px">申请的权限</div><div class="seg" style="grid-template-columns:repeat(3,1fr)"><button type="button">保安</button><button type="button">经理</button><button class="on" type="button">只读</button></div></div>
  {btnrow([B('发送申请', 'pri')], 1)}
  <div style="display:flex;gap:10px;align-items:center;padding:12px;border:1px solid {D['rule']}"><span class="discb"></span><span>已发送 08:12 · 等管理员批准</span></div></div>'''
    return board('App-E-register', 'App · 进入 · 申请账号', body)


ALL = [e_sites, e_login, e_add, e_register, s_admin, s_guard, s_mgr, s_viewer, s_home, s_home_m, s_alarms, s_alarm_rec, s_video, s_runs, s_notes,
       s_robots, s_robot_set, s_ops, s_add, s_layout, s_zones, s_routes, s_points, s_maps, s_wizard, s_arming, s_schedule, s_people, s_health, s_updates, s_settings, s_report, s_help]

if __name__ == '__main__':
    import json
    out = [f() for f in ALL]
    json.dump(out, open('site_boards.json', 'w'), ensure_ascii=False)
    print(len(out))

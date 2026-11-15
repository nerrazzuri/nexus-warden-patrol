# 「现在」层：这件事、多件、急停后、派去看一眼、临时路线、单台控制、派巡逻、遥控、经理、只读、来电式报警
from ac import *
from now import T, robot_tiles, tonight, sec, map_block, incident_strip, ops_p2, lastnote

STEPS = ['发现', '接手', '派遣', '到场', '确认', '结案']


def steps(done):
    cells = ''
    for i, s in enumerate(STEPS):
        st = 'done' if i < done else ('cur' if i == done else 'todo')
        bar = T['blue'] if st != 'todo' else T['rule']
        col = T['tx'] if st != 'todo' else T['mut']
        cells += f'<div style="min-width:0"><div style="height:4px;background:{bar}"></div><div style="font-size:12px;font-weight:{700 if st=="cur" else 600};color:{col};margin-top:4px;text-align:center">{s}</div></div>'
    return f'<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:3px">{cells}</div>'


def group(title, sub, rows):
    return f'''<section style="padding:14px 16px;border-bottom:1px solid {T['rule']}">
  <h2 class="h2">{title}</h2>{f'<div class="note" style="margin-bottom:10px">{sub}</div>' if sub else '<div style="height:10px"></div>'}{rows}</section>'''


def inc_head(owner_line, done, manager=False):
    return f'''<div style="padding:12px 16px;border-bottom:1px solid {T['rule']};background:{T['surf']};box-shadow:inset 0 0 0 4px {T['red']}">
  <div style="display:flex;gap:12px;align-items:flex-start"><span class="ring lg" style="margin-top:2px"></span>
  <div style="flex:1;min-width:0"><div style="display:flex;align-items:baseline;gap:8px"><b style="font-size:20px;line-height:26px">北门有人翻越</b><span class="chip c-bad" style="height:20px;font-size:12px">P1</span></div>
  <div class="note">北区 北门 · 摄像头 3 · 23:47:12 · 往 2 号楼方向</div>
  <div style="margin-top:4px;font-weight:600">{owner_line}</div></div></div>
  <div style="margin-top:12px">{steps(done)}</div></div>'''


def n_incident(name='App-N-incident', title='App · 保安 · 这件事（处理中）'):
    H = 2200
    body = appbar('这件事', '23:47 发现 · 已过 3 分钟') + inc_head('gina 23:48 接手 · A 正在跟随，距离 4.6 米', 3) + f'''
<div style="flex:1;min-height:0">
  <a href="#" style="display:flex;gap:6px;align-items:center;padding:8px 16px;border-bottom:1px solid {T['rule']};color:{T['tx']};text-decoration:none">{''.join('<span style="width:56px;height:40px;background:#000;flex:none"></span>' for _ in range(3))}<span style="flex:1;padding-left:6px"><b>现场照片 3 张</b><div class="note">摄像头 3 · 23:47</div></span>{ic('chev',18,T['mut'])}</a>
  {video(210, cap='A · 前摄像头 · 跟随中', tabs=('A 前', '事件', '热像'), on='A 前', overlay='<div style="position:absolute;left:40%;top:34%;width:52px;height:90px;border:2px solid #FF6166"></div>')}
  <div style="display:flex;gap:8px;padding:8px 16px;border-bottom:1px solid {T['rule']}">{B('−30 秒回放', sm=True)}{B('截图', sm=True)}<span style="flex:1"></span>{B('全屏', sm=True, icon='expand')}</div>
  <div style="padding:12px 16px;border-bottom:1px solid {T['rule']}">{map_block(219, alarm=True, tools=False, robots=(('A', 104, 38, True), ('B', 300, 168, False)), path='214,70 150,60 104,38')}</div>
  {group('派机器人', 'A 28%，来回约用 6%，够', '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><span class="sq"></span><b>A 已到北门 · 跟随中，距离 4.6 米</b></div>' + btnrow([B('让 A 停下守着', sm=True), B('改派 B', sm=True)]))}
  {group('现场警示 · 用 A 的喇叭和警灯', '对着闯入的人；警灯和喊话一起用效果最好', f'<div style="display:flex;gap:8px;align-items:center;padding:10px;border:1px solid {T["rule"]};margin-bottom:10px"><span class="tri"></span><div style="flex:1"><b>自动驱离：第 2 级 语音警告</b><div class="note">观察 → 灯光 → 语音（中、英、马来文轮放）→ 警笛</div></div>{B("结束驱离", sm=True)}</div>' + btnrow([B('喊话：请离开', icon='speaker'), B('开警灯 30 秒', icon='light')]) + '<div style="height:8px"></div>' + btnrow([B('警笛 10 秒', sm=True), B('说一句…', sm=True), B('全部关', sm=True)]))}
  {group('通知', '', btnrow([B('请求支援', icon='bell'), B('已到场', icon='person')]) + '<div class="note" style="margin-top:8px">请求支援会推给经理和管理员；已到场写进经过。</div>')}
  {group('结论', '定了结论才能结案', btnrow([B('确认有人', extra=f'background:{T["sel"]};border-color:{T["blue"]};box-shadow:inset 0 0 0 1px {T["blue"]}'), B('误报'), B('其他')]) + f'<div class="inp" style="margin-top:10px;height:72px;align-items:flex-start;padding-top:10px;color:{T["mut"]}">备注（给下一班看，可不写）</div>' + '<div style="height:10px"></div>' + btnrow([B('结案', 'pri')], 1))}
  {group('经过', '', ''.join(f'<div style="display:grid;grid-template-columns:64px 1fr;gap:8px;min-height:32px"><span class="mut">{a}</span><span>{b}</span></div>' for a,b in [('23:47:12','摄像头 3 发现有人翻越北门'),('23:47:20','派 A 去北门（自动）'),('23:48:05','gina 接手'),('23:49:31','A 到北门，开始跟随'),('23:49:40','gina 喊话：请离开')]))}
</div>''' + estop_fab(top=844 - 116) + fold()
    return board(name, title, body, h=H)


def n_multi(name='App-N-multi', title='App · 保安 · 同时两件 P1'):
    def strip(t1, t2, t3, owner, cur=False):
        return f'''<a href="#" style="display:block;margin:0 16px 10px;border:4px solid {T['red']};background:{T['surf']};padding:12px;color:{T['tx']};text-decoration:none">
  <div style="display:flex;gap:12px"><span class="ring lg"></span><div style="flex:1;min-width:0"><b style="font-size:18px">{t1}</b><div class="note">{t2}</div><div style="font-weight:600;margin-top:2px;{'color:'+T['redt'] if not owner else ''}">{t3}</div></div>{ic('chev',20,T['mut'])}</div>
  {'' if owner else f'<div class="row" style="grid-template-columns:1fr;margin-top:10px">{B("我来处理", "pri", icon="disc")}</div>'}</a>'''
    body = topbar(clock='23:52', open_n=4) + f'''
<div style="flex:1;min-height:0;padding-top:12px">
  <div style="padding:0 16px 10px;display:flex;align-items:center;gap:8px"><span class="ring"></span><b>2 件安全事件同时在处理</b><span style="flex:1"></span><span class="note">按发现时间</span></div>
  {strip('北门有人翻越', '北区 北门 · 摄像头 3 · 23:47', 'gina 在处理 · A 跟随中', True)}
  {strip('南墙有人靠近', '南区 · B 前摄像头 · 23:51', '没人接手 · 40 秒', False)}
  <div style="padding:4px 16px 12px;border-bottom:1px solid {T['rule']}">{map_block(219, alarm=True, tools=False, robots=(('A', 104, 38, False), ('B', 300, 168, False)), path=None)}</div>
  <section><div style="padding:14px 16px 4px"><h2 class="h2">设备与运营 2</h2></div>
  <a href="#" class="li"><span class="ring"></span><div class="b"><div style="font-weight:600">B 等待换电</div><div class="s">充电桩 1 · 23:31 · olga 处理中</div></div>{ic('chev',18,T['mut'])}</a>
  <a href="#" class="li"><span class="tri"></span><div class="b"><div style="font-weight:600">A 电量低于 30%</div><div class="s">23:12</div></div>{ic('chev',18,T['mut'])}</a></section>
</div>''' + estop_fab()
    return board(name, title, body)


def n_estop(name='App-N-estop', title='App · 保安 · 全部急停后'):
    body = topbar(clock='23:41', arm='布防中 · 2 台已急停', armsign='ring') + f'''
<div style="flex:1;min-height:0">
  <section style="margin:12px 16px;border:4px solid {T['red']};background:{T['surf']};padding:12px">
    <div style="display:flex;gap:12px"><span class="ring lg"></span><div style="flex:1"><b style="font-size:20px;line-height:26px">2 台机器人已急停</b><div class="note">gina 23:40 按的。恢复后不会自己接着跑，要再派。</div></div></div>
    <div style="margin-top:12px;padding:12px;border:1px solid {T['rule']};background:{T['bg']}">
      <b>确认全部恢复？</b><div class="note" style="margin:4px 0 10px">A 停在北区通道，B 在充电桩 1。恢复后两台都回到待命，巡逻要重新派。</div>
      {btnrow([B('确认恢复', 'pri'), B('先不恢复')])}</div></section>
  <div style="padding:0 16px 12px;border-bottom:1px solid {T['rule']}">{robot_tiles(a=('ring', '已急停', '62%', '停在北区通道 · guard-1 第 3 圈中断'), b=('ring', '已急停', '18%', '在充电桩 1 · 充电照常'))}</div>
  {video(200, cap='A · 前摄像头')}
</div>''' + estop_fab(label='全部急停')
    return board(name, title, body)


def n_spot(name='App-N-spot', title='App · 保安 · 派去看一眼'):
    body = appbar('派去看一眼', '在地图上点要看的位置，可以再点别处换位置', right=B('退出', sm=True)) + f'''
<div style="flex:1;min-height:0;position:relative">
  {sitemap(390, 430, pick=(70, 150), robots=(('A', 214, 70, False), ('B', 300, 168, False)))}
  <div style="position:absolute;right:12px;top:12px;display:flex;flex-direction:column;gap:6px">{''.join(f'<button class="btn sm" type="button" aria-label="{a}" style="width:44px;padding:0;box-shadow:0 2px 8px rgba(0,0,0,.3)">{b}</button>' for a,b in [('放大','+'),('缩小','−'),('回正',ic('home',18))])}</div>
  <section style="position:absolute;left:0;right:0;bottom:0;background:{T['surf']};border-top:1px solid {T['rule']};padding:14px 16px 20px;box-shadow:0 -8px 24px rgba(0,0,0,.3)">
    <div style="width:36px;height:4px;background:{T['rule']};margin:0 auto 12px"></div>
    <div style="display:flex;align-items:center;gap:8px"><span class="discb"></span><b style="font-size:18px">停车场北侧</b></div>
    <div class="note" style="margin:2px 0 12px">机器人能走到 · 离 A 约 60 米</div>
    <div class="lbl" style="margin-bottom:6px">派哪台</div>
    <a href="#" class="li" style="border:1px solid {T['blue']};background:{T['sel']};padding:8px 12px;min-height:52px"><span class="sq"></span><div class="b"><b>最近的：A · 约 2 分钟到</b><div class="s">A 会先暂停 guard-1 第 3 圈</div></div></a>
    <a href="#" class="li" style="border:1px solid {T['rule']};border-top:0;padding:8px 12px;min-height:52px"><span class="tri"></span><div class="b"><b>B · 在充电，18%</b></div></a>
    <div class="lbl" style="margin:12px 0 6px">看完以后</div>
    <div class="seg" style="grid-template-columns:1fr 1fr"><button class="on" type="button">接着巡逻</button><button type="button">回待命点</button></div>
    <div style="height:12px"></div>{btnrow([B('派 A 过去', 'pri'), B('取消')])}
    <div class="note" style="margin-top:8px">到了以后在「现在」的画面里看；不会产生报警。</div>
  </section>
</div>'''
    return board(name, title, body)


def n_route(name='App-N-route', title='App · 保安 · 临时路线'):
    pts = [(80, 150), (150, 150), (150, 196), (250, 196)]
    extra = ''.join(f'<circle cx="{x}" cy="{y}" r="9" fill="#1F6FC0" stroke="#fff" stroke-width="2"/><text x="{x}" y="{y+4}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff" font-family="Barlow">{i+1}</text>' for i, (x, y) in enumerate(pts))
    extra += f'<circle cx="340" cy="100" r="9" fill="none" stroke="{T["amb"]}" stroke-width="2.5" stroke-dasharray="3 2"/><text x="326" y="88" font-size="10" fill="{T["ambt"]}" font-family="Barlow" text-anchor="end">走不到</text>'
    body = appbar('临时路线', '按顺序点几个点，只走一次，不保存', right=B('退出', sm=True)) + f'''
<div style="flex:1;min-height:0;position:relative">
  {sitemap(390, 400, path='214,70 80,150 150,150 150,196 250,196', extra=extra)}
  <section style="position:absolute;left:0;right:0;bottom:0;background:{T['surf']};border-top:1px solid {T['rule']};padding:14px 16px 20px">
    <div style="width:36px;height:4px;background:{T['rule']};margin:0 auto 12px"></div>
    <div style="display:flex;align-items:center"><b style="font-size:18px;flex:1">4 个点 · 约 6 分钟</b>{B('撤销上一个点', sm=True)}</div>
    <div class="note" style="margin:2px 0 10px">1 停车场北 → 2 停车场中 → 3 停车场南 → 4 东通道</div>
    <div style="display:flex;gap:8px;align-items:flex-start;padding:10px;border:1px solid {T['amb']};background:{T['ambsoft']};margin-bottom:12px"><span class="tri" style="margin-top:4px"></span><span style="font-size:14px">刚才点的东墙外那一处机器人走不到，没加进去。</span></div>
    <div class="lbl" style="margin-bottom:6px">派哪台 · 走完以后</div>
    <div class="row" style="grid-template-columns:1fr 1fr">{B('A · 约 1 分钟到起点', extra=f'background:{T["sel"]};border-color:{T["blue"]}')}{B('B · 充电中 18%')}</div>
    <div style="height:8px"></div><div class="seg" style="grid-template-columns:1fr 1fr"><button class="on" type="button">回待命点</button><button type="button">接着原来的巡逻</button></div>
    <div style="height:12px"></div>{btnrow([B('派 A 走一次', 'pri'), B('取消')])}
  </section>
</div>'''
    return board(name, title, body)


def dpad():
    cells = []
    for l, k in [('', None), ('云台上', 'up'), ('', None), ('云台左', 'back'), ('回中', 'home'), ('云台右', 'chev'), ('', None), ('云台下', 'down'), ('', None)]:
        cells.append(f'<button class="btn" type="button" aria-label="{l}" style="width:52px;height:52px;padding:0">{ic(k, 20)}</button>' if l else '<span></span>')
    return '<div style="display:grid;grid-template-columns:repeat(3,52px);gap:6px">' + ''.join(cells) + '</div>'


def pad(lbl, inner):
    return f'<div><div class="lbl" style="margin-bottom:6px">{lbl}</div>{inner}</div>'


def n_robot(name='App-N-robot', title='App · 保安 · 机器人 A 控制', manager=False):
    H = 2120 if not manager else 1300
    dp = dpad
    head = f'''<div style="display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid {T['rule']}"><span class="sq" style="width:12px;height:12px"></span><div style="flex:1"><b style="font-size:17px">巡逻中 · guard-1 第 3 圈</b><div class="note">北区 · 定位好 · 走完约 23:58 · 电量 62%</div></div></div>'''
    move = group('任务', '', btnrow([B('派巡逻…', 'pri', icon='route'), B('原地停下', icon='pause')]) + '<div style="height:8px"></div>' + btnrow([B('回待命点', sm=True), B('回原点', sm=True)]) + '<div style="height:8px"></div>' + btnrow([B('中止并回原点…', sm=True)], 1))
    if manager:
        body = appbar('A · C40221', '经理只看状态和派巡逻') + head + f'''<div style="flex:1;min-height:0">{video(210)}
  {group('任务', '', btnrow([B('派巡逻…', 'pri', icon='route'), B('原地停下', icon='pause')]))}
  {group('今晚', '', tonight())}
  <section style="padding:14px 16px"><div class="note">遥控、喊话、警灯、云台由保安和管理员操作。</div></section></div>''' + estop_fab(top=844 - 116) + fold()
        return board(name, title, body, h=H)
    body = appbar('A · C40221', '巡逻中 · 62%', right=f'<button class="btn sm" type="button" aria-label="更多" style="width:44px;padding:0">{ic("more",20)}</button>') + head + f'''
<div style="flex:1;min-height:0">
  {video(210)}
  {move}
  {group('遥控与姿态', '遥控只能横屏；离开这一页机器人就停', btnrow([B('遥控', icon='robot'), B('站起', icon='stand'), B('趴下', sm=False)]) + '<div style="height:8px"></div>' + btnrow([B('重新定位', sm=True), B('协助定位…', sm=True)]))}
  {group('云台与镜头', '', f'<div style="display:flex;gap:16px;align-items:flex-start">{dp()}<div style="flex:1;display:flex;flex-direction:column;gap:8px">{B("雨刷", sm=True)}{B("预置位：北门", sm=True)}{B("编辑预置位", sm=True)}</div></div>')}
  {group('喊话', '常用话全站共用；说一句会用选的语言', f'<div class="seg" style="grid-template-columns:repeat(3,1fr);margin-bottom:8px"><button class="on" type="button">英文</button><button type="button">中文</button><button type="button">马来文</button></div>' + btnrow([B('请离开', sm=True), B('禁区', sm=True), B('保持距离', sm=True)], 3) + '<div style="height:8px"></div>' + f'<div style="display:grid;grid-template-columns:1fr auto;gap:8px"><div class="inp" style="color:{T["mut"]}">说一句…</div>{B("说", "pri")}</div>' + '<div style="height:8px"></div>' + btnrow([B('停止喊话', sm=True), B('编辑常用话', sm=True)]))}
  {group('警示', '每一路开都带时长，到点自己关', btnrow([B('警灯 30 秒', icon='light'), B('警笛 10 秒', icon='bell')]) + '<div style="height:8px"></div>' + btnrow([B('左聚光灯', sm=True), B('右聚光灯', sm=True), B('全部关', sm=True)], 3))}
  {group('最近事件', '', ''.join(f'<div style="display:grid;grid-template-columns:52px 1fr;gap:8px;min-height:32px"><span class="mut">{a}</span><span>{b}</span></div>' for a,b in [('23:38','过 2 号楼北侧'),('23:12','电量低于 30%'),('22:00','开始 guard-1')]))}
</div>''' + estop_fab(top=844 - 116) + fold()
    return board(name, title, body, h=H)


def n_dispatch(name='App-N-dispatch', title='App · 保安 · 派巡逻'):
    def route(n, eta, sel=False, note=''):
        return f'<a href="#" class="li" style="{"background:"+T["sel"]+";box-shadow:inset 0 0 0 2px "+T["blue"] if sel else ""}">{ic("route",20,T["sec"])}<div class="b"><b>{n}</b><div class="s">{eta}{note}</div></div></a>'
    body = appbar('A · C40221', '巡逻中 · 62%') + f'''
<div style="flex:1;min-height:0;position:relative;background:{T['bg']}">
  <div style="opacity:.35">{video(210)}</div>
  <div style="position:absolute;inset:0;background:rgba(0,0,0,.55)"></div>
  <section style="position:absolute;left:0;right:0;bottom:0;background:{T['surf']};border-top:1px solid {T['rule']};padding-bottom:20px;box-shadow:0 -8px 24px rgba(0,0,0,.45)">
    <div style="width:36px;height:4px;background:{T['rule']};margin:10px auto 6px"></div>
    <div style="padding:6px 16px 10px;display:flex;align-items:center"><b style="font-size:18px;flex:1">派 A 巡逻</b><span class="note">临时巡逻，不进日程</span></div>
    {route('guard-1', '约 14 分钟（含回待命点）', True)}
    {route('停车场一圈', '约 6 分钟')}
    {route('外围全线', '约 32 分钟', note=' · 电量不够走完，会先回充')}
    <div style="padding:12px 16px"><div class="lbl" style="margin-bottom:6px">圈数</div>
    <div class="seg" style="grid-template-columns:repeat(4,1fr)"><button class="on" type="button">1 圈</button><button type="button">2 圈</button><button type="button">3 圈</button><button type="button">一直跑</button></div>
    <div style="display:flex;gap:8px;align-items:flex-start;padding:10px;border:1px solid {T['amb']};background:{T['ambsoft']};margin-top:12px"><span class="tri" style="margin-top:4px"></span><span style="font-size:14px">A 现在在跑 guard-1 第 3 圈。日程优先，你这趟排到 23:58 之后。</span></div>
    <div style="height:12px"></div>{btnrow([B('排上', 'pri'), B('取消')])}
    <div class="note" style="margin-top:8px">派出去会通知经理和管理员。</div></div>
  </section>
</div>'''
    return board(name, title, body)


def n_teleop(name='App-N-teleop', title='App · 保安 · 遥控（横屏）'):
    stick = lambda x, lab: f'<div style="position:absolute;bottom:22px;{x};width:150px;height:150px;border-radius:50%;border:2px solid rgba(236,237,234,.45);background:rgba(0,0,0,.25)"><div style="position:absolute;left:50px;top:50px;width:50px;height:50px;border-radius:50%;background:rgba(236,237,234,.75)"></div><div style="position:absolute;left:0;right:0;bottom:-20px;text-align:center;font-size:12px;color:#ECEDEA">{lab}</div></div>'
    body = f'''<div style="position:absolute;inset:0;background:radial-gradient(ellipse at 50% 60%,#232a30 0%,#07080A 75%)"></div>
  <div style="position:absolute;left:0;right:0;top:0;display:flex;align-items:center;gap:12px;padding:10px 16px;background:rgba(0,0,0,.6)">
    <button class="btn sm" type="button" aria-label="结束遥控" style="background:transparent">{ic('back',18)}结束</button>
    <b>A · 你在控制</b><span class="sq"></span><span class="note">站立 · 62% · 低速档</span><span style="flex:1"></span>
    <div class="seg" style="grid-template-columns:repeat(3,auto)"><button class="on" type="button" style="padding:0 12px">前</button><button type="button" style="padding:0 12px">后</button><button type="button" style="padding:0 12px">热像</button></div>
    {B('姿态', sm=True)}</div>
  {stick('left:28px', '左杆：前后 · 横移')}{stick('right:150px', '右杆：转向')}
  <button type="button" aria-label="停" style="position:absolute;right:20px;bottom:30px;width:100px;height:100px;border:2px solid #fff;border-radius:2px;background:#D42F33;color:#fff;font:700 18px {F};display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px">{ic('oct',30,'#fff')}停</button>'''
    return board(name, title, body, w=844, h=390)


def n_ring(name='App-N-ring', title='App · 锁屏 / 后台来报警'):
    body = f'''<div style="flex:1;display:flex;flex-direction:column;padding:56px 20px 28px;background:{T['bg']};box-shadow:inset 0 0 0 6px {T['red']}">
  <div class="note" style="text-align:center">estate-1 · 23:47</div>
  <div style="display:flex;justify-content:center;margin:36px 0 20px"><span class="ring" style="width:96px;height:96px;border-width:14px"></span></div>
  <div style="text-align:center"><b style="font-size:28px;line-height:34px">北门有人翻越</b><div class="note" style="font-size:15px;margin-top:6px">P1 · 摄像头 3 · 往 2 号楼方向</div><div style="margin-top:6px;font-weight:600">A 已自动派往北门 · 约 1 分钟</div></div>
  <div style="flex:1"></div>
  <div class="note" style="text-align:center;margin-bottom:12px">一直响到有人接手；别人接手了这里自动停。</div>
  {btnrow([B('我来处理', 'pri', icon='disc', extra='height:56px;font-size:17px')], 1)}
  <div style="height:10px"></div>{btnrow([B('只看画面', extra='height:52px'), B('静音 2 分钟', extra='height:52px')])}
</div>'''
    return board(name, title, body)


def n_mgr(name='App-N-mgr', title='App · 经理 · 这件事'):
    H = 1500
    body = appbar('这件事', '23:47 发现 · 已过 3 分钟') + inc_head('gina 23:48 接手 · A 正在跟随', 3) + f'''
<div style="flex:1;min-height:0">
  {video(210, cap='A · 前摄像头 · 跟随中', tabs=('A 前', '事件'), on='A 前')}
  <div style="padding:12px 16px;border-bottom:1px solid {T['rule']}">{map_block(219, alarm=True, tools=False, robots=(('A', 104, 38, True), ('B', 300, 168, False)))}</div>
  {group('现在谁在做', '', f'<div style="display:grid;grid-template-columns:80px 1fr;gap:6px 10px"><span class="mut">处理人</span><b>gina（保安）</b><span class="mut">机器人</span><span>A 在北门跟随，距离 4.6 米</span><span class="mut">现场警示</span><span>23:49 喊话：请离开</span></div>')}
  {group('经理能做的', '派机器人去报警点和现场警示由保安操作', btnrow([B('我来接手', 'pri', icon='disc'), B('请求支援', icon='bell')]))}
  {group('结论', '', btnrow([B('确认有人'), B('误报'), B('其他')]) + '<div style="height:10px"></div>' + btnrow([B('结案')], 1))}
</div>''' + estop_fab(top=844 - 116) + fold()
    return board(name, title, body, h=H)


if __name__ == '__main__':
    import json, now
    out = [now.n_normal(), now.n_alarm(), n_ring(), n_incident(), n_multi(), n_estop(), n_spot(), n_route(), n_robot(), n_dispatch(), n_teleop(),
           now.n_alarm(name='App-M-now', title='App · 经理 · 现在（有人翻越）', manager=True), n_mgr(), n_robot(name='App-M-robot', title='App · 经理 · 机器人 A', manager=True),
           now.n_alarm(name='App-V-now', title='App · 只读 · 现在（有人翻越）', viewer=True)]
    json.dump(out, open('now_boards.json', 'w'), ensure_ascii=False)
    print(len(out))


def n_map(name='App-N-map', title='App · 全屏地图（图层）'):
    ex = f'<polyline points="214,70 268,70 268,124" fill="none" stroke="{T["bluet"]}" stroke-width="1.5" stroke-dasharray="2 3"/><circle cx="268" cy="124" r="5" fill="none" stroke="{T["amb"]}" stroke-width="2"/><text x="276" y="128" font-size="9" fill="{T["ambt"]}" font-family="Barlow">被挡</text><circle cx="140" cy="170" r="5" fill="none" stroke="{T["mut"]}" stroke-width="2"/><text x="148" y="174" font-size="9" fill="{T["sec"]}" font-family="Barlow">定位出过问题</text>'
    leg = lambda sw, t: f'<div style="display:flex;align-items:center;gap:8px;min-height:30px">{sw}<span style="font-size:14px">{t}</span></div>'
    body = appbar('现场地图', 'estate-1 第 8 版 · 摆正 23°', right=B('图层', sm=True)) + f'''
<div style="flex:1;min-height:0;position:relative">
  {sitemap(390, 470, path='40,100 140,100 140,124 214,124 214,70', extra=ex)}
  <div style="position:absolute;right:12px;top:12px;display:flex;flex-direction:column;gap:6px">{''.join(f'<button class="btn sm" type="button" aria-label="{a}" style="width:44px;padding:0">{b}</button>' for a,b in [('放大','+'),('缩小','−'),('回正',ic('home',18))])}</div>
  <div style="position:absolute;left:12px;top:440px;font-size:12px;color:{T['sec']}">10 米 ▁▁▁▁</div>
  <section style="position:absolute;left:0;right:0;bottom:0;top:470px;background:{T['surf']};border-top:1px solid {T['rule']};padding:12px 16px">
    {btnrow([B('派去看一眼', icon='pin', sm=True), B('临时路线', icon='route', sm=True), B('设位置', sm=True)], 3)}
    <div class="lbl" style="margin:14px 0 4px">图例</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;column-gap:12px">
    {leg(f'<span style="width:18px;border-top:2.5px solid {T["bluet"]}"></span>', 'A 已走的轨迹')}{leg(f'<span style="width:18px;border-top:1.5px dashed {T["mut"]}"></span>', '巡逻路线')}
    {leg(f'<span style="width:14px;height:12px;border:1.2px dashed {T["redt"]}"></span>', '布防的防区')}{leg(f'<span style="width:14px;height:12px;border:1.2px solid {T["grn"]}"></span>', '充电桩')}
    {leg(f'<span style="width:12px;height:12px;border:2px solid {T["amb"]};border-radius:50%"></span>', '被挡的位置')}{leg(f'<span style="width:12px;height:12px;border:2px solid {T["mut"]};border-radius:50%"></span>', '定位出过问题')}</div>
  </section>
</div>'''
    return board(name, title, body)


def n_refuse(name='App-N-refuse', title='App · 派单被拒、急停没成功'):
    body = appbar('A · C40221', '巡逻中 · 62%') + f'''
<div style="flex:1;min-height:0;padding:12px 16px;display:flex;flex-direction:column;gap:12px">
  <section style="border:1px solid {T['amb']};background:{T['ambsoft']};padding:12px">
    <div style="display:flex;gap:10px"><span class="tri lg"></span><div style="flex:1"><b style="font-size:17px">站点没派：A 没站起来</b><div class="note" style="margin-top:2px">A 现在趴着。站起来以后再派一次。</div></div></div>
    <div style="height:10px"></div>{btnrow([B('让 A 站起', 'pri'), B('知道了')])}</section>
  <section style="border:4px solid {T['red']};background:{T['surf']};padding:12px">
    <div style="display:flex;gap:10px"><span class="ring lg"></span><div style="flex:1"><b style="font-size:17px">急停没确认</b><div class="note" style="margin-top:2px">站点 23:41:05 收到了，B 没回话。B 可能还在动，请看画面或到现场。</div></div></div>
    <div style="height:10px"></div>{btnrow([B('再按一次急停', 'stop'), B('看 B 的画面')])}</section>
</div>''' + estop_fab()
    return board(name, title, body)


def n_tour(name='App-N-tour', title='App · 上手导览（第 2 步）'):
    body = topbar(clock='20:05') + f'''
<div style="flex:1;min-height:0;position:relative">
  <div style="display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid {T['rule']}"><span class="sq" style="width:12px;height:12px"></span><div style="flex:1"><b>全场正常</b><div class="note">下一次巡逻 22:00 由 A 跑</div></div></div>
  {video(212, playing=False)}
  <div style="position:absolute;inset:0;background:rgba(0,0,0,.6)"></div>
  <div style="position:absolute;left:12px;right:12px;top:58px;height:216px;box-shadow:0 0 0 3px {T['bluet']}"></div>
  <section style="position:absolute;left:16px;right:16px;top:300px;background:{T['surf']};border:1px solid {T['rule']};padding:14px;box-shadow:0 8px 24px rgba(0,0,0,.45)">
    <div class="note">2 / 5</div><b style="font-size:18px">画面</b>
    <p style="margin:6px 0 12px">默认不播，点一下才开始，省流量。左右滑换机器人，前、后、热像在右上角切。</p>
    {btnrow([B('下一步', 'pri'), B('跳过')])}</section>
</div>''' + estop_fab()
    return board(name, title, body)


def n_nomap(name='App-N-nomap', title='App · 管理员 · 现在（还没有地图）'):
    body = topbar(clock='10:20', arm='撤防', armsign='none') + f'''
<div style="flex:1;min-height:0">
  <section style="margin:12px 16px;border:1px solid {T['rule']};background:{T['surf']};padding:14px">
    <div style="display:flex;gap:10px"><span class="discb" style="margin-top:5px"></span><div style="flex:1"><b style="font-size:17px">站点还没有地图</b><div class="note">机器人要先有图才能巡逻。用 A 走一圈，大约 20 分钟。</div></div></div>
    <div style="height:12px"></div>{btnrow([B('开始建图', 'pri')], 1)}</section>
  {video(212, playing=False)}
  <div style="padding:12px 16px">{robot_tiles(a=('sq', '待命', '96%', '还没有地图'), b=('tri', '换网待批', '54%', '等管理员批准'))}</div>
  <div style="position:absolute;left:0;right:0;bottom:0;display:flex;align-items:center;gap:10px;padding:12px 16px 20px;background:{T['surf']};border-top:1px solid {T['rule']}"><span class="discb"></span><span style="flex:1">App 有新版本 2.8.2</span>{B('更新', sm=True)}{B('以后', sm=True)}</div>
</div>''' + estop_fab(bottom=96)
    return board(name, title, body)


if __name__ == '__main__':
    import json, now
    out = json.load(open('now_boards.json'))
    out += [n_map(), n_refuse(), n_tour(), n_nomap()]
    json.dump(out, open('now_boards.json', 'w'), ensure_ascii=False)
    print(len(out))

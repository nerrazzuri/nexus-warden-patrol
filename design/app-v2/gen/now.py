# 「现在」这一层（深色）
from ac import *
T = DARK


def robot_tiles(a=('sq', '巡逻中', '62%', '北区 · guard-1 第 3 圈'), b=('tri', '充电中', '18%', '充电桩 1 · 约 01:00 到 80%'), sel='A', btn=True):
    def tile(n, d, on):
        sign = {'sq': '<span class="sq"></span>', 'tri': '<span class="tri"></span>', 'ring': '<span class="ring"></span>', 'off': '<span class="off"></span>', 'stop': '<span class="ring"></span>'}[d[0]]
        pc = T['ambt'] if d[0] == 'tri' else T['tx']
        return f'''<a href="#" style="display:block;padding:10px 12px;background:{T['sel'] if on else T['surf']};border:1px solid {T['blue'] if on else T['rule']};border-radius:2px;color:{T['tx']};text-decoration:none;min-width:0">
  <div style="display:flex;align-items:center;gap:8px"><b style="font-size:20px;line-height:24px">{n}</b>{sign}<span style="font-weight:600">{d[1]}</span><span style="flex:1"></span><b style="color:{pc}">{d[2]}</b></div>
  <div class="note" style="margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{d[3]}</div>
  {f'<div style="display:flex;align-items:center;gap:4px;margin-top:6px;font-size:14px;font-weight:600;color:{T["bluet"]}">控制{ic("chev",14)}</div>' if btn else ''}</a>'''
    return f'<div class="row" style="grid-template-columns:1fr 1fr">{tile("A", a, sel=="A")}{tile("B", b, sel=="B")}</div>'


def tonight(rows=None):
    rows = rows or [('19:00', 'guard-1 · A', '走完', 'ok'), ('22:00', 'guard-1 · A', '第 3 圈', 'n'), ('01:00', 'guard-1 · B', '等充电', 'warn'), ('04:00', 'guard-1 · A', '排好了', 'n')]
    out = ''
    for tm, what, st, k in rows:
        sign = '<span class="sq"></span>' if k == 'ok' else ('<span class="tri"></span>' if k == 'warn' else '')
        out += f'<div style="display:grid;grid-template-columns:52px 1fr auto;align-items:center;gap:8px;min-height:40px;border-bottom:1px solid {T["rule"]}"><b>{tm}</b><span>{what}</span><span style="display:inline-flex;align-items:center;gap:6px;color:{T["sec"]}">{sign}{st}</span></div>'
    return out


def sec(title, inner, right='', pad='14px 16px'):
    return f'''<section style="padding:{pad};border-bottom:1px solid {T['rule']}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><h2 class="h2" style="flex:1">{title}</h2>{right}</div>
  {inner}</section>'''


def map_block(h=219, alarm=False, tools=True, robots=None, pick=None, path=None):
    kw = {}
    if robots is not None:
        kw['robots'] = robots
    tl = f'''<div class="row" style="grid-template-columns:1fr 1fr 44px;margin-top:8px">{B('派去看一眼', icon='pin', sm=True)}{B('临时路线', icon='route', sm=True)}<button class="btn sm" type="button" aria-label="全屏地图" style="padding:0">{ic('expand',18)}</button></div>''' if tools else ''
    return f'<div style="border:1px solid {T["rule"]}">{sitemap(358, h, alarm=alarm, pick=pick, path=path, **kw)}</div>{tl}'


def lastnote():
    return sec('上一班留言 · olga 19:05', f'<p style="margin:0">停车场有施工车辆进出，22:00 前算正常。</p><div style="margin-top:10px">{B("给下一班留言", sm=True, icon="note")}</div>')


def ops_p2():
    return f'''<a href="#" class="li" style="padding-left:16px"><span class="tri"></span><div class="b"><div style="font-weight:600">B 电量 18%</div><div class="s">22:40 自动回桩充电 · 01:00 前能充到 80%</div></div>{ic('chev',18,T['mut'])}</a>'''


# ---------------- 1. 正常值班 ----------------
def n_normal(name='App-N-normal', who='保安', title='App · 保安 · 现在（正常）'):
    H = 1560
    body = topbar(clock='23:40') + f'''
<div style="flex:1;min-height:0">
  <div style="display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid {T['rule']}"><span class="sq" style="width:12px;height:12px"></span><div style="flex:1"><b>全场正常</b><div class="note">A 在跑 guard-1 第 3 圈 · 下一次巡逻 01:00 由 B 跑</div></div></div>
  {video(212)}
  <div style="padding:12px 16px;border-bottom:1px solid {T['rule']}">{robot_tiles()}</div>
  <div style="padding:12px 16px;border-bottom:1px solid {T['rule']}">{map_block()}</div>
  {sec('今晚巡逻', tonight(), f'<span class="note">本班 19:00 → 07:00</span>')}
  <section style="border-bottom:1px solid {T['rule']}"><div style="padding:14px 16px 4px"><h2 class="h2">设备与运营</h2></div>{ops_p2()}</section>
  {lastnote()}
  {sec('最新活动', ''.join(f'<div style="display:grid;grid-template-columns:52px 1fr;gap:8px;min-height:36px;align-items:center"><span class="mut">{a}</span><span>{b}</span></div>' for a,b in [('23:38','A 过 2 号楼北侧'),('22:40','B 回桩充电'),('22:05','gina 关闭：停车场车辆滞留'),('22:00','A 开始 guard-1')]), f'<a href="#" style="color:{T["bluet"]};font-weight:600;text-decoration:none">记录与录像</a>')}
</div>''' + estop_fab(top=844 - 116) + fold()
    return board(name, title, body, h=H)


# ---------------- 2. 有 P1 ----------------
def incident_strip(owner=None, age='没人接手 · 1 分钟', act=True, manager=False, viewer=False):
    if viewer:
        btns = f'<div class="note" style="margin-top:10px">只读账号：能看进度，处理由保安和经理做。</div>'
    elif owner:
        btns = f'<div class="row" style="grid-template-columns:1fr;margin-top:12px">{B("打开这件事", "pri", icon="disc")}</div>'
    else:
        btns = f'<div class="row" style="grid-template-columns:1fr 1fr;margin-top:12px">{B("我来处理", "pri", icon="disc")}{B("打开这件事")}</div>'
    return f'''<section style="margin:12px 16px;border:4px solid {T['red']};background:{T['surf']};border-radius:2px;padding:12px">
  <div style="display:flex;gap:12px;align-items:flex-start"><span class="ring lg" style="margin-top:2px"></span>
  <div style="flex:1;min-width:0"><div style="display:flex;align-items:baseline;gap:8px"><b style="font-size:20px;line-height:26px">北门有人翻越</b><span class="chip c-bad" style="height:20px;font-size:12px">P1</span></div>
  <div class="note">北区 北门 · 摄像头 3 · 23:47 · 往 2 号楼方向</div>
  <div style="margin-top:4px;font-weight:600;color:{T['redt'] if not owner else T['tx']}">{owner or age}</div></div></div>
  {btns}</section>'''


def n_alarm(name='App-N-alarm', title='App · 保安 · 现在（有人翻越）', manager=False, viewer=False, who='gina'):
    H = 1080
    body = topbar(clock='23:48', open_n=3) + f'''
<div style="flex:1;min-height:0">
  {incident_strip(manager=manager, viewer=viewer, owner=('olga 在处理 · A 已派往北门' if viewer else None))}
  {video(200, cap='摄像头 3 · 北门 · 事件画面', tabs=('事件', 'A 前'), on='事件', overlay='<div style="position:absolute;left:46%;top:38%;width:58px;height:96px;border:2px solid #FF6166"><span style="position:absolute;left:-2px;top:-20px;background:#D42F33;color:#fff;font-size:11px;font-weight:700;padding:0 4px">人 · 0.93</span></div>')}
  <div style="padding:12px 16px;border-bottom:1px solid {T['rule']}">{map_block(219, alarm=True, tools=False, robots=(('A', 150, 60, False), ('B', 300, 168, False)), path='214,70 150,60 92,26')}<div class="note" style="margin-top:6px">A 48 米 · 约 1 分钟</div></div>
  <section style="border-bottom:1px solid {T['rule']}"><div style="padding:14px 16px 4px;display:flex"><h2 class="h2" style="flex:1">另外 2 件没处理</h2></div>
  <a href="#" class="li"><span class="ring"></span><div class="b"><div style="font-weight:600">B 等待换电</div><div class="s">充电桩 1 · 23:31 · olga 处理中</div></div>{ic('chev',18,T['mut'])}</a>
  <a href="#" class="li"><span class="tri"></span><div class="b"><div style="font-weight:600">A 电量低于 30%</div><div class="s">巡逻中 · 23:12</div></div>{ic('chev',18,T['mut'])}</a></section>
  <div style="padding:12px 16px">{robot_tiles(a=('ring', '赶往北门', '28%', '北门 · 约 1 分钟到'), b=('ring', '等待换电', '18%', '充电桩 1'), btn=not viewer)}</div>
</div>''' + ('' if viewer else estop_fab(top=844 - 116)) + fold()
    return board(name, title, body, h=H)


if __name__ == '__main__':
    import json
    out = [n_normal(), n_alarm()]
    print(json.dumps(out, ensure_ascii=False))

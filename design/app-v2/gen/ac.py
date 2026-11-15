# 手机 App 稿：公共件（方案 B「现在 / 现场」两层；画风同网页 V4）
import os
OUT = '/tmp/claude-1000/-home-liang-Projects-D1-Max/ecced633-c546-490e-ade6-e46e90a431ed/scratchpad/dcanvas/project'
F = "Barlow,'Noto Sans SC','Microsoft YaHei UI',sans-serif"

DARK = dict(bg='#0E1013', surf='#16191D', raised='#20242A', rule='#2E333A', tx='#ECEDEA', sec='#B4B8BE', mut='#9A9FA6',
            blue='#1F6FC0', bluet='#5AA2E6', red='#D42F33', redt='#FF6166', redsoft='#33191B', amb='#F2B01E', ambt='#F2B01E',
            ambsoft='#2D2512', grn='#3DC46E', grnsoft='#16281D', line='#9A9FA6', sel='#14273D')
LIGHT = dict(bg='#F5F6F4', surf='#FFFFFF', raised='#ECEEEB', rule='#D3D6D2', tx='#15181B', sec='#474C52', mut='#5F646A',
             blue='#0B5FA5', bluet='#0B5FA5', red='#C8102E', redt='#C8102E', redsoft='#FBE4E7', amb='#F2A900', ambt='#8A5A00',
             ambsoft='#FBF0D2', grn='#0F7A3C', grnsoft='#E3F2E8', line='#6B7178', sel='#E3EEF9')


def css(t):
    return f'''body{{margin:0}}
*{{box-sizing:border-box}}
.btn{{height:44px;padding:0 14px;border:1px solid {t['line']};border-radius:2px;background:{t['surf']};color:{t['tx']};font:600 15px {F};display:inline-flex;align-items:center;justify-content:center;gap:8px;white-space:nowrap;min-width:0}}
.btn.sm{{height:36px;padding:0 10px;font-size:14px}}
.btn.pri{{background:{t['blue']};border-color:{t['blue']};color:#fff;font-weight:700}}
.btn.danger{{background:transparent;border-color:{t['redt']};color:{t['redt']}}}
.btn.stop{{background:{t['red']};border-color:{t['red']};color:#fff;font-weight:700}}
.btn.ghost{{background:transparent;border-color:transparent;color:{t['bluet']}}}
.row{{display:grid;gap:8px}}
.lbl{{font-size:12px;font-weight:600;letter-spacing:.06em;color:{t['mut']}}}
.mut{{color:{t['sec']}}}
.ring{{display:inline-block;flex:none;width:14px;height:14px;border:3px solid {t['redt']};border-radius:50%}}
.ring.lg{{width:26px;height:26px;border-width:5px}}
.tri{{display:inline-block;flex:none;width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-bottom:12px solid {t['amb']}}}
.tri.lg{{border-left-width:12px;border-right-width:12px;border-bottom-width:21px}}
.sq{{display:inline-block;flex:none;width:9px;height:9px;background:{t['grn']}}}
.off{{display:inline-block;flex:none;width:14px;height:14px;border:2px solid {t['mut']};border-radius:50%;background:linear-gradient(135deg,transparent 45%,{t['mut']} 45%,{t['mut']} 58%,transparent 58%)}}
.disc{{display:inline-block;flex:none;width:12px;height:12px;border-radius:50%;background:#fff}}
.discb{{display:inline-block;flex:none;width:12px;height:12px;border-radius:50%;background:{t['blue']}}}
.p3{{display:inline-block;flex:none;width:12px;height:12px;border:1.5px solid {t['mut']};border-radius:50%}}
.sec{{padding:14px 16px;border-bottom:1px solid {t['rule']}}}
.h2{{margin:0;font-size:17px;line-height:24px;font-weight:600}}
.h1{{margin:0;font-size:22px;line-height:28px;font-weight:700}}
.li{{display:flex;align-items:center;gap:12px;min-height:56px;padding:8px 16px;border-bottom:1px solid {t['rule']};color:{t['tx']};text-decoration:none}}
.li .b{{flex:1;min-width:0}}
.li .s{{font-size:13px;line-height:18px;color:{t['sec']}}}
.seg{{display:grid;border:1px solid {t['rule']};border-radius:2px;padding:3px;gap:3px}}
.seg button{{height:36px;border:0;border-radius:2px;background:transparent;color:{t['sec']};font:600 14px {F}}}
.seg button.on{{background:{t['blue']};color:#fff}}
.chip{{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 8px;border-radius:2px;font-size:13px;font-weight:600;white-space:nowrap}}
.c-ok{{background:{t['grnsoft']};color:{t['grn']}}} .c-warn{{background:{t['ambsoft']};color:{t['ambt']}}} .c-bad{{background:{t['redsoft']};color:{t['redt']}}} .c-n{{background:{t['raised']};color:{t['sec']}}}
.vid{{position:relative;background:#000;overflow:hidden}}
.vid .cap{{position:absolute;left:0;right:0;top:0;display:flex;align-items:center;gap:8px;padding:6px 10px;background:rgba(0,0,0,.65);color:#ECEDEA;font-size:13px}}
.inp{{height:44px;border:1px solid {t['line']};border-radius:2px;padding:0 12px;background:{t['surf']};color:{t['tx']};font:400 15px {F};display:flex;align-items:center;width:100%}}
.sw{{width:44px;height:26px;border-radius:2px;background:{t['raised']};border:1px solid {t['line']};position:relative;flex:none}}
.sw::after{{content:"";position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:1px;background:{t['mut']}}}
.sw.on{{background:{t['blue']};border-color:{t['blue']}}} .sw.on::after{{left:21px;background:#fff}}
.note{{font-size:13px;line-height:18px;color:{t['sec']}}}
.tag{{display:inline-block;padding:0 6px;border:1px solid {t['bluet']};color:{t['bluet']};font-size:11px;font-weight:700;line-height:16px}}
'''


def board(name, title, body, light=False, w=390, h=844, lang='zh-CN'):
    t = LIGHT if light else DARK
    html = f'''<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&display=swap">
<style>
{css(t)}
</style>
</helmet>
<div style="width:{w}px;height:{h}px;position:relative;overflow:hidden;background:{t['bg']};color:{t['tx']};font-family:{F};font-size:15px;line-height:22px;font-variant-numeric:tabular-nums;display:flex;flex-direction:column">
{body}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":{w},"height":{h}}}}}'>
class Component extends DCLogic {{
  renderVals() {{ return {{}}; }}
}}
</script>
</body>
</html>
'''
    open(os.path.join(OUT, name + '.dc.html'), 'w').write(html)
    return dict(name=name, title=title, w=w, h=h)


# ---------- 图标（线条，2px，24 格） ----------
def ic(kind, size=20, color='currentColor'):
    p = {
        'back': '<polyline points="15,4 7,12 15,20"/>',
        'chev': '<polyline points="9,5 16,12 9,19"/>',
        'down': '<polyline points="5,9 12,16 19,9"/>',
        'robot': '<rect x="4" y="8" width="16" height="9" rx="1"/><line x1="7" y1="17" x2="6" y2="21"/><line x1="17" y1="17" x2="18" y2="21"/><circle cx="16" cy="11" r="1.2"/><line x1="20" y1="10" x2="22" y2="9"/>',
        'map': '<polygon points="3,6 9,4 15,6 21,4 21,18 15,20 9,18 3,20"/><line x1="9" y1="4" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="20"/>',
        'play': '<polygon points="8,5 19,12 8,19" fill="currentColor"/>',
        'expand': '<polyline points="14,4 20,4 20,10"/><polyline points="10,20 4,20 4,14"/><line x1="20" y1="4" x2="14" y2="10"/><line x1="4" y1="20" x2="10" y2="14"/>',
        'pin': '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11z"/><circle cx="12" cy="10" r="2"/>',
        'route': '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6"/>',
        'speaker': '<polygon points="4,9 8,9 13,5 13,19 8,15 4,15"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M18.5 6.5a8 8 0 0 1 0 11"/>',
        'light': '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
        'bell': '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
        'person': '<circle cx="12" cy="7" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
        'search': '<circle cx="11" cy="11" r="6"/><line x1="16" y1="16" x2="21" y2="21"/>',
        'plus': '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
        'close': '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
        'more': '<circle cx="12" cy="5" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="19" r="1.4" fill="currentColor"/>',
        'cam': '<rect x="3" y="7" width="13" height="10" rx="1"/><polygon points="16,10 21,7 21,17 16,14"/>',
        'clock': '<circle cx="12" cy="12" r="8"/><polyline points="12,7 12,12 15,14"/>',
        'doc': '<path d="M6 3h8l4 4v14H6z"/><polyline points="14,3 14,7 18,7"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="15" y2="16"/>',
        'gear': '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
        'shield': '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
        'key': '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>',
        'chart': '<line x1="4" y1="20" x2="20" y2="20"/><rect x="6" y="11" width="3" height="7"/><rect x="11" y="7" width="3" height="11"/><rect x="16" y="13" width="3" height="5"/>',
        'list': '<line x1="8" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="20" y2="12"/><line x1="8" y1="18" x2="20" y2="18"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/>',
        'wrench': '<path d="M14 6a4 4 0 0 0 5 5l-9 9-3-3 9-9a4 4 0 0 1-2-2z"/>',
        'up': '<polyline points="5,15 12,8 19,15"/>',
        'help': '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5V14"/><circle cx="12" cy="17" r=".8" fill="currentColor"/>',
        'cloud': '<path d="M7 18h10a4 4 0 0 0 0-8 6 6 0 0 0-11.5 1.5A3.3 3.3 0 0 0 7 18z"/>',
        'note': '<path d="M5 4h14v12l-4 4H5z"/><polyline points="15,20 15,16 19,16"/>',
        'pause': '<line x1="9" y1="5" x2="9" y2="19"/><line x1="15" y1="5" x2="15" y2="19"/>',
        'home': '<polyline points="4,11 12,4 20,11"/><path d="M6 10v10h12V10"/>',
        'stand': '<rect x="5" y="6" width="14" height="6" rx="1"/><line x1="7" y1="12" x2="7" y2="20"/><line x1="17" y1="12" x2="17" y2="20"/>',
        'scan': '<path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/><line x1="4" y1="12" x2="20" y2="12"/>',
        'wifi': '<path d="M2 9a15 15 0 0 1 20 0"/><path d="M5 12.5a10 10 0 0 1 14 0"/><path d="M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1" fill="currentColor"/>',
        'oct': '<polygon points="8,2 16,2 22,8 22,16 16,22 8,22 2,16 2,8"/><line x1="7" y1="12" x2="17" y2="12"/>',
    }[kind]
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none">{p}</svg>'


# ---------- 顶部：站点 + 布防 + 时间；下面 现在 | 现场 ----------
def topbar(arm='布防中 · 到 07:00', armsign='sq', clock='23:48', site='estate-1', layer='now', open_n=0, stop_small=False):
    t = DARK
    sign = {'sq': '<span class="sq"></span>', 'tri': '<span class="tri"></span>', 'ring': '<span class="ring"></span>', 'none': ''}[armsign]
    badge = f'<span style="display:inline-flex;align-items:center;gap:5px;margin-left:8px;font-size:13px"><span class="ring" style="width:12px;height:12px;border-width:2.5px"></span>{open_n}</span>' if open_n else ''
    stop = f'<button class="btn stop sm" type="button" style="height:36px">{ic("oct",16,"#fff")}全部急停</button>' if stop_small else f'<b style="font-size:17px">{clock}</b>'
    return f'''<header style="flex:none;background:#0A0C0E;color:{t['tx']};padding:10px 16px 10px">
  <div style="display:flex;align-items:center;gap:10px;min-height:40px">
    <div style="flex:1;min-width:0"><div style="display:flex;align-items:center;gap:4px;font-size:17px;font-weight:700">{site}{ic('down',16,t['mut'])}</div>
    <div style="display:flex;align-items:center;gap:6px;font-size:13px;color:{t['sec']}">{sign}{arm}</div></div>
    {stop}
  </div>
  <div class="seg" role="tablist" aria-label="层" style="grid-template-columns:1fr 1fr;margin-top:10px;border-color:{t['rule']}">
    <button type="button" role="tab" class="{'on' if layer=='now' else ''}" style="display:inline-flex;align-items:center;justify-content:center">现在{badge}</button>
    <button type="button" role="tab" class="{'on' if layer=='site' else ''}">现场</button>
  </div>
</header>'''


def appbar(title, sub='', light=False, right='', back=True):
    t = LIGHT if light else DARK
    bg = t['surf'] if light else '#0A0C0E'
    return f'''<header style="flex:none;display:flex;align-items:center;gap:6px;min-height:56px;padding:6px 12px 6px 4px;background:{bg};border-bottom:1px solid {t['rule']}">
  {f'<button type="button" aria-label="返回" style="width:44px;height:44px;border:0;background:transparent;color:{t["tx"]};display:flex;align-items:center;justify-content:center">{ic("back",22)}</button>' if back else '<span style="width:12px"></span>'}
  <div style="flex:1;min-width:0"><div style="font-size:18px;font-weight:700;line-height:24px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{title}</div>{f'<div style="font-size:13px;line-height:18px;color:{t["sec"]};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{sub}</div>' if sub else ''}</div>
  {right}
</header>'''


def estop_fab(bottom=24, label='全部急停', top=None):
    return f'''<button type="button" aria-label="{label}" style="position:absolute;right:16px;{f'top:{top}px' if top is not None else f'bottom:{bottom}px'};width:92px;height:92px;border:2px solid #fff;border-radius:2px;background:#D42F33;color:#fff;font:700 15px/18px {F};display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;box-shadow:0 8px 24px rgba(0,0,0,.45);z-index:5">{ic('oct',28,'#fff')}<span>{label}</span></button>'''


def scroll(inner, pad_bottom=130, light=False):
    return f'<main style="flex:1;min-height:0;overflow:hidden;padding-bottom:{pad_bottom}px">{inner}</main>'


def btnrow(btns, cols=None, gap=8):
    n = cols or len(btns)
    return f'<div class="row" style="grid-template-columns:repeat({n},minmax(0,1fr));gap:{gap}px">' + ''.join(btns) + '</div>'


def B(text, kind='', icon=None, sm=False, extra=''):
    cls = 'btn' + (' sm' if sm else '') + (' ' + kind if kind else '')
    pre = ''
    if icon == 'disc':
        pre = '<span class="disc"></span>'
    elif icon:
        pre = ic(icon, 18)
    return f'<button class="{cls}" type="button" style="{extra}">{pre}{text}</button>'


# ---------- 现场地图（示意） ----------
def sitemap(w, h, alarm=False, robots=(('A', 214, 70, False), ('B', 300, 168, False)), route=True, pick=None, path=None, light=False, labels=True, dim=False, extra=''):
    t = LIGHT if light else DARK
    ground = '#E7E9E5' if light else '#20242A'
    wall = '#9AA0A6' if light else '#5B6168'
    txt = t['sec']
    s = f'''<svg width="{w}" height="{h}" viewBox="0 0 360 220" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;background:{ground}" role="img" aria-label="现场地图">
  <rect x="14" y="14" width="332" height="192" fill="none" stroke="{wall}" stroke-width="2"/>
  <rect x="150" y="40" width="96" height="70" fill="{'#D9DCD7' if light else '#2A2F35'}" stroke="{wall}" stroke-width="1.5"/>
  {f'<text x="198" y="80" text-anchor="middle" font-size="11" fill="{txt}" font-family="Barlow">2 号楼</text>' if labels else ''}
  <rect x="24" y="22" width="110" height="44" fill="none" stroke="{t['redt']}" stroke-width="1.2" stroke-dasharray="4 3" opacity=".8"/>
  {f'<text x="30" y="60" font-size="10" fill="{txt}" font-family="Barlow">北区 · 布防</text>' if labels else ''}
  <rect x="60" y="12" width="40" height="5" fill="{t['bg']}"/>{f'<text x="80" y="31" text-anchor="middle" font-size="10" fill="{txt}" font-family="Barlow">北门</text>' if labels else ''}
  <rect x="290" y="186" width="34" height="14" fill="none" stroke="{t['grn']}" stroke-width="1.2"/>{f'<text x="307" y="181" text-anchor="middle" font-size="9" fill="{txt}" font-family="Barlow">充电桩 1</text>' if labels else ''}
  <rect x="34" y="130" width="90" height="62" fill="none" stroke="{wall}" stroke-width="1" stroke-dasharray="2 3"/>{f'<text x="79" y="165" text-anchor="middle" font-size="10" fill="{txt}" font-family="Barlow">停车场</text>' if labels else ''}
'''
    if route:
        s += f'<polyline points="40,100 140,100 140,124 268,124 268,30 320,30 320,170 40,170 40,100" fill="none" stroke="{t["mut"]}" stroke-width="1.5" stroke-dasharray="5 4"/>'
    if path:
        s += f'<polyline points="{path}" fill="none" stroke="{t["bluet"]}" stroke-width="2.5"/>'
    if alarm:
        s += f'<circle cx="80" cy="20" r="12" fill="none" stroke="{t["redt"]}" stroke-width="4"/><path d="M92 26 L130 60" stroke="{t["redt"]}" stroke-width="1.5" stroke-dasharray="3 3"/>'
    if pick:
        x, y = pick
        s += f'<circle cx="{x}" cy="{y}" r="9" fill="{t["blue"]}" stroke="#fff" stroke-width="2"/><circle cx="{x}" cy="{y}" r="2.5" fill="#fff"/>'
    for name, x, y, sel in robots:
        fill = t['blue'] if sel else ('#15181B' if light else '#ECEDEA')
        tc = '#fff' if (sel or light) else '#0E1013'
        s += f'<circle cx="{x}" cy="{y}" r="10" fill="{fill}" stroke="{t["bg"]}" stroke-width="2"/><text x="{x}" y="{y+4}" text-anchor="middle" font-size="12" font-weight="700" fill="{tc}" font-family="Barlow">{name}</text>'
    s += extra + '</svg>'
    return s


def video(h, cap='A · 前摄像头', live=True, tabs=('前', '后', '热像'), on='前', overlay='', playing=True):
    tb = ''.join(f'<span style="padding:2px 8px;border:1px solid {"#5AA2E6" if x==on else "#6B7178"};{"background:#1F6FC0;border-color:#1F6FC0;" if x==on else ""}border-radius:2px;font-size:12px;font-weight:600">{x}</span>' for x in tabs) if tabs else ''
    body = '<div style="position:absolute;inset:0;background:radial-gradient(ellipse at 40% 70%,#1d2328 0%,#07080A 70%)"></div>'
    if not playing:
        body += f'<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:#B4B8BE">{ic("play",36,"#ECEDEA")}<span style="font-size:14px">点开看实时画面</span></div>'
    return f'''<div class="vid" style="height:{h}px">{body}
  <div class="cap"><b style="font-weight:600">{cap}</b>{'<span style="color:#B4B8BE">实时</span>' if live and playing else ''}<span style="flex:1"></span>{tb}</div>{overlay}</div>'''


def fold(y=844, light=False):
    t = LIGHT if light else DARK
    return f'<div aria-hidden="true" style="position:absolute;left:0;right:0;top:{y}px;border-top:1px dashed {t["bluet"]};z-index:6"><span style="position:absolute;right:4px;top:-18px;font-size:11px;font-weight:600;color:{t["bluet"]}">第一屏到这里</span></div>'

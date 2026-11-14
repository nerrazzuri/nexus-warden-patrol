# 机器人页三个方案共用的小部件
def chev(d,size=18,color="currentColor"):
    pts={"up":"4,13 10,7 16,13","down":"4,7 10,13 16,7","left":"13,4 7,10 13,16","right":"7,4 13,10 7,16"}[d]
    return f'<svg width="{size}" height="{size}" viewBox="0 0 20 20" aria-hidden="true"><polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="square"/></svg>'
CENTER='<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="10" r="1.6" fill="currentColor"/></svg>'
def dpad(btn_style, size=44):
    b=lambda d,l: f'<button type="button" aria-label="云台{l}" style="{btn_style};width:{size}px;height:{size}px">{chev(d)}</button>'
    c=f'<button type="button" aria-label="云台回中" style="{btn_style};width:{size}px;height:{size}px">{CENTER}</button>'
    return f'<div style="display:grid;grid-template-columns:repeat(3,{size}px);gap:4px"><span></span>{b("up","上")}<span></span>{b("left","左")}{c}{b("right","右")}<span></span>{b("down","下")}<span></span></div>'
NOISE='background:#07080A'

SEL='background:#E3EEF9;box-shadow:inset 0 0 0 2px #1F6FC0'
DISC='<span aria-hidden="true" style="display:inline-block;flex:none;width:12px;height:12px;border-radius:50%;background:#1F6FC0"></span>'
RINGN='<span aria-hidden="true" style="display:inline-block;flex:none;width:11px;height:11px;border:1.5px solid #6B7178;border-radius:50%;box-sizing:border-box"></span>'
TRI_S='<span class="tri" style="border-left-width:6px;border-right-width:6px;border-bottom-width:11px"></span>'
def fleet(sel, join=True):
    def row(name,code,sign,state,pct,pcol,on):
        return f'''<a href="#" style="display:grid;grid-template-columns:14px minmax(0,1fr) auto;gap:4px 10px;align-items:center;padding:12px 16px;border-bottom:1px solid #E3E5E8;text-decoration:none;color:#16191D;{SEL if on else ''}"{' aria-current="true"' if on else ''}>
        {sign}<b style="font-size:16px">{name} <span class="mut" style="font-weight:400;font-size:13px">{code}</span></b><b style="color:{pcol}">{pct}</b>
        <span></span><span class="mut">{state}</span><span></span></a>'''
    j=f'''<div style="margin-top:auto;padding:14px 16px;border-top:1px solid #D5D8DC">
      <div style="display:flex;gap:8px;align-items:center">{DISC}<b>1 台请求加入</b></div>
      <div class="mut" style="margin:4px 0 10px">C40388 · olga 的手机 · 09:41<br>核对码 <b style="color:#16191D;letter-spacing:.08em">482 913</b></div>
      <div style="display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:8px"><button class="btn sm pri" type="button" style="justify-content:center">核对后批准…</button><button class="btn sm" type="button" style="justify-content:center">拒绝</button></div></div>''' if join else ''
    return f'''<aside aria-label="机队" style="background:#fff;border-right:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0">
    <div style="display:flex;align-items:center;padding:16px;gap:8px;border-bottom:1px solid #E3E5E8"><h1 class="h2" style="flex:1;font-size:18px">机器人 2</h1><button class="btn sm" type="button">添加</button></div>
    {row("A","C40221",'<span class="sq"></span>',"巡逻 停车场一圈","62%","#16191D",sel=="A")}
    {row("B","C40011",TRI_S,"充电中 · 换网待批","18%","#7A5200",sel=="B")}
    {j}</aside>'''
def rhead(name,code,chip,meta,view):
    seg=''.join(f'<button class="btn{" on" if v==view else ""}" type="button" role="tab" aria-selected="{"true" if v==view else "false"}">{v}</button>' for v in ("操作","设置"))
    return f'''<div style="flex:none;display:flex;align-items:center;gap:14px;padding:16px 24px;border-bottom:1px solid #D5D8DC;background:#fff">
      <h2 style="margin:0;font-size:28px;line-height:34px">{name}</h2>{chip}<span class="mut">{code} · {meta}</span>
      <span style="flex:1"></span>
      <div class="seg" role="tablist" aria-label="{name} 的视图">{seg}</div></div>'''

INP='height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit;background:#fff;color:#16191D'
def phead(title, sentence, right="", sign=""):
    # 管理页统一页头：标题 + 一句话现状 + 右边操作；白底，1px 底线
    return f'''<div style="flex:none;display:flex;align-items:center;gap:16px;padding:0 28px;min-height:74px;background:#fff;border-bottom:1px solid #D5D8DC">
      <h1 style="margin:0;font-size:28px;line-height:34px">{title}</h1>
      <p style="margin:0;font-size:15px;min-width:0">{f'<span style="display:inline-flex;vertical-align:-1px;margin-right:8px">{sign}</span>' if sign else ""}{sentence}</p>
      <span style="flex:1"></span>{right}</div>'''
def seg(items,on,label):
    return f'<div class="seg" role="tablist" aria-label="{label}">'+''.join(f'<button class="btn{" on" if i==on else ""}" type="button" role="tab" aria-selected="{"true" if i==on else "false"}">{i}</button>' for i in items)+'</div>'
def rule(): return '<div style="grid-column:1/-1;height:1px;background:#E3E5E8"></div>'
def segw(items,on,label):
    # 等宽、占满一行的分段切换
    return f'<div class="seg" role="tablist" aria-label="{label}" style="display:grid;grid-template-columns:repeat({len(items)},minmax(0,1fr));width:100%">'+''.join(f'<button class="btn{" on" if i==on else ""}" type="button" role="tab" aria-selected="{"true" if i==on else "false"}" style="justify-content:center;padding:0 6px">{i}</button>' for i in items)+'</div>'
def tgrid(items,on,cols,label,h=36):
    # 等宽多选格：选中蓝底，未选白底
    cells=''.join(f'<button type="button" aria-pressed="{"true" if i in on else "false"}" style="height:{h}px;min-width:0;padding:0 6px;border:1px solid {"#1F6FC0" if i in on else "#9AA0A6"};background:{"#1F6FC0" if i in on else "#fff"};color:{"#fff" if i in on else "#16191D"};border-radius:2px;font:600 14px Barlow,\'Noto Sans SC\',sans-serif;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{i}</button>' for i in items)
    return f'<div role="group" aria-label="{label}" style="display:grid;grid-template-columns:repeat({cols},minmax(0,1fr));gap:6px">{cells}</div>'

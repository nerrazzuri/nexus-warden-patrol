from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
DAYS="一二三四五六日"
def week(days,a,b,today=6):
    return '<div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px">'+''.join(
        f'<span style="height:26px;display:flex;align-items:center;justify-content:center;font-size:12.5px;font-weight:600;background:{"#2A2F35" if i in days else "#F2F3F1"};color:{"#fff" if i in days else "#8A9097"};{"box-shadow:inset 0 -3px 0 #16191D;" if i==today else ""}">{d}</span>' for i,d in enumerate(DAYS))+'</div>'
def arow(name,scope,days,a,b,when,until,note=""):
    return f'''<div style="display:contents"><div style="padding:12px 0 12px 20px"><b>{name}</b>{f'<div class="mut" style="font-size:13px">{note}</div>' if note else ''}</div>
      <div style="padding:12px 0">{scope}</div><div style="padding:12px 0">{week(days,a,b)}<div class="mut" style="font-size:12.5px;margin-top:3px">{when}</div></div>
      <div style="padding:12px 0" class="mut">{until}</div><div style="padding:9px 20px 9px 0;display:flex;justify-content:flex-end"><button class="btn sm" type="button">删除…</button></div></div>{rule()}'''
zchip=lambda z,on=False: f'<button type="button" aria-pressed="{"true" if on else "false"}" style="height:36px;padding:0 12px;border:1px solid {"#1F6FC0" if on else "#6B7178"};background:{"#1F6FC0" if on else "#fff"};color:{"#fff" if on else "#16191D"};border-radius:2px;font:600 14px Barlow,\'Noto Sans SC\',sans-serif;cursor:pointer">{z}</button>'
body=f'''
{phead("授权","<b>现在 1 条授权在生效</b>：空调维修，到 12:00。",'<button class="btn" type="button">按防区临时撤防…</button>')}
<div style="flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 380px">
  <div style="min-width:0;overflow:auto;display:flex;flex-direction:column;background:#fff">
    <section aria-label="现在生效" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="padding:12px 20px"><h2 class="h2" style="font-size:17px">现在生效</h2></div>
      <div style="display:grid;grid-template-columns:120px minmax(0,1fr) auto;column-gap:14px;align-items:center">
        {rule()}<span class="lbl" style="padding-left:20px">授权</span>
        <div style="padding:12px 0"><b>空调维修</b> · 停车场、北区通道 · 09:00 → 12:00<div class="mut" style="font-size:13px">这两个防区里发现有人不报紧急报警，只记录</div></div>
        <button class="btn sm" type="button" style="margin-right:20px">提前结束</button>
        {rule()}<span class="lbl" style="padding-left:20px">临时撤防</span>
        <div style="padding:12px 0" class="mut">没有。现在全站撤防到 19:00；布防期间可以按防区临时撤防几小时，到点自动恢复。</div><span></span>
      </div>
    </section>
    <section aria-label="全部授权" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:baseline;gap:12px;padding:12px 20px"><h2 class="h2" style="font-size:17px">全部授权 4</h2><span class="mut" style="font-size:13px">每周重复的按星期画，底下有黑线的是今天</span></div>
      <div style="display:grid;grid-template-columns:150px 150px minmax(0,1fr) 110px auto;column-gap:16px;align-items:center">
        {rule()}<span class="lbl" style="padding:8px 0 8px 20px">人员</span><span class="lbl">范围</span><span class="lbl">星期和时间</span><span class="lbl">有效到</span><span></span>{rule()}
        {arow("空调维修","停车场、北区通道",[6],9,12,"11-15 09:00–12:00","今天","厂家 2 人")}
        {arow("保洁","2 号楼周边",[0,2,4,6],14,17,"一、三、五、日 14:00–17:00","2026-12-31")}
        {arow("垃圾车","南墙",[2],7,8,"每周三 07:00–08:00","长期")}
        {arow("夜班保安巡场","全站",[0,1,2,3,4,5,6],22,24,"每天 22:00–02:00（跨午夜）","长期","人走动不报")}
      </div>
    </section>
  </div>
  <aside aria-label="加授权" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0">
    <div style="padding:16px 20px;border-bottom:1px solid #D5D8DC">
      <h2 class="h2" style="font-size:17px">加授权</h2>
      <p class="mut" style="margin:4px 0 0;font-size:13px">授权生效期间，在授权的防区里发现有人不报紧急报警：摄像头入侵只记录，机器人看到的只记一条普通记录。</p>
    </div>
    <form onsubmit="return false" style="flex:1;min-height:0;display:flex;flex-direction:column"><div style="flex:1;min-height:0;overflow:auto;padding:16px 20px;display:flex;flex-direction:column;gap:14px">
      <div class="field"><label class="lbl">人员</label><input style="{INP}" placeholder="比如：维修人员"></div>
      <div class="field"><span class="lbl">范围</span>{segw(["全站","选定的防区"],"选定的防区","范围")}
        <div style="margin-top:8px">{tgrid(["北门","北区通道","停车场","南墙","2 号楼周边"],["北区通道","停车场"],2,"防区")}</div></div>
      <div class="field"><span class="lbl">什么时候</span>{segw(["某一天","每周重复"],"每周重复","重复")}
        <div style="margin-top:8px">{tgrid(list(DAYS),list(DAYS[:5]),7,"星期")}</div>
        <div style="margin-top:6px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px"><button class="btn sm" type="button" style="justify-content:center">每天</button><button class="btn sm" type="button" style="justify-content:center">工作日</button><button class="btn sm" type="button" style="justify-content:center">周末</button></div></div>
      <div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px"><div class="field"><label class="lbl">从</label><input style="{INP};min-width:0" value="22:00"></div><div class="field"><label class="lbl">到</label><input style="{INP};min-width:0" value="06:00"></div></div>
      <p class="mut" style="margin:-6px 0 0;font-size:12.5px">结束早于开始就是跨午夜。</p>
      <div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px"><div class="field"><label class="lbl">有效到 <span style="font-weight:400">· 可选</span></label><input style="{INP};min-width:0" placeholder="不填就一直有效"></div><div class="field"><label class="lbl">备注 <span style="font-weight:400">· 可选</span></label><input style="{INP};min-width:0"></div></div>
      </div>
      <div style="flex:none;padding:12px 20px;border-top:1px solid #D5D8DC;background:#fff"><div style="display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:8px"><button class="btn pri" type="button" style="justify-content:center">加上授权</button><button class="btn" type="button" style="justify-content:center">清空</button></div></div>
    </form>
  </aside>
</div>
'''
page("S-access.dc.html","现场设置 授权与临时撤防","access",body,{"home":B},full=True)

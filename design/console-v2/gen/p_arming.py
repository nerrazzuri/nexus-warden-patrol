from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
pct=lambda h: f'{h/24*100:.3f}%'
def day(name,armed,patrols,duty,today=False,exc=""):
    a=''.join(f'<div title="布防" style="position:absolute;left:{pct(x)};width:{pct(y-x)};top:20px;height:20px;background:#D5D8DC"></div>' for x,y in armed)
    d=''.join(f'<div title="有机器人在巡逻" style="position:absolute;left:{pct(x)};width:{pct(y-x)};top:20px;height:20px;background:#2A2F35"></div>' for x,y in duty)
    p=''.join(f'<span style="position:absolute;left:calc({pct(x)} - 20px);top:0;width:40px;text-align:center;font-size:10.5px;line-height:11px;color:#16191D;font-weight:600">{int(x):02d}:00</span><span title="排好的巡逻 {int(x):02d}:00" style="position:absolute;left:calc({pct(x)} - 5px);top:12px;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:7px solid #16191D"></span>' for x in patrols)
    return f'''<div style="display:contents"><span style="padding:20px 0 0 20px;font-weight:{700 if today else 600};{'text-decoration:underline 3px;text-underline-offset:5px;' if today else ''}">{name}{'<span class="mut" style="font-weight:400;font-size:12px;display:block;text-decoration:none">今天</span>' if today else ''}</span>
      <div style="position:relative;height:44px;margin:6px 0">{a}{d}{p}</div><span></span></div>{rule()}'''
wk=[(0,7),(19,24)]; we=[(0,7),(19,24)]
duty=[(0,0.8),(1.5,3.6),(4.6,6.8),(19,21.2),(21.5,24)]
rows=''.join(day(n,wk if i<5 else we,[1,4,22] if i<5 else [1,4,20,22],duty,today=(i==6)) for i,n in enumerate(["周一","周二","周三","周四","周五","周六","周日"]))
ticks=''.join(f'<span style="position:absolute;left:{h/24*100}%;transform:translateX(-50%)">{h:02d}:00</span>' for h in (0,6,12,18,24))
body=f'''
{phead("布防与巡逻","按时间表：现在撤防，<b>今天 19:00 布防</b>。",'<label style="display:flex;gap:8px;align-items:center;font-weight:600"><input type="checkbox" checked style="width:18px;height:18px">使用时间表</label>'+seg(["全站一起","按防区分开"],"全站一起","布防范围")+'<button class="btn" type="button">切换模式…</button><button class="btn pri" type="button">保存</button>')}
<div style="flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 380px">
  <div style="min-width:0;overflow:auto;display:flex;flex-direction:column;background:#fff">
    <section aria-label="一周" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:center;gap:18px;padding:12px 20px;flex-wrap:wrap">
        <h2 class="h2" style="font-size:17px;flex:1">一周</h2>
        <span style="display:inline-flex;gap:6px;align-items:center" class="mut"><span style="width:18px;height:12px;background:#D5D8DC"></span>布防</span>
        <span style="display:inline-flex;gap:6px;align-items:center" class="mut"><span style="width:18px;height:12px;background:#2A2F35"></span>布防中，有机器人在巡逻</span>
        <span style="display:inline-flex;gap:6px;align-items:center" class="mut"><span style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:7px solid #16191D"></span>排好的单次巡逻</span>
        
      </div>
      <div style="display:grid;grid-template-columns:72px minmax(0,1fr) 16px;column-gap:12px">
        {rule()}<span></span><div style="position:relative;height:22px;font-size:11px;color:#5A6068;margin-top:6px">{ticks}</div><span></span>{rule()}
        {rows}
      </div>
      <div style="display:flex;gap:10px;align-items:center;padding:10px 20px"><span class="mut" style="font-size:13px;flex:1">在空白处拖动加布防时段，拖两端改时间。</span><span class="mut" style="font-size:13px">把选中那天复制到：</span><button class="btn sm" type="button">工作日</button><button class="btn sm" type="button">周末</button><button class="btn sm" type="button">其余全部</button></div>
    </section>
    <div style="display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);border-bottom:1px solid #D5D8DC">
      <section aria-label="巡逻日程" style="background:#fff;border-bottom:1px solid #D5D8DC">
        <div style="display:flex;align-items:center;padding:12px 20px"><h2 class="h2" style="font-size:17px;flex:1">巡逻日程</h2><button class="btn sm" type="button">加一条</button></div>
        <table style="width:100%;border-collapse:collapse"><thead><tr><th>几点</th><th>路线</th><th>机器人</th><th>错过了</th></tr></thead><tbody>
          <tr><td>每天 01:00</td><td>guard-1</td><td>哪台空就哪台</td><td class="mut">迟 15 分内补跑</td></tr>
          <tr><td>每天 04:00</td><td>guard-1</td><td>A</td><td class="mut">跳过</td></tr>
          <tr><td>每天 22:00</td><td>guard-1</td><td>A</td><td class="mut">跳过</td></tr>
          <tr><td>周末 20:00</td><td>停车场一圈</td><td>哪台空就哪台</td><td class="mut">跳过</td></tr>
        </tbody></table>
      </section>
      <section aria-label="例外日期" style="background:#fff;border-bottom:1px solid #D5D8DC">
        <div style="display:flex;align-items:center;padding:12px 20px"><h2 class="h2" style="font-size:17px;flex:1">例外日期</h2><button class="btn sm" type="button">加例外</button></div>
        <div style="display:grid;grid-template-columns:auto minmax(0,1fr) auto;column-gap:12px;align-items:center">
          {rule()}<b style="padding:10px 0 10px 20px">12-24 → 12-26</b><span>全天布防</span><button class="btn sm" type="button" style="margin-right:20px">删除</button>
          {rule()}<b style="padding:10px 0 10px 20px">12-31</b><span>全天撤防</span><button class="btn sm" type="button" style="margin-right:20px">删除</button>
        </div>
        <p class="mut" style="margin:0;padding:8px 20px 12px;font-size:13px">加、删例外马上生效，不用按保存。</p>
      </section>
    </div>
  </div>
  <aside aria-label="布防时巡逻" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0;overflow:auto">
    <div style="padding:16px 20px;border-bottom:1px solid #D5D8DC">
      <h2 class="h2" style="font-size:17px">布防时巡逻</h2>
      <p class="mut" style="margin:4px 0 0;font-size:13px">布防期间机器人一圈接一圈地走，中间停下歇着、充电、换车。</p>
    </div>
    <div style="padding:16px 20px;display:flex;flex-direction:column;gap:14px">
      <div class="field"><label class="lbl">路线</label><select style="{INP}"><option>guard-1 · 一圈约 18 分</option></select></div>
      <div class="field"><label class="lbl">机器人</label><select style="{INP}"><option>A、B 轮换</option></select></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="field"><label class="lbl">两圈之间歇</label><select style="{INP}"><option>10 分钟</option></select></div>
        <div class="field"><label class="lbl">每圈顺序</label><select style="{INP}"><option>打乱</option><option>固定</option></select></div>
      </div>
      <div class="field"><label class="lbl">巡逻电量线</label><div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:10px;align-items:center"><select style="{INP}"><option>30%</option></select><span class="mut" style="font-size:13px">低于这个电量就回去充电，另一台接上</span></div></div>
      <label style="display:flex;gap:10px;align-items:center"><input type="checkbox" checked style="width:18px;height:18px">撤防时回待命点</label>
      <div style="border-top:1px solid #E3E5E8;padding-top:14px">
        <h3 class="h2" style="margin-bottom:8px">今晚会怎么跑</h3>
        <dl style="margin:0;display:grid;grid-template-columns:100px 1fr;gap:6px 10px">
          <dt class="mut">一次充电</dt><dd style="margin:0">A 约 7 圈，B 约 4 圈</dd>
          <dt class="mut">换车</dt><dd style="margin:0">22:00 A 跑日程那轮时 B 接上；之后轮流</dd>
          <dt class="mut">每个防区</dt><dd style="margin:0">至少 25 分钟经过一次</dd>
        </dl>
        <div style="position:relative;height:28px;margin-top:12px;background:#F2F3F1">
          <div style="position:absolute;left:0;width:36%;top:0;height:13px;background:#2A2F35"></div><span style="position:absolute;left:4px;top:0;font-size:10.5px;color:#fff;font-weight:700">A</span>
          <div style="position:absolute;left:36%;width:44%;top:15px;height:13px;background:#2A2F35"></div><span style="position:absolute;left:calc(36% + 4px);top:15px;font-size:10.5px;color:#fff;font-weight:700">B</span>
          <div style="position:absolute;left:80%;width:20%;top:0;height:13px;background:#2A2F35"></div>
        </div>
        <div class="mut" style="display:flex;justify-content:space-between;font-size:11px;margin-top:2px"><span>19:00</span><span>01:00</span><span>07:00</span></div>
      </div>
      <div style="border-top:1px solid #E3E5E8;padding-top:14px;display:flex;flex-direction:column;gap:6px">
        <h3 class="h2">昨晚</h3>
        <p style="margin:0">跑了 31 圈，每个防区最长 22 分钟没人经过。</p>
        <a href="#">看每一圈的记录</a>
      </div>
    </div>
  </aside>
</div>
'''
page("S-arming.dc.html","现场设置 布防与巡逻","arming",body,{"home":B},full=True)

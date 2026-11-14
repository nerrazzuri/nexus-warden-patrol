from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
H=lambda h: f'calc({h}/24*100%)'
def band(a,b,color,label="",txt="#fff"):
    return f'<div style="position:absolute;left:{a/24*100:.3f}%;width:{(b-a)/24*100:.3f}%;top:0;bottom:0;background:{color};color:{txt};font-size:12px;font-weight:600;display:flex;align-items:center;padding-left:6px;overflow:hidden;white-space:nowrap">{label}</div>'
def oband(a,b,label):
    return f'<div style="position:absolute;left:{a/24*100:.3f}%;width:{(b-a)/24*100:.3f}%;top:0;bottom:0;background:repeating-linear-gradient(135deg,#fff 0 4px,#D5D8DC 4px 5px);box-shadow:inset 0 0 0 2px #2A2F35;font-size:12px;font-weight:600;display:flex;align-items:center;padding-left:6px;overflow:hidden;white-space:nowrap">{label}</div>'
def lane(name,inner,note=""):
    return f'''<div style="display:contents"><span style="font-weight:600;padding:6px 0">{name}</span>
      <div style="position:relative;height:26px;background:#F2F3F1;margin:4px 0">{inner}</div><span class="mut" style="font-size:13px;padding:6px 0">{note}</span></div>'''
now=10+20/60
ticks=''.join(f'<span style="position:absolute;left:{h/24*100}%;transform:translateX(-50%)">{h:02d}</span>' for h in (0,3,6,9,12,15,18,21,24))
appr=lambda title,meta,where: f'''<li style="display:grid;grid-template-columns:20px minmax(0,1fr) auto;gap:4px 12px;padding:12px 20px;border-top:1px solid #E3E5E8;align-items:center"><span>{DISC}</span><div><b>{title}</b><div class="mut" style="font-size:13px">{meta}</div></div><a class="btn sm" href="#">{where}</a></li>'''
notice=lambda sign,title,meta,detail="",open_=False: f'''<li style="display:grid;grid-template-columns:20px minmax(0,1fr) auto;gap:4px 12px;padding:14px 20px;border-top:1px solid #E3E5E8">
      <span style="padding-top:3px">{sign}</span>
      <div><b>{title}</b><div class="mut" style="font-size:13px">{meta}</div>
        <button type="button" aria-expanded="{'true' if open_ else 'false'}" style="background:none;border:0;padding:4px 0 0;color:#1A5FA6;font:600 13px Barlow,'Noto Sans SC',sans-serif;cursor:pointer;display:inline-flex;gap:4px;align-items:center">技术细节 {chev('up' if open_ else 'down',12)}</button>
        {f'<div style="margin-top:6px;padding:8px 10px;background:#F5F6F4;border:1px solid #E3E5E8;font:13px/18px JetBrains Mono,ui-monospace,monospace;color:#2A2F35">{detail}</div>' if open_ else ''}</div>
      <div style="display:flex;gap:8px;align-items:flex-start"><button class="btn sm" type="button" title="看到了，解决前留在这里">知道了</button><button class="btn sm" type="button" title="已经解决，从这里拿掉">已处理</button></div></li>'''
body=f'''
{phead("概况","现在撤防，19:00 按时间表布防。机器人 2 台都在线。<b>4 件等你批准，2 条提醒。</b>",'<a class="btn" href="#">看报告</a>',DISC)}
<div style="flex:1;min-height:0;overflow:auto;display:grid;grid-template-columns:minmax(0,1fr) 400px;background:#fff">
  <div style="display:flex;flex-direction:column;min-width:0">
    <section aria-label="待处理事项" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:baseline;gap:12px;padding:14px 20px"><h2 class="h2" style="font-size:17px">待处理 6</h2><span class="mut" style="font-size:13px">蓝圆 = 等你批准，去对应页面做；黄三角 = 提醒：「知道了」留着，「已处理」拿掉</span></div>
      <ul style="list-style:none;margin:0;padding:0">
        {appr("机器人 C40388 请求加入","olga 的手机 09:41 发起 · 要核对 6 位码","去机器人页批准")}
        {appr("B 要换到 Wi-Fi estate-iot","08:12 从机器人发起","去 B 的设置批准")}
        {appr("Ravi 申请保安账号","09:58 从手机 App 发起","去人员页批准")}
        {appr("禁行区「水池」缩小了","demo 10:12 改 · 确认前仍避开原范围","去现场布置确认")}
        {notice('<span class="tri"></span>',"B 的电池在变差","涉及机器人：B · 11-14 起 · 满电能跑 2 小时 10 分，上个月 3 小时","battery.capacity_drop robot=C40011 full_runtime_min=130 baseline=180",False)}
        {notice('<span class="tri"></span>',"站点磁盘用了 71%","录像保留 30 天，按现在的速度约 40 天后满")}
      </ul>
    </section>
    <section aria-label="今天的安排" style="background:#fff;border-bottom:1px solid #D5D8DC;padding:16px 20px 18px">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px"><h2 class="h2" style="font-size:17px;flex:1">今天的安排 · 11-15 周日</h2><button class="btn sm" type="button">切换模式…</button><button class="btn sm" type="button">按防区临时撤防…</button></div>
      <div style="display:grid;grid-template-columns:72px minmax(0,1fr) 170px;column-gap:14px;align-items:center;position:relative">
        <span></span><div style="position:relative;height:16px;font-size:11px;color:#5A6068">{ticks}</div><span></span>
        {lane("布防",band(0,7,"#2A2F35","全部防区")+band(19,24,"#2A2F35","全部防区"),"时间表开着")}
        {lane("授权",oband(9,12,"空调维修")+oband(14,17,"保洁"),"2 条 · 空调维修在生效")}
        {lane("巡逻",band(1,3.5,"#9AA0A6","B")+band(4,6.5,"#9AA0A6","A")+band(10.08,10.5,"#9AA0A6","")+band(22,24,"#9AA0A6","A"),"4 轮 · A 现在在跑")}
        <span></span><div style="position:relative;height:0"><div style="position:absolute;left:{now/24*100:.2f}%;top:-118px;height:122px;width:2px;background:#16191D"></div><span style="position:absolute;left:{now/24*100:.2f}%;top:6px;transform:translateX(-50%);font-size:12px;font-weight:700">现在 10:20</span></div><span></span>
      </div>
      <p class="mut" style="margin:26px 0 0;font-size:13px">深色 = 布防；斜线框 = 授权（区内发现有人不报紧急报警）；灰 = 巡逻。点一段去改。</p>
    </section>
  </div>
  <div style="display:flex;flex-direction:column;border-left:1px solid #D5D8DC">
    <section aria-label="机器人" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:baseline;padding:14px 20px"><h2 class="h2" style="font-size:17px;flex:1">机器人</h2><a href="#">去机器人页</a></div>
      <div style="display:grid;grid-template-columns:44px 24px minmax(0,1fr) auto;gap:0 8px;align-items:center">
        {rule()}<span style="padding:12px 0 12px 20px"><span class="sq"></span></span><b style="font-size:16px">A</b><span>在跑停车场一圈 · 今天第 2 次</span><span class="mut" style="padding-right:20px">正常</span>
        {rule()}<span style="padding:12px 0 12px 20px"><span class="tri"></span></span><b style="font-size:16px">B</b><span>在线 · 今天巡逻 1 次</span><span style="padding-right:20px;color:#7A5200;font-weight:600">电池变差</span>
      </div>
    </section>
    <section aria-label="这周" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:baseline;padding:14px 20px"><h2 class="h2" style="font-size:17px;flex:1">这周 11-09 起</h2><a href="#">看报告</a></div>
      <dl style="margin:0;display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:0 14px">
        {rule()}<dt style="padding:10px 0 10px 20px">事件</dt><dd style="margin:0;padding:10px 0;font-weight:700;text-align:right">23 次</dd><dd class="mut" style="margin:0;padding:10px 20px 10px 0">比上周多 3 次</dd>
        {rule()}<dt style="padding:10px 0 10px 20px">误报</dt><dd style="margin:0;padding:10px 0;font-weight:700;text-align:right">9 次</dd><dd class="mut" style="margin:0;padding:10px 20px 10px 0">与上周持平</dd>
        {rule()}<dt style="padding:10px 0 10px 20px">巡逻走完</dt><dd style="margin:0;padding:10px 0;font-weight:700;text-align:right">26 / 28</dd><dd class="mut" style="margin:0;padding:10px 20px 10px 0">2 次电量不够</dd>
      </dl>
    </section>
  </div>
</div>
'''
page("S-home.dc.html","现场设置 概况","home",body,{"home":B},full=True)

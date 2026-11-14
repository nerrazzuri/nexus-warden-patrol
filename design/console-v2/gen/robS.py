from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
inp='height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit;background:#fff'
SQ='<span class="sq"></span>'
TRI='<span class="tri"></span>'
# 一张连续清单：标志 | 项目 | 状态 | 操作（固定宽，按钮等宽）
AW=168
def btn(t,cls="btn sm"): return f'<button class="{cls}" type="button" style="width:100%;justify-content:center">{t}</button>'
def r(group,sign,name,state,detail="",act=""):
    return f'''<div role="row" style="display:contents">
      <span style="padding:15px 0 0 20px;display:flex;justify-content:center">{sign}</span>
      <span style="padding:12px 0;font-weight:600">{name}</span>
      <span style="padding:12px 0"><span style="display:block">{state}</span>{f'<span class="mut" style="display:block;font-size:13px">{detail}</span>' if detail else ''}</span>
      <span style="padding:9px 20px 9px 0;display:flex;flex-direction:column;gap:6px">{act}</span></div>
      <div style="grid-column:1/-1;height:1px;background:#E3E5E8"></div>'''
def g(name): return f'<div style="grid-column:1/-1;padding:14px 20px 4px" class="lbl">{name}</div>'
todo=r("",DISC,"Wi-Fi",'<b>要换到 estate-iot，等你批准</b>',"现在 estate-staff · 08:12 从机器人发起 · 批准后约 30 秒断开再连上",btn("批准换网","btn sm pri")+btn("拒绝"))
todo+=r("",TRI,"电量",'<b style="color:#7A5200">18%，充电中</b>',"约 01:10 充到 80%；01:00 那一轮可能跑不完",btn("换一台跑 01:00"))
ok=g("连接")+r("",SQ,"证书","有效，到 2027-10-03","还有 687 天，到期前 30 天会提醒",btn("现在续"))
ok+=r("",SQ,"激活码","没有在用的","重装系统、要重新加入时才需要",btn("发新激活码…"))
ok+=g("机身")+r("",SQ,"时间","和站点差 0.2 秒","差超过 2 秒才需要对时",btn("对时"))
ok+=r("",SQ,"存储","用了 41%，没有待上传的录像","",btn("清理…"))
ok+=r("",SQ,"软件和地图","v1.20 · 地图第 4 版，和站点一致","",'')
ok+=r("",SQ,"机器人参数","速度、音量、避障距离","",btn("改参数…"))
ok+=g("排查")+r("",'',"日志",f'<span style="display:inline-flex;gap:8px"><select aria-label="日志种类" style="{inp};height:32px"><option>巡逻程序</option><option>视频</option><option>网络</option></select><select aria-label="时间范围" style="{inp};height:32px"><option>最近 1 小时</option><option>最近 24 小时</option></select></span>',"",btn("看日志"))
ok+=r("",'',"调试","关着","打开后 30 分钟自动关，售后远程排查用",btn("打开 30 分钟"))
ok+=r("",'',"诊断包","日志、配置和最近 10 分钟的状态，打包给工程师","",btn("下载诊断包"))
GRID=f'display:grid;grid-template-columns:44px 120px minmax(0,1fr) {AW+20}px;column-gap:12px;background:#fff'
body=f'''
<div style="flex:1;min-height:0;display:grid;grid-template-columns:248px minmax(0,1fr)">
  {fleet("B")}
  <div style="min-width:0;min-height:0;display:flex;flex-direction:column">
    {rhead("B","C40011",'<span class="chip warn"><span class="tri" style="border-left-width:5px;border-right-width:5px;border-bottom-width:9px"></span>充电中 18%</span>',"定位好 · 上次联系 1 秒前","设置")}
    <!-- 名字和派单是设置，不是体检项：放成表单条 -->
    <form style="flex:none;display:flex;align-items:center;gap:28px;padding:14px 24px;background:#fff;border-bottom:1px solid #D5D8DC" onsubmit="return false">
      <label style="display:flex;align-items:center;gap:10px"><span class="lbl">名字</span><input value="B" style="{inp};width:180px"><button class="btn sm" type="button">保存</button></label>
      <span style="width:1px;align-self:stretch;background:#E3E5E8"></span>
      <div style="display:flex;align-items:center;gap:10px"><span class="lbl">派单方式</span><div class="seg" role="radiogroup" aria-label="派单方式"><button class="btn sm on" type="button" role="radio" aria-checked="true">自动</button><button class="btn sm" type="button" role="radio" aria-checked="false">只手动</button></div><span class="mut" style="font-size:13px">自动：日程和报警都能派它</span></div>
    </form>
    <div style="flex:1;min-height:0;overflow:auto;display:grid;grid-template-columns:minmax(0,1fr) 300px;background:#fff">
      <div style="min-width:0;display:flex;flex-direction:column">
        <p style="margin:0;padding:16px 20px;font-size:17px;line-height:24px;border-bottom:1px solid #D5D8DC"><b>2 件要处理。</b>其余 9 项正常。</p>
        <div role="table" aria-label="B 的状况" style="{GRID}">
          {todo}
          <div style="grid-column:1/-1;display:flex;align-items:center;gap:10px;padding:10px 20px;background:#F8F9F8"><span class="mut">其余 9 项正常</span><button type="button" aria-expanded="true" style="background:none;border:0;padding:0;color:#1A5FA6;font:600 14px Barlow,'Noto Sans SC',sans-serif;cursor:pointer;display:inline-flex;gap:4px;align-items:center">收起 {chev("up",14)}</button></div>
          <div style="grid-column:1/-1;height:1px;background:#E3E5E8"></div>
          {ok}
        </div>
      </div>
      <aside aria-label="B 的经过和移除" style="padding:20px 24px;display:flex;flex-direction:column;gap:20px;border-left:1px solid #D5D8DC">
        <section>
          <h3 class="h2" style="margin-bottom:10px">这台的经过</h3>
          <ol style="list-style:none;margin:0;padding:0 0 0 14px;border-left:2px solid #D5D8DC;display:flex;flex-direction:column;gap:14px">
            <li><div class="mut" style="font-size:12px">11-15 08:12</div>申请换 Wi-Fi 到 estate-iot</li>
            <li><div class="mut" style="font-size:12px">11-02</div>换到地图第 4 版</li>
            <li><div class="mut" style="font-size:12px">10-28</div>升级到 v1.20</li>
            <li><div class="mut" style="font-size:12px">10-04</div>olga 用手机登记加入 · demo 批准</li>
          </ol>
        </section>
        <section style="border-top:1px solid #D5D8DC;padding-top:16px;display:flex;flex-direction:column;gap:16px">
          <h3 class="h2">重启和移除</h3>
          <p class="mut" style="margin:-8px 0 0;font-size:13px">它现在没在跑任务，可以重启。</p>
          <div style="display:flex;flex-direction:column;gap:6px">{btn("重启巡逻程序…")}<span class="mut" style="font-size:12.5px">约 1 分钟，期间不能派</span></div>
          <div style="display:flex;flex-direction:column;gap:6px">{btn("重启机器人…")}<span class="mut" style="font-size:12.5px">约 4 分钟，期间不能派</span></div>
          <div style="display:flex;flex-direction:column;gap:6px;border-top:1px solid #E3E5E8;padding-top:16px">{btn("解绑 B…","btn sm danger")}<span class="mut" style="font-size:12.5px">证书马上作废，所有机器人断开约 10 秒。要输入密码。</span></div>
        </section>
      </aside>
    </div>
  </div>
</div>
'''
page("R-A2.dc.html","机器人 设置","robots",body,{"home":B},full=True)

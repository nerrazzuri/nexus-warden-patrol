from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
def urow(name,login,role,last,status="",sel=False,stcol="#16191D"):
    st=SEL if sel else ''
    return f'''<a href="#" style="display:contents;color:#16191D;text-decoration:none">
      <span style="padding:12px 0 12px 20px;{st.replace('box-shadow:inset 0 0 0 2px #1F6FC0','')}"><b>{name}</b> <span class="mut" style="font-size:13px">{login}</span></span>
      <span style="padding:12px 0;{st.replace('box-shadow:inset 0 0 0 2px #1F6FC0','')}">{role}</span><span style="padding:12px 0;{st.replace('box-shadow:inset 0 0 0 2px #1F6FC0','')}" class="mut">{last}</span>
      <span style="padding:12px 20px 12px 0;color:{stcol};{st.replace('box-shadow:inset 0 0 0 2px #1F6FC0','')}">{status}</span></a>{rule()}'''
ev=lambda t,txt: f'<li style="display:grid;grid-template-columns:96px 1fr;gap:10px;padding:8px 0;border-top:1px solid #E3E5E8"><span class="mut">{t}</span><span>{txt}</span></li>'
body=f'''
{phead("人员","5 个账号，1 个工程师临时账号。<b>1 个申请等你批准。</b>",'<button class="btn" type="button">给工程师开临时账号…</button><button class="btn" type="button">添加人员</button>',DISC)}
<div style="flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 440px">
  <div style="min-width:0;overflow:auto;display:flex;flex-direction:column;background:#fff">
    <section aria-label="待批准" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:center;gap:10px;padding:12px 20px">{DISC}<h2 class="h2" style="font-size:17px">待批准 1</h2><span class="mut" style="font-size:13px">从手机 App 申请的账号</span></div>
      <div style="display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center">{rule()}
        <div style="padding:12px 20px"><b>Ravi</b> 申请当 <b>保安</b><div class="mut" style="font-size:13px">11-15 09:58 · 手机 vivo</div></div>
        <div style="display:flex;gap:8px;padding-right:20px"><button class="btn sm pri" type="button">批准…</button><button class="btn sm" type="button">拒绝</button></div></div>
    </section>
    <section aria-label="全部账号" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:baseline;gap:12px;padding:12px 20px"><h2 class="h2" style="font-size:17px">全部账号</h2><span class="mut" style="font-size:13px">每人一个账号；点一行看这个人的角色和操作记录</span></div>
      <div style="display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1.2fr)">
        {rule()}<span class="lbl" style="padding:8px 0 8px 20px">人</span><span class="lbl" style="padding:8px 0">角色</span><span class="lbl" style="padding:8px 0">最后登录</span><span class="lbl" style="padding:8px 0">状态</span>{rule()}
        {urow("demo","demo","管理员","今天 10:02","正常")}
        {urow("olga","olga","经理","今天 07:05","正常")}
        {urow("gina","gina","保安","昨天","正常",True)}
        {urow("vic","vic","只读","4 天前","正常")}
        {urow("林工","eng-0415","工程师（临时）","今天 09:40","还剩 3 小时 12 分")}
        {urow("Ahmad","ahmad","保安","11-02","已停用",stcol="#5A6068")}
      </div>
    </section>
    <details style="background:#fff;border-bottom:1px solid #D5D8DC"><summary style="list-style:none;padding:12px 20px;cursor:pointer;font-weight:600;display:flex;gap:6px;align-items:center">每个角色能做什么 {chev("down",12)}</summary>
      <p class="mut" style="margin:0;padding:0 20px 14px;font-size:13px">管理员：全部。经理：处理报警、急停、布防、排时间表，机器人页和报告只看。保安：处理报警、急停、布防、派机器人、遥控。只读：只看。工程师（临时）：同管理员，但不能管账号，到期自动失效。</p></details>
  </div>
  <aside aria-label="gina" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0;overflow:auto">
    <div style="padding:24px 24px 20px;border-bottom:1px solid #D5D8DC;display:flex;flex-direction:column;align-items:center;text-align:center;gap:14px">
      <div><h2 style="margin:0;font-size:24px;line-height:30px">gina</h2><span class="mut">登录名 gina · 正常</span></div>
      <div style="width:100%;display:flex;flex-direction:column;gap:6px;align-items:stretch"><span class="lbl">角色</span>{segw(["经理","保安","只读"],"保安","角色")}</div>
      <div style="width:100%;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px"><button class="btn sm" type="button" style="justify-content:center">重设密码…</button><button class="btn sm danger" type="button" style="justify-content:center">停用…</button><button class="btn sm danger" type="button" style="justify-content:center">删除…</button></div>
      <p class="mut" style="margin:0;font-size:12.5px;max-width:34em">停用会马上退出登录，重新启用前不能登录。删除后操作记录仍保留。</p>
    </div>
    <div style="padding:16px 24px">
      <h3 class="h2" style="margin-bottom:6px">gina 的操作记录</h3>
      <ul style="list-style:none;margin:0;padding:0">
        {ev("昨天 23:48","接手报警「北门有人翻越」")}
        {ev("昨天 23:49","派 A 去北门 · 当时在跑 guard-1")}
        {ev("昨天 23:55","结论：确认有人 · 通知到 olga")}
        {ev("昨天 22:09","关闭报警「停车场车辆滞留」· 结论：误报")}
        {ev("昨天 19:02","布防")}
        {ev("11-14 02:14","全部急停 · 02:16 恢复")}
      </ul>
      <a href="#" style="display:inline-block;margin-top:10px">在操作记录里看全部</a>
    </div>
  </aside>
</div>
'''
page("S-users.dc.html","现场设置 人员","users",body,{"home":B},full=True)

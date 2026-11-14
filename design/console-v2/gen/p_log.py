from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
days=[("11-09",3,1),("11-10",5,2),("11-11",2,0),("11-12",4,2),("11-13",3,1),("11-14",4,2),("11-15",2,1)]
mx=6
bars=''.join(f'''<div style="display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0">
  <div style="height:120px;width:100%;display:flex;align-items:flex-end;justify-content:center;gap:3px">
    <div title="事件 {e}" style="width:16px;height:{e/mx*100:.0f}%;background:#2A2F35"></div><div title="误报 {f}" style="width:16px;height:{max(f/mx*100,1):.0f}%;background:#B4B8BE"></div></div>
  <span style="font-size:12px" class="mut">{d}</span><span style="font-size:12px">{e} / {f}</span></div>''' for d,e,f in days)
def evr(t,robot,what,res,sign):
    return f'<tr><td>{t}</td><td>{robot}</td><td>{what}</td><td><span style="display:inline-flex;gap:6px;align-items:center">{sign}{res}</span></td></tr>'
def lg(t,who,grp,what):
    return f'<tr><td class="mut">{t}</td><td><b>{who}</b></td><td class="mut">{grp}</td><td>{what}</td></tr>'
body=f'''
{phead("报告","这个站点上谁做了什么，新的在前。11-09 到 11-15 共 214 条。",seg(["报告","操作记录"],"操作记录","看哪个"))}
<div style="flex:1;min-height:0;overflow:auto;background:#fff;display:flex;flex-direction:column">
  <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;padding:14px 28px;border-bottom:1px solid #D5D8DC">
    <div class="field"><label class="lbl">从</label><input style="{INP};width:130px" value="2026-11-09"></div>
    <div class="field"><label class="lbl">到</label><input style="{INP};width:130px" value="2026-11-15"></div>
    <div class="field"><label class="lbl">人</label><select style="{INP};width:170px"><option>所有人</option></select></div>
    <div class="field"><label class="lbl">操作</label><select style="{INP};width:170px"><option>全部</option><option>报警处理</option><option>布防撤防</option><option>机器人</option><option>现场布置</option><option>账号</option></select></div>
    <span style="flex:1"></span><button class="btn" type="button">导出 CSV</button>
  </div>
  <section aria-label="记录" style="background:#fff;border-bottom:1px solid #D5D8DC">
    <table style="width:100%;border-collapse:collapse"><thead><tr><th style="width:150px">时间</th><th style="width:140px">人</th><th style="width:130px">类别</th><th>做了什么</th></tr></thead><tbody>
      {lg("11-15 10:20","demo","布防撤防","南墙临时撤防到 12:30")}
      {lg("11-15 10:12","demo","现场布置","缩小禁行区「水池」· 等确认")}
      {lg("11-15 09:40","林工","账号","登录（工程师临时账号）")}
      {lg("11-15 09:31","demo","账号","给工程师开临时账号 林工 · 4 小时")}
      {lg("11-15 07:00","系统","布防撤防","按时间表撤防")}
      {lg("11-15 06:52","—","机器人","B 回到充电桩")}
      {lg("11-14 23:55","gina","报警处理","结论：确认有人 · 北门有人翻越")}
      {lg("11-14 23:49","gina","机器人","派 A 去北门")}
      {lg("11-14 23:48","gina","报警处理","接手报警「北门有人翻越」")}
      {lg("11-14 22:09","gina","报警处理","关闭「停车场车辆滞留」· 误报")}
      {lg("11-14 19:02","gina","布防撤防","布防")}
      {lg("11-14 18:30","olga","布防撤防","加例外 12-31 全天撤防")}
    </tbody></table>
    <div style="display:flex;align-items:center;gap:10px;padding:10px 20px;border-top:1px solid #E3E5E8"><span class="mut" style="flex:1">第 1–12 条，共 214 条</span><button class="btn sm" type="button" disabled style="color:#9AA0A6;border-color:#C7CACE">上一页</button><button class="btn sm" type="button">下一页</button></div>
  </section>
</div>
'''
page("S-log.dc.html","现场设置 操作记录","reports",body,{"home":B},full=True)

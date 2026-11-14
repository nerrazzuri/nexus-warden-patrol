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
{phead("报告","11-09 到 11-15：<b>事件 23 次</b>（比上周多 3），误报 9 次（7 次来自停车场摄像头）；巡逻派出 28 走完 26，7% 要人帮忙。",seg(["报告","操作记录"],"报告","看哪个"))}
<div style="flex:1;min-height:0;overflow:auto;background:#fff;display:flex;flex-direction:column">
  <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;padding:14px 28px;border-bottom:1px solid #D5D8DC">
    <div class="field"><span class="lbl">时间段</span>{seg(["今天","这周","上周","这个月"],"这周","时间段")}</div>
    <div class="field"><label class="lbl">从</label><input style="{INP};width:130px" value="2026-11-09"></div>
    <div class="field"><label class="lbl">到</label><input style="{INP};width:130px" value="2026-11-15"></div>
    <span class="mut" style="font-size:13px;padding-bottom:10px">最长 31 天</span>
    <span style="flex:1"></span><button class="btn" type="button">导出表格</button><button class="btn" type="button">导出 PDF</button>
  </div>
  
  <div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr);border-bottom:1px solid #D5D8DC">
    <section aria-label="按天" style="background:#fff;padding:14px 20px 16px">
      <div style="display:flex;gap:16px;align-items:center;margin-bottom:12px"><h2 class="h2" style="font-size:17px;flex:1">按天</h2>
        <span class="mut" style="display:inline-flex;gap:6px;align-items:center"><span style="width:12px;height:12px;background:#2A2F35"></span>事件</span>
        <span class="mut" style="display:inline-flex;gap:6px;align-items:center"><span style="width:12px;height:12px;background:#B4B8BE"></span>其中误报</span></div>
      <div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;border-bottom:1px solid #9AA0A6;padding-bottom:6px">{bars}</div>
    </section>
    <section aria-label="事件" style="background:#fff;border-left:1px solid #D5D8DC">
      <div style="display:flex;align-items:baseline;gap:12px;padding:12px 20px"><h2 class="h2" style="font-size:17px">事件 23</h2><span class="mut" style="font-size:13px">点一行去「记录与录像」看录像</span></div>
      <table style="width:100%;border-collapse:collapse"><thead><tr><th>时间</th><th>机器人</th><th>事件</th><th>结论</th></tr></thead><tbody>
        {evr("11-14 23:47","A","北门有人翻越","确认有人",'<span class="ring"></span>')}
        {evr("11-14 22:05","—","停车场（摄像头）车辆滞留","误报",'')}
        {evr("11-13 02:14","B","南墙有人","确认有人",'<span class="ring"></span>')}
        {evr("11-12 21:30","—","停车场（摄像头）有人","误报",'')}
        {evr("11-12 19:48","A","北区通道有人","已处理",'')}
      </tbody></table>
      <p class="mut" style="margin:0;padding:8px 20px 12px;font-size:13px">只列出前 5 件，导出表格看全部。</p>
    </section>
  </div>
</div>
'''
page("S-reports.dc.html","现场设置 报告","reports",body,{"home":B},full=True)

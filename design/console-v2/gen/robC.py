from shell import page
from common import *
B='<span class="chip warn" style="height:20px">2</span>'
SEL='background:#E3EEF9;box-shadow:inset 0 0 0 2px #1F6FC0'
mi=lambda t,h="": f'<a href="#" role="menuitem" style="display:flex;gap:8px;align-items:baseline;padding:7px 14px;color:#16191D;text-decoration:none"><span style="flex:1">{t}</span><span class="mut" style="font-size:12px">{h}</span></a>'
mg=lambda t: f'<div class="lbl" style="padding:10px 14px 2px">{t}</div>'
menu=f'''<div role="menu" aria-label="更多操作" style="position:absolute;left:0;top:48px;width:560px;background:#fff;border:1px solid #6B7178;box-shadow:0 12px 32px rgba(21,24,27,.18);display:grid;grid-template-columns:1fr 1fr;z-index:2">
  <div style="border-right:1px solid #E3E5E8;padding-bottom:8px">{mg("任务")}{mi("派一次巡逻…","这一圈后开始")}{mi("回家","先停下")}{mi("回待命点","先停下")}
    {mg("喊话与警示")}{mi("念常用话","3 句")}{mi("临时说一句…")}{mi("开警灯…","30 秒")}{mi("放警报声 / 英文警告")}
    {mg("身体")}{mi("趴下","会马上动")}{mi("云台…","0° / −10°")}{mi("雨刷 10 秒")}</div>
  <div style="padding-bottom:8px">{mg("这台的设置")}{mi("改名字")}{mi("派单方式","现在 自动")}{mi("发新激活码…")}{mi("Wi-Fi 换网审批","没有待批")}
    {mg("维护")}{mi("对时")}{mi("清理存储…","64%")}{mi("续证书","到 2027-10")}{mi("看日志 / 调试")}{mi("重启巡逻程序…")}{mi("重启机器人…")}
    <div style="border-top:1px solid #E3E5E8;margin-top:6px"></div><a href="#" role="menuitem" style="display:block;padding:9px 14px;color:#A41E24;text-decoration:none;font-weight:600">解绑 A…</a></div>
</div>'''
ev=lambda t,sign,txt: f'<li style="display:grid;grid-template-columns:52px 16px 1fr;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid #EDEEEC"><span class="mut">{t}</span>{sign}<span>{txt}</span></li>'
body=f'''
<div style="flex:none;padding:20px 32px 0;display:flex;align-items:baseline;gap:16px"><h1 class="h1" style="flex:1">机器人</h1><button class="btn sm" type="button">添加机器人</button></div>
<section aria-label="机队" style="flex:none;margin:12px 32px 0;background:#fff;border:1px solid #D5D8DC">
  <table style="width:100%;border-collapse:collapse"><thead><tr><th>机器人</th><th>在干什么</th><th style="text-align:right">电量</th><th>定位</th><th>网络</th><th>今天</th><th>派单</th><th>要注意</th></tr></thead><tbody>
    <tr style="{SEL}"><td><b>A</b> <span class="mut">C40221</span></td><td><span style="display:inline-flex;gap:6px;align-items:center"><span class="sq"></span>巡逻 guard-1</span></td><td style="text-align:right;font-weight:700">62%</td><td>好</td><td>好</td><td>3 轮 · 卡住 1 次</td><td>自动</td><td class="mut">—</td></tr>
    <tr><td><b>B</b> <span class="mut">C40011</span></td><td><span style="display:inline-flex;gap:6px;align-items:center"><span style="width:9px;height:9px;background:#9AA0A6"></span>充电中</span></td><td style="text-align:right;font-weight:700;color:#7A5200">18%</td><td>好</td><td>好</td><td>1 轮</td><td>自动</td><td><span style="display:inline-flex;gap:6px;align-items:center;color:#7A5200"><span class="tri" style="border-left-width:6px;border-right-width:6px;border-bottom-width:10px"></span>Wi-Fi 换网待批</span></td></tr>
    <tr style="background:#FCF1D6"><td><b>C40388</b></td><td colspan="6" style="color:#4A3600">请求加入 · olga 的手机 09:41 · 核对码 <b>482 913</b></td><td><a href="#">核对后批准…</a> · <a href="#">拒绝</a></td></tr>
  </tbody></table>
</section>
<div style="flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:32px;padding:24px 32px">
  <article aria-label="A" style="min-width:0;display:flex;flex-direction:column;gap:18px">
    <p style="margin:0;font-size:28px;line-height:36px;font-weight:700;max-width:22em">A 正在巡逻 guard-1 第 3 圈，<br>还要约 40 分钟，电量够跑完。</p>
    <div style="position:relative;display:flex;gap:8px;align-items:center">
      <button class="btn pri" type="button">停下并回家</button>
      <button class="btn" type="button">停下当前任务</button>
      <button class="btn" type="button" aria-expanded="true" aria-haspopup="menu" style="box-shadow:inset 0 0 0 1px #1F6FC0;border-color:#1F6FC0">更多操作 {chev("down",14)}</button>
      <span class="mut" style="margin-left:8px">急停在顶栏</span>
      {menu}
    </div>
    <section style="margin-top:8px">
      <h2 class="h2" style="margin-bottom:6px">今天的经过</h2>
      <div style="position:relative;height:18px;background:#ECEEEB;margin:6px 0 4px">
        <div style="position:absolute;left:0;width:22%;top:0;bottom:0;background:#9AA0A6"></div>
        <div style="position:absolute;left:22%;width:14%;top:0;bottom:0;background:#1F6FC0"></div>
        <div style="position:absolute;left:36%;width:0.8%;top:0;bottom:0;background:#C4262B"></div>
        <div style="position:absolute;left:37%;width:9%;top:0;bottom:0;background:#9AA0A6"></div>
        <div style="position:absolute;left:46%;width:6%;top:0;bottom:0;background:#1F6FC0"></div>
      </div>
      <div class="mut" style="display:flex;justify-content:space-between;font-size:12px"><span>12:00</span><span>16:00</span><span>20:00</span><span>24:00</span><span>04:00</span><span>08:00</span><span>12:00</span></div>
      <ol style="list-style:none;margin:8px 0 0;padding:0">
        {ev("22:00",'<span class="sq"></span>',"开始 guard-1（日程）")}
        {ev("20:52",'<span class="ring" style="width:11px;height:11px;border-width:2px"></span>',"卡住，东侧通道 · 2 分钟后自己脱困")}
        {ev("19:30",'<span style="width:9px;height:9px;background:#9AA0A6"></span>',"充电到 92%")}
      </ol>
    </section>
  </article>
  <aside aria-label="A 的状况" style="display:flex;flex-direction:column;gap:18px">
    <section><h2 class="h2" style="margin-bottom:8px">身体状况</h2>
      <dl style="margin:0;display:grid;grid-template-columns:76px 1fr;border-top:1px solid #D5D8DC">
        <dt class="mut" style="padding:8px 0;border-bottom:1px solid #E3E5E8">电池</dt><dd style="margin:0;padding:8px 0;border-bottom:1px solid #E3E5E8"><b>62%</b> · 约 2 小时 40 分 · 健康 94%</dd>
        <dt class="mut" style="padding:8px 0;border-bottom:1px solid #E3E5E8">姿态</dt><dd style="margin:0;padding:8px 0;border-bottom:1px solid #E3E5E8">站着</dd>
        <dt class="mut" style="padding:8px 0;border-bottom:1px solid #E3E5E8">定位</dt><dd style="margin:0;padding:8px 0;border-bottom:1px solid #E3E5E8">好 · 地图第 4 版</dd>
        <dt class="mut" style="padding:8px 0;border-bottom:1px solid #E3E5E8">网络</dt><dd style="margin:0;padding:8px 0;border-bottom:1px solid #E3E5E8">Wi-Fi 好 · 上次联系 2 秒前</dd>
        <dt class="mut" style="padding:8px 0;border-bottom:1px solid #E3E5E8">设备</dt><dd style="margin:0;padding:8px 0;border-bottom:1px solid #E3E5E8">云台、警灯、喇叭 正常</dd>
        <dt class="mut" style="padding:8px 0;border-bottom:1px solid #E3E5E8">存储</dt><dd style="margin:0;padding:8px 0;border-bottom:1px solid #E3E5E8">64% · 3 段待上传</dd>
        <dt class="mut" style="padding:8px 0;border-bottom:1px solid #E3E5E8">证书</dt><dd style="margin:0;padding:8px 0;border-bottom:1px solid #E3E5E8">到 2027-10-03</dd>
      </dl></section>
    <section><div style="display:flex;align-items:baseline;margin-bottom:6px"><h2 class="h2" style="flex:1">30 天报警</h2><a href="#">全部 4 条</a></div>
      <ol style="list-style:none;margin:0;padding:0">
        {ev("11-14",'<span class="ring" style="width:11px;height:11px;border-width:2px"></span>',"北门有人 · 确认有人")}
        {ev("11-12",'<span class="tri" style="border-left-width:6px;border-right-width:6px;border-bottom-width:10px"></span>',"定位变差 · 已恢复")}
      </ol></section>
  </aside>
</div>
'''
page("R-C.dc.html","机器人 方案C","robots",body,{"home":B},full=True)

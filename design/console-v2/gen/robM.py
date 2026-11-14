import shell
from shell import page
from common import *
shell.ROLE.update(who="olga · 经理",allow={"home","robots","arming","reports"})
row=lambda t,sign,txt: f'<li style="display:grid;grid-template-columns:44px 16px 1fr;gap:8px;align-items:center;padding:8px 0;border-top:1px solid #E3E5E8"><span class="mut">{t}</span>{sign}<span>{txt}</span></li>'
sel='height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit;background:#fff;min-width:0'
body=f'''
<div style="flex:1;min-height:0;display:grid;grid-template-columns:248px minmax(0,1fr)">
  {fleet("A",False).replace('<button class="btn sm" type="button">添加</button>','')}
  <div style="min-width:0;min-height:0;display:flex;flex-direction:column">
    <div style="flex:none;display:flex;align-items:center;gap:14px;padding:16px 24px;border-bottom:1px solid #D5D8DC;background:#fff">
      <h2 style="margin:0;font-size:28px;line-height:34px">A</h2><span class="chip ok"><span class="sq"></span>巡逻中</span><span class="mut">C40221 · 定位好 · 派单自动 · 上次联系 2 秒前</span></div>
    <div style="flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 344px">
      <section aria-label="A 的画面" style="min-width:0;display:flex;flex-direction:column;background:#fff">
        <figure style="margin:0;position:relative;flex:1;min-height:0;{NOISE};color:#ECEDEA">
          <figcaption style="position:absolute;left:0;right:0;top:0;display:flex;gap:10px;align-items:center;padding:8px 12px;background:rgba(0,0,0,.6)"><b>前摄像头</b><span style="font-weight:700;letter-spacing:.06em">实时</span><span style="flex:1"></span>
            <div role="radiogroup" aria-label="镜头" style="display:flex;gap:4px"><button type="button" role="radio" aria-checked="true" style="display:inline-flex;align-items:center;justify-content:center;height:30px;padding:0 12px;border:1px solid rgba(255,255,255,.35);background:rgba(10,12,14,.72);color:#fff;border-radius:2px;font:600 13px Barlow,'Noto Sans SC',sans-serif;cursor:pointer;background:#1F6FC0;border-color:#1F6FC0">前</button><button type="button" role="radio" aria-checked="false" style="display:inline-flex;align-items:center;justify-content:center;height:30px;padding:0 12px;border:1px solid rgba(255,255,255,.35);background:rgba(10,12,14,.72);color:#fff;border-radius:2px;font:600 13px Barlow,'Noto Sans SC',sans-serif;cursor:pointer">后</button><button type="button" role="radio" aria-checked="false" style="display:inline-flex;align-items:center;justify-content:center;height:30px;padding:0 12px;border:1px solid rgba(255,255,255,.35);background:rgba(10,12,14,.72);color:#fff;border-radius:2px;font:600 13px Barlow,'Noto Sans SC',sans-serif;cursor:pointer">热像</button></div></figcaption>
        </figure>
        <div style="flex:none;display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);border-top:1px solid #D5D8DC">
          <section style="padding:14px 24px">
            <div style="display:flex;align-items:baseline;margin-bottom:4px"><h3 class="h2" style="flex:1">今天</h3><a href="#">30 天报警 4 条</a></div>
            <ol style="list-style:none;margin:0;padding:0">
              {row("10:05","<span></span>","开始停车场一圈 · gina 派的")}
              {row("04:31",RINGN,"卡住，东侧通道 · 2 分钟后脱困")}
              {row("04:00","<span></span>","开始 guard-1")}
              {row("01:00","<span></span>","guard-1 走完")}
            </ol>
          </section>
          <section style="padding:14px 24px;border-left:1px solid #D5D8DC">
            <h3 class="h2" style="margin-bottom:4px">身体状况</h3>
            <dl style="margin:0;display:grid;grid-template-columns:92px 1fr;column-gap:8px">
              <dt class="mut" style="padding:8px 0;border-top:1px solid #E3E5E8">电池</dt><dd style="margin:0;padding:8px 0;border-top:1px solid #E3E5E8">62% · 约 2 小时 40 分</dd>
              <dt class="mut" style="padding:8px 0;border-top:1px solid #E3E5E8">网络</dt><dd style="margin:0;padding:8px 0;border-top:1px solid #E3E5E8">Wi-Fi 好</dd>
              <dt class="mut" style="padding:8px 0;border-top:1px solid #E3E5E8">设备</dt><dd style="margin:0;padding:8px 0;border-top:1px solid #E3E5E8">云台、警灯、喇叭 正常</dd>
              <dt class="mut" style="padding:8px 0;border-top:1px solid #E3E5E8">软件</dt><dd style="margin:0;padding:8px 0;border-top:1px solid #E3E5E8">v1.20 · 地图第 4 版</dd>
            </dl>
          </section>
        </div>
      </section>
      <aside aria-label="A 的任务" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0">
        <section style="padding:20px;border-bottom:1px solid #E3E5E8;display:flex;flex-direction:column;gap:10px">
          <span class="lbl">现在的任务</span>
          <p style="margin:0;font-size:17px;line-height:24px;font-weight:600">在跑停车场一圈，还要约 25 分钟。</p>
          <p class="mut" style="margin:0">gina 10:05 派的</p>
        </section>
        <section style="padding:20px;border-bottom:1px solid #E3E5E8;display:flex;flex-direction:column;gap:10px">
          <span class="lbl">派一次巡逻</span>
          <select aria-label="路线" style="{sel}"><option>guard-1 · 约 18 分</option><option>停车场一圈 · 约 25 分</option></select>
          <div style="display:grid;grid-template-columns:minmax(0,1fr) 96px;gap:8px"><select aria-label="圈数" style="{sel}"><option>跑 1 圈</option><option>跑 3 圈</option><option>一直巡逻</option></select><button class="btn" type="button" style="justify-content:center">排上</button></div>
          <p class="mut" style="margin:0;font-size:12.5px">这一圈跑完再开始；日程到点时日程优先。</p>
        </section>
        <section style="padding:20px;display:flex;flex-direction:column;gap:8px">
          <span class="lbl">现场控制</span>
          <p style="margin:0">云台、喊话、警灯、停下和遥控由值班保安在「值班」页做。</p>
          <p class="mut" style="margin:0;font-size:13px">现在值班：gina（在线）</p>
        </section>
      </aside>
    </div>
  </div>
</div>
'''
page("M-robot.dc.html","经理 机器人","robots",body,{},full=True)

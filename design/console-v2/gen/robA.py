from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
PAD='display:inline-flex;align-items:center;justify-content:center;padding:0;border:1px solid rgba(255,255,255,.35);background:rgba(10,12,14,.72);color:#fff;border-radius:2px;cursor:pointer'
sel='height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit;background:#fff'
body=f'''
<div style="flex:1;min-height:0;display:grid;grid-template-columns:248px minmax(0,1fr)">
  {fleet("A")}
  <div style="min-width:0;min-height:0;display:flex;flex-direction:column">
    {rhead("A","C40221",'<span class="chip ok"><span class="sq"></span>巡逻中</span>',"定位好 · 派单自动 · 上次联系 2 秒前","操作")}
    <div style="flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 344px">
      <section aria-label="A 的画面和对外" style="min-width:0;display:flex;flex-direction:column;padding:20px 24px;gap:14px;background:#F5F6F4">
        <figure style="margin:0;position:relative;flex:1;min-height:0;{NOISE};border:1px solid #2E333A;color:#ECEDEA">
          <figcaption style="position:absolute;left:0;right:0;top:0;display:flex;gap:10px;align-items:center;padding:8px 12px;background:rgba(0,0,0,.6)"><b>前摄像头</b><span style="color:#ECEDEA;font-weight:700;letter-spacing:.06em">实时</span><span style="flex:1"></span><span style="color:#B4B8BE">云台 水平 0° · 俯仰 −10°</span></figcaption>
          <div style="position:absolute;right:14px;bottom:14px">{dpad(PAD)}</div>
          <button type="button" style="{PAD};position:absolute;left:14px;bottom:14px;height:40px;padding:0 14px;font:600 14px Barlow,'Noto Sans SC',sans-serif">雨刷 10 秒</button>
        </figure>
        <div style="background:#fff;border:1px solid #D5D8DC;display:grid;grid-template-columns:88px minmax(0,1fr)">
          <div class="lbl" style="padding:14px 0 0 16px">喊话</div>
          <div style="padding:10px 16px 10px 0;display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button class="btn" type="button">私人区域，请离开</button><button class="btn" type="button">已录像，保安马上到</button><button class="btn" type="button">请出示通行证</button><a href="#" style="margin-left:4px">编辑常用话</a></div>
            <div style="display:flex;gap:8px"><input aria-label="临时说一句" style="flex:1;{sel}" placeholder="临时说一句，回车就念"><button class="btn" type="button">念</button><button class="btn" type="button">停止</button></div>
          </div>
          <div class="lbl" style="padding:14px 0 0 16px;border-top:1px solid #E3E5E8">警示</div>
          <div style="padding:10px 16px 10px 0;border-top:1px solid #E3E5E8;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <select aria-label="警灯时长" style="{sel}"><option>警灯 30 秒</option><option>60 秒</option><option>一直开</option></select><button class="btn" type="button">开警灯</button><button class="btn" type="button">关</button>
            <span style="width:1px;height:28px;background:#D5D8DC;margin:0 8px"></span>
            <button class="btn" type="button">放警报声</button><button class="btn" type="button">放英文警告</button>
          </div>
        </div>
      </section>
      <aside aria-label="A 的任务和状况" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0">
        <section style="padding:20px;border-bottom:1px solid #E3E5E8;display:flex;flex-direction:column;gap:12px">
          <p style="margin:0;font-size:17px;line-height:24px;font-weight:600">在跑停车场一圈，<br>还要约 25 分钟。</p>
          <p class="mut" style="margin:-6px 0 0">gina 10:05 派的</p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><button class="btn" type="button" style="justify-content:center">原地停下</button><button class="btn" type="button" style="justify-content:center">停下并回家</button></div>
          <p class="mut" style="margin:-4px 0 0;font-size:12px">原地停下：停在这里等你下一步。停下并回家：走回充电桩。</p>
          <div style="display:flex;gap:8px"><select aria-label="派一次巡逻" style="flex:1;min-width:0;{sel}"><option>guard-1 · 约 18 分</option></select><button class="btn" type="button">排上</button></div>
          <p class="mut" style="margin:-4px 0 0;font-size:12px">这一圈跑完再开始。</p>
        </section>
        <section style="padding:14px 20px;border-bottom:1px solid #E3E5E8;display:flex;align-items:center;gap:10px">
          <span style="flex:1">现在<b> 站着</b></span><button class="btn sm" type="button" title="会马上动身体，先确认旁边没人">趴下</button>
        </section>
        <section style="padding:14px 20px;border-bottom:1px solid #E3E5E8">
          <div style="display:flex;align-items:baseline;margin-bottom:8px"><h3 class="h2" style="flex:1">今天</h3><a href="#">30 天报警 4 条</a></div>
          <ol style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px">
            <li style="display:grid;grid-template-columns:44px 14px 1fr;gap:6px;align-items:center"><span class="mut">10:05</span><span></span><span>开始停车场一圈</span></li>
            <li style="display:grid;grid-template-columns:44px 14px 1fr;gap:6px;align-items:center"><span class="mut">04:31</span>{RINGN}<span>卡住，东侧通道 · 2 分钟后脱困</span></li>
            <li style="display:grid;grid-template-columns:44px 14px 1fr;gap:6px;align-items:center"><span class="mut">04:00</span><span></span><span>开始 guard-1</span></li>
          </ol>
        </section>
        <section style="padding:14px 20px">
          <h3 class="h2" style="margin-bottom:8px">身体状况</h3>
          <dl style="margin:0;display:grid;grid-template-columns:72px 1fr;gap:6px 8px">
            <dt class="mut">电池</dt><dd style="margin:0">62% · 约 2 小时 40 分 · 健康 94%</dd>
            <dt class="mut">网络</dt><dd style="margin:0">Wi-Fi 好</dd>
            <dt class="mut">存储</dt><dd style="margin:0">64% · 3 段待上传</dd>
            <dt class="mut">设备</dt><dd style="margin:0">云台、警灯、喇叭 正常</dd>
            <dt class="mut">软件</dt><dd style="margin:0">v1.20 · 地图第 4 版</dd>
          </dl>
          <p class="mut" style="margin:10px 0 0;font-size:12px">改名、激活码、Wi-Fi、维护、解绑在上面「设置」。</p>
        </section>
      </aside>
    </div>
  </div>
</div>
'''
page("R-A.dc.html","机器人 操作","robots",body,{"home":B},full=True)

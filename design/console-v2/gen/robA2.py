from shell import page
from common import *
B='<span class="chip warn" style="height:20px">2</span>'
PAD='display:inline-flex;align-items:center;justify-content:center;padding:0;border:1px solid rgba(255,255,255,.35);background:rgba(10,12,14,.72);color:#fff;border-radius:2px;cursor:pointer'
SEL='background:#E3EEF9;box-shadow:inset 0 0 0 2px #1F6FC0'
row=lambda name,code,sign,state,pct,pcol,note,sel=False: f'''
      <a href="#" style="display:grid;grid-template-columns:14px minmax(0,1fr) auto;gap:4px 10px;align-items:center;padding:12px 16px;border-bottom:1px solid #E3E5E8;text-decoration:none;color:#16191D;{SEL if sel else ''}"{' aria-current="true"' if sel else ''}>
        {sign}<b style="font-size:16px">{name} <span class="mut" style="font-weight:400;font-size:13px">{code}</span></b><b style="color:{pcol}">{pct}</b>
        <span></span><span class="mut">{state}</span><span class="mut" style="font-size:12px">{note}</span>
      </a>'''
body=f'''
<div style="flex:1;min-height:0;display:grid;grid-template-columns:248px minmax(0,1fr) 344px">
  <!-- 机队：窄条，点一台 -->
  <aside aria-label="机队" style="background:#fff;border-right:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0">
    <div style="display:flex;align-items:center;padding:16px;gap:8px;border-bottom:1px solid #E3E5E8"><h1 class="h2" style="flex:1;font-size:18px">机器人 2</h1><button class="btn sm" type="button">添加</button></div>
    {row("A","C40221",'<span class="sq"></span>',"巡逻 guard-1","62%","#16191D","",True)}
    {row("B","C40011",'<span class="tri" style="border-left-width:6px;border-right-width:6px;border-bottom-width:11px"></span>',"充电中 · Wi-Fi 换网待批","18%","#7A5200","")}
    <div style="margin-top:auto;padding:14px 16px;background:#FCF1D6;border-top:1px solid #EBD9A6">
      <div style="display:flex;gap:8px;align-items:center"><span class="tri"></span><b>1 台请求加入</b></div>
      <div style="color:#4A3600;margin:4px 0 10px">C40388 · olga 的手机 · 09:41<br>核对码 <b style="letter-spacing:.08em">482 913</b></div>
      <div style="display:flex;gap:8px"><button class="btn sm" type="button">核对后批准…</button><button class="btn sm" type="button">拒绝</button></div>
    </div>
  </aside>

  <!-- 中：它看到的 + 对外发声 -->
  <section aria-label="A 的画面和对外" style="min-width:0;display:flex;flex-direction:column;padding:20px 24px;gap:14px;background:#F5F6F4">
    <div style="display:flex;align-items:baseline;gap:12px">
      <h2 style="margin:0;font-size:28px;line-height:34px">A</h2>
      <span class="chip ok" style="align-self:center"><span class="sq"></span>巡逻中</span>
      <span class="mut">C40221 · 定位好 · 上次联系 2 秒前</span>
      <span style="flex:1"></span>
      <span class="mut">派单：<b style="color:#16191D">自动</b></span>
    </div>
    <figure style="margin:0;position:relative;flex:1;min-height:0;{NOISE};border:1px solid #2E333A;color:#ECEDEA">
      <figcaption style="position:absolute;left:0;right:0;top:0;display:flex;gap:10px;align-items:center;padding:8px 12px;background:rgba(0,0,0,.6)"><b>前摄像头</b><span style="color:#FF6166;font-weight:700">● 实时</span><span style="flex:1"></span><span style="color:#B4B8BE">云台 水平 0° · 俯仰 −10°</span></figcaption>
      <div style="position:absolute;right:14px;bottom:14px">{dpad(PAD)}</div>
      <button type="button" style="{PAD};position:absolute;left:14px;bottom:14px;height:40px;padding:0 14px;font:600 14px Barlow,'Noto Sans SC',sans-serif">雨刷 10 秒</button>
    </figure>
    <!-- 对外：一条连续的控制面，左边写动作，右边是选项 -->
    <div style="background:#fff;border:1px solid #D5D8DC;display:grid;grid-template-columns:88px minmax(0,1fr);">
      <div class="lbl" style="padding:14px 0 0 16px">喊话</div>
      <div style="padding:10px 16px 10px 0;display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" type="button">私人区域，请离开</button><button class="btn" type="button">已录像，保安马上到</button><button class="btn" type="button">请出示通行证</button><a href="#" style="align-self:center;margin-left:4px">编辑常用话</a></div>
        <div style="display:flex;gap:8px;width:100%"><input style="flex:1;height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 12px;font:inherit" placeholder="临时说一句，回车就念"><button class="btn" type="button">念</button><button class="btn" type="button">停止</button></div>
      </div>
      <div class="lbl" style="padding:14px 0 0 16px;border-top:1px solid #E3E5E8">警示</div>
      <div style="padding:10px 16px 10px 0;border-top:1px solid #E3E5E8;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <select aria-label="警灯时长" style="height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit"><option>警灯 30 秒</option><option>60 秒</option><option>一直开</option></select><button class="btn" type="button">开警灯</button><button class="btn" type="button">关</button>
        <span style="width:1px;height:28px;background:#D5D8DC;margin:0 8px"></span>
        <button class="btn" type="button">放警报声</button><button class="btn" type="button">放英文警告</button>
      </div>
    </div>
  </section>

  <!-- 右：它在干什么 → 能让它干什么；然后今天、身体状况 -->
  <aside aria-label="A 的任务和状况" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0">
    <section style="padding:20px;border-bottom:1px solid #E3E5E8;display:flex;flex-direction:column;gap:12px">
      <p style="margin:0;font-size:17px;line-height:24px;font-weight:600">在跑 guard-1 第 3 圈，<br>还要约 40 分钟。</p>
      <p class="mut" style="margin:-6px 0 0">22:00 按日程开始</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><button class="btn" type="button" style="justify-content:center">停下当前任务</button><button class="btn" type="button" style="justify-content:center">停下并回家</button></div>
      <div style="display:flex;gap:8px;width:100%"><select aria-label="派一次巡逻" style="flex:1;min-width:0;height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit"><option>停车场一圈 · 约 40 分</option></select><button class="btn" type="button">排上</button></div>
      <p class="mut" style="margin:-4px 0 0;font-size:12px">这一圈跑完再开始。回家、回待命点要先停下。</p>
    </section>
    <section style="padding:14px 20px;border-bottom:1px solid #E3E5E8;display:flex;align-items:center;gap:10px">
      <span style="flex:1">现在<b> 站着</b></span><button class="btn sm" type="button" title="会马上动身体，先确认旁边没人">趴下</button>
    </section>
    <section style="padding:14px 20px;border-bottom:1px solid #E3E5E8">
      <div style="display:flex;align-items:baseline;margin-bottom:8px"><h3 class="h2" style="flex:1">今天</h3><a href="#">30 天报警 4 条</a></div>
      <ol style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px">
        <li style="display:grid;grid-template-columns:44px 14px 1fr;gap:6px;align-items:center"><span class="mut">22:00</span><span class="sq"></span><span>开始 guard-1</span></li>
        <li style="display:grid;grid-template-columns:44px 14px 1fr;gap:6px;align-items:center"><span class="mut">20:52</span><span class="ring" style="width:11px;height:11px;border-width:2px"></span><span>卡住，东侧通道 · 2 分钟后脱困</span></li>
        <li style="display:grid;grid-template-columns:44px 14px 1fr;gap:6px;align-items:center"><span class="mut">19:30</span><span style="width:10px;height:10px;background:#9AA0A6"></span><span>充电到 92%</span></li>
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
    </section>
    <a href="#" class="btn" style="margin:auto 20px 20px;justify-content:space-between">这台的设置<span class="mut" style="font-weight:400">改名 · 激活码 · Wi-Fi · 维护 · 解绑</span></a>
  </aside>
</div>

<div style="position:absolute;inset:60px 0 0 232px;background:rgba(21,24,27,.32)"></div>
<aside role="dialog" aria-label="A 的设置" style="position:absolute;top:60px;right:0;bottom:0;width:560px;background:#fff;border-left:1px solid #6B7178;box-shadow:-16px 0 40px rgba(21,24,27,.18);display:flex;flex-direction:column">
  <div style="display:flex;align-items:center;gap:12px;padding:18px 24px;border-bottom:1px solid #D5D8DC"><h2 style="margin:0;font-size:22px;line-height:28px;flex:1">A 的设置</h2><span class="mut">C40221</span><button class="btn sm" type="button" aria-label="关闭">关闭</button></div>
  <div style="flex:1;overflow:auto;padding:4px 24px 24px">
    <h3 class="h2" style="margin:18px 0 2px">身份和派单</h3>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">名字</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><div style="display:flex;gap:8px;width:100%"><input style="height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 12px;font:inherit;flex:1" value="A"><button class="btn" type="button">保存</button></div><div class="mut" style="font-size:12px;width:100%">1/24 个字 · 清空就显示编号</div></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">派单方式</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><div class="seg" role="radiogroup"><button class="btn sm on" type="button" role="radio" aria-checked="true">自动</button><button class="btn sm" type="button" role="radio">只手动</button></div><div class="mut" style="font-size:12px;width:100%">自动 = 日程和报警可以派它</div></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">Wi-Fi</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center">estate-staff · 没有待批的换网</div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">激活码</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><button class="btn sm" type="button">发新激活码…</button> <span class="mut">旧码马上失效</span></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">证书</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center">到 2027-10-03 · 已登记 41 天</div></div>
    <h3 class="h2" style="margin:24px 0 2px">维护 <span class="mut" style="font-weight:400;font-size:13px">安装和售后用</span></h3>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">时间</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center">和站点差 0.2 秒 <button class="btn sm" type="button" style="">对时</button></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">存储</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center">64% · 3 段待上传 <button class="btn sm" type="button" style="">清理…</button></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">证书</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><button class="btn sm" type="button">现在续证书</button></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">机器人设置</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><button class="btn sm" type="button">改设置…</button> <span class="mut">速度、音量等</span></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">日志</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><div style="display:flex;gap:8px;width:100%"><select style="height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 12px;font:inherit;flex:1"><option>巡逻程序</option><option>视频</option><option>网络</option></select><select style="height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 12px;font:inherit"><option>最近 1 小时</option></select><button class="btn" type="button">看</button></div></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">调试</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><button class="btn sm" type="button">打开 30 分钟</button> <button class="btn sm" type="button">下载诊断包</button></div></div>
    <div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #E3E5E8"><span class="mut">重启</span><div style="display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center"><button class="btn sm danger" type="button">重启巡逻程序…</button> <button class="btn sm danger" type="button">重启机器人…</button><div class="mut" style="font-size:12px;width:100%">会停下几分钟。它现在在跑 guard-1，先停下再重启。</div></div></div>
    <div style="margin-top:24px;padding:16px;border:1px solid #E7B7BB;background:#FBE4E7;display:flex;gap:16px;align-items:center">
      <div style="flex:1"><b style="color:#8E1820">解绑 A</b><div style="color:#5E1418">证书马上作废。站点消息服务会重启，所有机器人断开约 10 秒。要输入密码。</div></div>
      <button class="btn danger" type="button" style="background:#fff">解绑…</button>
    </div>
  </div>
</aside>
'''
page("R-A2.dc.html","机器人 这台的设置","robots",body,{"home":B},full=True)

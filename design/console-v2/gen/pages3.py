from shell import page
B='<span class="chip warn" style="height:20px">2</span>'
FLEET='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">机器人</h1><p class="mut" style="margin:4px 0 0">派它干活、喊话警示、改设置、远程维护，都在这里。</p></div><button class="btn pri" type="button">添加机器人</button></div>
<section class="card" style="flex:none">
  <div style="display:flex;align-items:center;gap:12px;padding:10px 16px;background:#FCF1D6;border-bottom:1px solid #E3E5E8"><span class="tri"></span><b>1 台机器人请求加入</b><span style="color:#4A3600;flex:1">C40388 · 11-15 09:41 从 olga 的手机 · 核对码 482 913</span><button class="btn sm" type="button">核对后批准…</button><button class="btn sm" type="button">拒绝</button></div>
  <table style="width:100%;border-collapse:collapse"><thead><tr><th>机器人</th><th>现在</th><th style="text-align:right">电量</th><th>定位</th><th>网络</th><th>今天</th><th>派单</th><th>软件</th><th>要注意</th></tr></thead><tbody>
    <tr{SA}><td><b>A</b> <span class="mut">C40221</span></td><td><span class="chip ok"><span class="sq"></span>巡逻 guard-1</span></td><td style="text-align:right;font-weight:700">62%</td><td>好</td><td>Wi-Fi 好</td><td>巡逻 3 轮 · 卡住 1 次</td><td>自动</td><td>v1.20</td><td class="mut">—</td></tr>
    <tr{SB}><td><b>B</b> <span class="mut">C40011</span></td><td><span class="chip gray">充电中</span></td><td style="text-align:right;font-weight:700;color:#7A5200">18%</td><td>好</td><td><span class="chip warn">Wi-Fi 换网待批</span></td><td>巡逻 1 轮</td><td>自动</td><td>v1.20</td><td><span class="chip warn">2 件</span></td></tr>
  </tbody></table>
</section>
'''
SEL=' aria-selected="true" style="background:#E3EEF9;box-shadow:inset 0 0 0 2px #1F6FC0"'
def tabs(on):
    names=["控制与喊话","设备和报警记录","管理与维护"]
    return '<div role="tablist" aria-label="A 的功能" style="display:flex;border-bottom:1px solid #D5D8DC;padding:0 16px">'+''.join(
        f'<button type="button" role="tab" aria-selected="{"true" if n in on else "false"}" style="height:44px;padding:0 16px;border:0;background:transparent;font:600 14px Barlow,\'Noto Sans SC\',sans-serif;color:{"#0E3F70" if n in on else "#454A51"};box-shadow:{"inset 0 -3px 0 #1F6FC0" if n in on else "none"};cursor:pointer">{n}</button>' for n in names)+'</div>'
HEADA='''<div class="cardh"><h2 class="h2" style="font-size:20px">A</h2><span class="chip ok"><span class="sq"></span>巡逻中 · guard-1 第 3 圈</span><span class="mut">62% · 定位好 · 上次联系 2 秒前</span><span style="flex:1"></span><a class="btn sm" href="#">在值班页看画面</a></div>'''
ctrl=FLEET.replace('{SA}',SEL).replace('{SB}','')+'''
<section class="card" style="flex:none">
'''+HEADA+tabs(["控制与喊话"])+'''
  <!-- 第一行：任务。最常用、最要紧，横着一条 -->
  <div style="padding:14px 16px;border-bottom:1px solid #E3E5E8;display:flex;align-items:center;gap:20px;flex-wrap:wrap">
    <div style="min-width:220px"><div class="lbl">正在跑</div><b style="font-size:16px">guard-1 · 第 3 圈</b><div class="mut">22:00 按日程开始 · 还要约 40 分</div></div>
    <div style="display:flex;gap:8px"><button class="btn" type="button">停下当前任务</button><button class="btn" type="button">停下并回家</button></div>
    <span style="width:1px;align-self:stretch;background:#E3E5E8"></span>
    <div style="display:flex;gap:8px;align-items:center"><span class="lbl">派一次巡逻</span><select style="height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit;width:220px"><option>停车场一圈 · 约 40 分</option></select><button class="btn" type="button">巡逻</button></div>
    <span style="flex:1"></span>
    <div style="display:flex;gap:8px"><button class="btn" type="button" disabled style="border-style:dashed;color:#6B7178" title="正在跑任务：用「停下并回家」">回家</button><button class="btn" type="button">回待命点</button></div>
  </div>
  <!-- 第二行：左边喊话与警示（宽，出事时用），右边身体和云台（窄，偶尔用） -->
  <div style="display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr)">
    <div style="padding:16px;border-right:1px solid #E3E5E8;display:flex;flex-direction:column;gap:14px">
      <div style="display:flex;align-items:center"><h3 class="h2" style="flex:1">喊话与警示</h3><button class="btn sm" type="button">编辑常用话</button></div>
      <div style="display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;align-items:center"><span class="lbl">常用话</span>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px">
          <button class="btn" type="button" style="justify-content:center">私人区域，请离开</button>
          <button class="btn" type="button" style="justify-content:center">已录像，保安马上到</button>
          <button class="btn" type="button" style="justify-content:center">请出示通行证</button>
        </div></div>
      <div style="display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;align-items:center"><span class="lbl">临时说</span><div style="display:flex;gap:8px"><input style="flex:1;height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit" placeholder="输入要机器人念的话"><button class="btn" type="button" style="width:96px;justify-content:center">念</button><button class="btn" type="button">停止</button></div></div>
      <div style="display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;align-items:center"><span class="lbl">警灯</span><div style="display:flex;gap:8px"><select style="height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit;width:120px"><option>30 秒</option></select><button class="btn" type="button">开警灯</button><button class="btn" type="button">关</button></div></div>
      <div style="display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;align-items:center"><span class="lbl">提示音</span><div style="display:flex;gap:8px"><button class="btn" type="button">警报声</button><button class="btn" type="button">英文警告</button></div></div>
    </div>
    <div style="padding:16px;display:flex;flex-direction:column;gap:14px">
      <h3 class="h2">身体和云台</h3>
      <div style="display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;align-items:center"><span class="lbl">姿态</span><div style="display:flex;gap:8px;align-items:center"><button class="btn" type="button">站起来</button><button class="btn" type="button">趴下</button><span class="mut">现在站着</span></div></div>
      <div style="display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;align-items:center"><span class="lbl">云台</span>
        <div style="display:flex;gap:16px;align-items:center">
          <div style="display:grid;grid-template-columns:repeat(3,44px);gap:4px">
            <span></span><button class="btn" type="button" aria-label="上" style="padding:0;justify-content:center;width:44px;height:44px">上</button><span></span>
            <button class="btn" type="button" aria-label="左" style="padding:0;justify-content:center;width:44px;height:44px">左</button><button class="btn" type="button" style="padding:0;justify-content:center;width:44px;height:44px;font-size:12px">回中</button><button class="btn" type="button" aria-label="右" style="padding:0;justify-content:center;width:44px;height:44px">右</button>
            <span></span><button class="btn" type="button" aria-label="下" style="padding:0;justify-content:center;width:44px;height:44px">下</button><span></span>
          </div>
          <span class="mut">水平 0°<br>俯仰 −10°</span>
        </div></div>
      <div style="display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;align-items:center"><span class="lbl">雨刷</span><div><button class="btn" type="button">擦 10 秒</button></div></div>
      <p class="mut" style="margin:0;font-size:12px">姿态会马上动身体，先确认旁边没人；跑任务时要先停下。</p>
    </div>
  </div>
</section>
<p class="mut" style="margin:0">经理看这页时：只显示状态和记录，按钮都不出现。急停在顶栏，所有页面都有。</p>
'''
page("S-robots.dc.html","现场设置 机器人","robots",ctrl,{"home":B})

mgmt=FLEET.replace('{SB}',SEL).replace('{SA}','').replace(HEADA,'')+'''
<section class="card" style="flex:none">
<div class="cardh"><h2 class="h2" style="font-size:20px">B</h2><span class="chip gray">充电中</span><span class="mut">18% · 在充电桩 1 · 上次联系 1 秒前</span><span style="flex:1"></span></div>
'''+tabs(["管理与维护"]).replace('A 的功能','B 的功能')+'''
  <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr))">
    <div style="padding:16px;border-right:1px solid #E3E5E8;display:flex;flex-direction:column;gap:14px">
      <h3 class="h2">管理</h3>
      <div style="display:flex;align-items:center;gap:12px;padding:10px 12px;background:#FCF1D6"><span class="tri"></span><div style="flex:1"><b>Wi-Fi 换网等你批准</b><div style="color:#4A3600">从 estate-staff 换到 estate-iot · 11-15 08:12 申请</div></div><button class="btn sm" type="button">批准</button><button class="btn sm" type="button">拒绝</button></div>
      <div class="field"><label class="lbl">名字</label><div style="display:flex;gap:8px"><input style="flex:1" value="B"><button class="btn" type="button">保存名字</button></div><span class="mut" style="font-size:12px">1/24 个字 · 清空就显示编号 C40011</span></div>
      <div class="field"><span class="lbl">派单方式</span><div class="seg" role="radiogroup" style="align-self:flex-start"><button class="btn sm on" type="button" role="radio" aria-checked="true">自动（按日程、报警派）</button><button class="btn sm" type="button" role="radio">只手动</button></div></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div><div class="lbl">登记于</div>10-04</div><div><div class="lbl">证书到期</div>2027-10-03</div>
        <div><div class="lbl">地图</div>第 4 版 · 和站点一致</div><div><div class="lbl">软件</div>v1.20</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn sm" type="button">发新激活码…</button><span class="mut" style="align-self:center">旧码马上失效</span></div>
      <div style="border-top:1px solid #E3E5E8;padding-top:12px;display:flex;align-items:center;gap:12px"><div style="flex:1"><b>解绑 B</b><div class="mut">证书马上作废。站点的消息服务会重启，所有机器人断开约 10 秒。要输入密码。</div></div><button class="btn danger" type="button">解绑…</button></div>
    </div>
    <div style="padding:16px;display:flex;flex-direction:column;gap:14px">
      <h3 class="h2">维护 <span class="mut" style="font-weight:400;font-size:13px">· 安装和售后用</span></h3>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
        <div><div class="lbl">存储</div>64% · 3 段待上传</div><div><div class="lbl">时间</div>和站点差 0.2 秒</div><div><div class="lbl">温度</div>41 °C</div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        <button class="btn sm" type="button">对时</button><button class="btn sm" type="button">清理存储…</button><button class="btn sm" type="button">续证书</button><button class="btn sm" type="button">改机器人设置…</button>
      </div>
      <div class="field"><label class="lbl">看日志</label><div style="display:flex;gap:8px"><select style="flex:1"><option>巡逻程序</option><option>视频</option><option>网络</option></select><select><option>最近 1 小时</option></select><button class="btn" type="button">看</button></div></div>
      <div style="display:flex;flex-wrap:wrap;gap:8px"><button class="btn sm" type="button">打开调试 30 分钟</button><button class="btn sm" type="button">下载诊断包</button></div>
      <div style="border-top:1px solid #E3E5E8;padding-top:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center"><span class="mut" style="flex:1;min-width:200px">重启会让它停下几分钟，确认没在跑任务。</span><button class="btn danger" type="button">重启巡逻程序…</button><button class="btn danger" type="button">重启机器人…</button></div>
    </div>
  </div>
</section>
'''
page("S-robots2.dc.html","现场设置 机器人管理","robots",mgmt,{"home":B})

import json
p='/tmp/claude-1000/-home-liang-Projects-D1-Max/ecced633-c546-490e-ade6-e46e90a431ed/scratchpad/dcanvas/project/canvas.json'
c=json.load(open(p))
c['boards']['S-robots.dc.html']['title']="现场设置 · 机器人（控制、喊话与警示）"
c['boards']['S-robots2.dc.html']={"x":0,"y":7060,"w":1536,"h":960,"title":"现场设置 · 机器人（管理、维护）"}
if 'S-robots2.dc.html' not in c['order']: c['order'].insert(c['order'].index('S-robots.dc.html')+1,'S-robots2.dc.html')
c['notes']['nS']['x']=1616; c['notes']['nS']['y']=7060
c['notes']['nR']={"x":2440,"y":7060,"w":520,"text":"机器人页按老页面的功能全部保留：\n· 控制：停任务、停下并回家、派一次巡逻、回家、回待命点、站起来/趴下、云台、雨刷\n· 喊话与警示：常用话（可编辑）、临时说一句、警灯和时长、录好的提示音\n· 设备和报警记录：设备状态、最近 30 天报警\n· 管理：批准加入、Wi-Fi 换网审批、改名、自动/只手动、新激活码、解绑\n· 维护：对时、清理存储、续证书、设置、日志、调试、重启\n上面是整个机队的表，点一行，下面换成那台的功能。","size":"m","fill":"blue"}
json.dump(c,open(p,'w'),ensure_ascii=False)
print("ok")

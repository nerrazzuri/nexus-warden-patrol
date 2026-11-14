from shell import page
BADGE='<span class="chip warn" style="height:20px">2</span>'
# 概况：只回答「现场能不能正常值班」+ 要我做的事
home='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">概况</h1><p class="mut" style="margin:4px 0 0">今晚能不能正常值班，以及需要你处理的事。</p></div><a class="btn" href="#">看操作记录</a></div>
<section class="card" style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr))">
  <div style="padding:16px 20px;border-right:1px solid #E3E5E8"><div class="lbl">今晚值班</div><div style="display:flex;align-items:center;gap:8px;margin-top:6px"><span class="tri"></span><b style="font-size:20px">能跑，有 2 件事</b></div><div class="mut">01:00 那一轮 B 可能电量不够</div></div>
  <div style="padding:16px 20px;border-right:1px solid #E3E5E8"><div class="lbl">机器人</div><b style="font-size:20px;display:block;margin-top:6px">2 / 2 在线</b><div class="mut">A 62% · B 18% 充电中</div></div>
  <div style="padding:16px 20px;border-right:1px solid #E3E5E8"><div class="lbl">布防</div><b style="font-size:20px;display:block;margin-top:6px">19:00 → 07:00</b><div class="mut">按时间表 · 明天没有例外</div></div>
  <div style="padding:16px 20px"><div class="lbl">最近 7 天报警</div><b style="font-size:20px;display:block;margin-top:6px">23 条 · 误报 9</b><div class="mut">误报多在停车场摄像头 2</div></div>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">要你处理 2</h2><span class="lbl">按影响今晚值班排序</span></div>
  <div style="display:flex;align-items:center;gap:16px;padding:14px 16px;border-bottom:1px solid #E3E5E8"><span class="tri"></span><div style="flex:1"><b>B 的电池在退化</b><div class="mut">满电只能巡逻 2 小时 10 分（上个月 3 小时）。01:00 那一轮要 2 小时 30 分。</div></div><a class="btn sm" href="#">改由 A 跑这一轮</a><a class="btn sm" href="#">看电池记录</a></div>
  <div style="display:flex;align-items:center;gap:16px;padding:14px 16px"><span class="tri"></span><div style="flex:1"><b>停车场摄像头 2 一周误报 7 次</b><div class="mut">都是施工车停留。可以给停车场加一个「车辆停留」的忽略时段。</div></div><a class="btn sm" href="#">去设置</a><button class="btn sm" type="button">先不管</button></div>
</section>
<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px">
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">现场准备情况</h2><span class="chip ok">6 / 7</span></div>
  <ul style="list-style:none;margin:0;padding:8px 16px;display:flex;flex-direction:column">
    <li style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #E3E5E8"><span class="sq"></span><span style="flex:1">地图 · 第 4 版已确认</span></li>
    <li style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #E3E5E8"><span class="sq"></span><span style="flex:1">防区 7 个 · 巡逻路线 2 条</span></li>
    <li style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #E3E5E8"><span class="sq"></span><span style="flex:1">固定摄像头 6 个，全部有画面</span></li>
    <li style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #E3E5E8"><span class="sq"></span><span style="flex:1">充电桩 1 个，B 已对上</span></li>
    <li style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #E3E5E8"><span class="sq"></span><span style="flex:1">保安 2 人，都绑了手机</span></li>
    <li style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #E3E5E8"><span class="sq"></span><span style="flex:1">报警推送 · 上次测试 11-14 通过</span></li>
    <li style="display:flex;gap:10px;align-items:center;padding:8px 0"><span class="tri"></span><span style="flex:1">经理 olga 没设第二联系人</span><a href="#">去设</a></li>
  </ul>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">技术提醒</h2><span class="lbl">给安装和售后看，不影响今晚</span></div>
  <ul style="list-style:none;margin:0;padding:8px 16px;display:flex;flex-direction:column;color:#2A2F35">
    <li style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #E3E5E8"><span style="width:44px" class="mut">11-14</span><span style="flex:1">有新版本 v1.21 可以升级</span><a href="#">看</a></li>
    <li style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #E3E5E8"><span style="width:44px" class="mut">11-12</span><span style="flex:1">A 在东侧通道定位变差过 3 次</span><a href="#">看</a></li>
    <li style="display:flex;gap:10px;padding:8px 0"><span style="width:44px" class="mut">11-10</span><span style="flex:1">站点磁盘用了 71%（录像保留 30 天）</span><a href="#">看</a></li>
  </ul>
</section>
</div>
'''
page("S-home.dc.html","现场设置 概况","home",home,{"home":BADGE})

robots='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">机器人</h1><p class="mut" style="margin:4px 0 0">每台机器人的状态、电池、连接，以及添加和移除。</p></div><button class="btn pri" type="button">添加机器人</button></div>
<div style="display:grid;grid-template-columns:420px minmax(0,1fr);gap:20px;min-height:0">
  <section class="card" style="align-self:start">
    <table style="width:100%;border-collapse:collapse"><thead><tr><th>名字</th><th>状态</th><th style="text-align:right">电量</th></tr></thead><tbody>
      <tr aria-selected="true" style="background:#E3EEF9;box-shadow:inset 0 0 0 2px #1F6FC0"><td><b>A</b><div class="mut">C40221</div></td><td><span class="chip ok"><span class="sq"></span>巡逻中</span></td><td style="text-align:right;font-weight:700">62%</td></tr>
      <tr><td><b>B</b><div class="mut">C40011</div></td><td><span class="chip gray">充电中</span></td><td style="text-align:right;font-weight:700;color:#7A5200">18%</td></tr>
    </tbody></table>
  </section>
  <section class="card">
    <div class="cardh"><h2 class="h2" style="font-size:20px">A</h2><span class="mut">C40221 · 已绑定 41 天</span><span style="flex:1"></span><a class="btn sm" href="#">在值班页看</a><button class="btn sm" type="button">改名字</button></div>
    <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-bottom:1px solid #E3E5E8">
      <div style="padding:14px 16px;border-right:1px solid #E3E5E8"><div class="lbl">现在</div><b style="display:block;font-size:18px;margin-top:4px">巡逻中 · guard-1</b><div class="mut">第 3 圈 · 定位好</div></div>
      <div style="padding:14px 16px;border-right:1px solid #E3E5E8"><div class="lbl">电池</div><b style="display:block;font-size:18px;margin-top:4px">62% · 约 2 小时 40 分</b><div class="mut">健康 94% · 循环 212 次</div></div>
      <div style="padding:14px 16px"><div class="lbl">连接</div><b style="display:block;font-size:18px;margin-top:4px">Wi-Fi 好 · 延迟 38 ms</b><div class="mut">证书到 2027-10-03</div></div>
    </div>
    <div style="padding:14px 16px;border-bottom:1px solid #E3E5E8">
      <div class="lbl" style="margin-bottom:8px">最近 24 小时</div>
      <div style="position:relative;height:28px;background:#F2F3F1">
        <div style="position:absolute;left:0;width:30%;top:0;bottom:0;background:#1F6FC0"></div>
        <div style="position:absolute;left:30%;width:22%;top:0;bottom:0;background:#9AA0A6"></div>
        <div style="position:absolute;left:52%;width:9%;top:0;bottom:0;background:#1F6FC0"></div>
        <div style="position:absolute;left:61%;width:0.8%;top:0;bottom:0;background:#C4262B"></div>
        <div style="position:absolute;left:62%;width:38%;top:0;bottom:0;background:#1F6FC0"></div>
      </div>
      <div class="mut" style="display:flex;gap:16px;margin-top:6px;font-size:12px"><span>蓝 巡逻 14 小时</span><span>灰 充电 6 小时</span><span style="color:#A41E24">红 卡住 1 次（20:52 东侧通道，已脱困）</span></div>
    </div>
    <div style="padding:14px 16px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;border-bottom:1px solid #E3E5E8">
      <div><div class="lbl" style="margin-bottom:6px">它会跑的巡逻</div><div>每晚 22:00、04:00 · guard-1</div><a href="#">去「布防与巡逻」改</a></div>
      <div><div class="lbl" style="margin-bottom:6px">站立 / 趴下</div><div class="mut">在手机 App 的遥控页操作，这里不放，避免误点。</div></div>
    </div>
    <div style="padding:14px 16px;display:flex;align-items:center;gap:12px">
      <div style="flex:1"><b>移除这台机器人</b><div class="mut">站点不再接收它的数据，它的证书马上作废。要输入你的密码。</div></div>
      <button class="btn danger" type="button">移除 A…</button>
    </div>
  </section>
</div>
'''
page("S-robots.dc.html","现场设置 机器人","robots",robots,{"home":BADGE})

users='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">人员与权限</h1><p class="mut" style="margin:4px 0 0">谁能登录、能做什么、报警推给谁。</p></div><button class="btn pri" type="button">添加人员</button></div>
<section class="card">
  <table style="width:100%;border-collapse:collapse"><thead><tr><th>人</th><th>角色</th><th>报警推送</th><th>手机</th><th>最后登录</th><th></th></tr></thead><tbody>
    <tr><td><b>demo</b></td><td>管理员</td><td class="mut">不推</td><td class="mut">—</td><td>今天 10:02</td><td style="text-align:right"><a href="#">改</a></td></tr>
    <tr><td><b>olga</b></td><td>经理</td><td>P1 全部 · 夜里只推 P1</td><td><span class="chip ok">已绑定</span></td><td>今天 07:05</td><td style="text-align:right"><a href="#">改</a></td></tr>
    <tr style="background:#E3EEF9;box-shadow:inset 0 0 0 2px #1F6FC0"><td><b>gina</b></td><td>保安</td><td>P1、P2</td><td><span class="chip ok">已绑定</span></td><td>昨天 18:55</td><td style="text-align:right"><a href="#">改</a></td></tr>
    <tr><td><b>vic</b></td><td>只看</td><td class="mut">不推</td><td><span class="chip gray">没绑</span></td><td>11-09</td><td style="text-align:right"><a href="#">改</a></td></tr>
  </tbody></table>
</section>
<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px">
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">gina · 保安</h2></div>
  <div style="padding:16px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px">
    <div class="field"><label class="lbl">角色</label><select><option>保安</option></select></div>
    <div class="field"><label class="lbl">推送哪些报警</label><select><option>P1、P2</option></select></div>
    <div class="field"><label class="lbl">手机</label><div style="display:flex;gap:8px;align-items:center;height:40px"><span class="chip ok">vivo · 11-02 绑定</span><button class="btn sm" type="button">换手机</button></div></div>
    <div class="field"><label class="lbl">密码</label><div style="display:flex;gap:8px;align-items:center;height:40px"><button class="btn sm" type="button">重设密码</button></div></div>
  </div>
  <div style="padding:0 16px 16px;display:flex;gap:8px"><button class="btn pri" type="button">保存</button><span style="flex:1"></span><button class="btn danger" type="button">停用 gina</button></div>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">每个角色能做什么</h2></div>
  <table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr><th></th><th>管理员</th><th>经理</th><th>保安</th><th>只看</th></tr></thead><tbody>
    <tr><td>看值班页、录像</td><td>能</td><td>能</td><td>能</td><td>能</td></tr>
    <tr><td>接手、结案报警</td><td>能</td><td>能</td><td>能</td><td class="mut">不能</td></tr>
    <tr><td>全部急停、切换布防</td><td>能</td><td>能</td><td>能</td><td class="mut">不能</td></tr>
    <tr><td>派机器人、遥控</td><td>能</td><td class="mut">不能</td><td>能</td><td class="mut">不能</td></tr>
    <tr><td>改布防时间、巡逻日程</td><td>能</td><td>能</td><td class="mut">不能</td><td class="mut">不能</td></tr>
    <tr><td>看机器人页、报告</td><td>能</td><td>能（只看）</td><td class="mut">不能</td><td class="mut">不能</td></tr>
    <tr><td>现场布置、来访、加人</td><td>能</td><td class="mut">不能</td><td class="mut">不能</td><td class="mut">不能</td></tr>
  </tbody></table>
</section>
</div>
'''
page("S-users.dc.html","现场设置 人员与权限","users",users,{"home":BADGE})
print("ok")

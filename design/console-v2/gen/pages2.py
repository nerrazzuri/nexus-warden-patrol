from shell import page
B='<span class="chip warn" style="height:20px">2</span>'
# 现场布置：一张图，七种东西是图层；左边选正在改的那层，右边是选中的那一项
layout='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">现场布置</h1><p class="mut" style="margin:4px 0 0">地图第 4 版（已确认）。所有东西画在同一张图上，选一层来改。</p></div><span class="chip warn"><span class="tri" style="border-left-width:5px;border-right-width:5px;border-bottom-width:9px"></span>有 1 处没保存</span><button class="btn" type="button">放弃改动</button><button class="btn pri" type="button">保存</button></div>
<div style="flex:1;min-height:640px;display:grid;grid-template-columns:240px minmax(0,1fr) 320px;gap:0" class="card">
  <aside aria-label="图层" style="border-right:1px solid #E3E5E8;display:flex;flex-direction:column">
    <div class="lbl" style="padding:12px 16px 6px">正在改</div>
    <div role="radiogroup" aria-label="图层" style="display:flex;flex-direction:column">
      <label style="display:flex;align-items:center;gap:10px;padding:8px 16px;background:#E3EEF9;box-shadow:inset 0 0 0 1px #9DC1E6;font-weight:700"><input type="radio" name="ly" checked><span style="flex:1">防区</span><span class="mut">7</span></label>
      <label style="display:flex;align-items:center;gap:10px;padding:8px 16px"><input type="radio" name="ly"><span style="flex:1">禁行区和限速区</span><span class="mut">3</span></label>
      <label style="display:flex;align-items:center;gap:10px;padding:8px 16px"><input type="radio" name="ly"><span style="flex:1">巡逻路线</span><span class="mut">2</span></label>
      <label style="display:flex;align-items:center;gap:10px;padding:8px 16px"><input type="radio" name="ly"><span style="flex:1">路网</span><span class="mut">41 个点</span></label>
      <label style="display:flex;align-items:center;gap:10px;padding:8px 16px"><input type="radio" name="ly"><span style="flex:1">待命点和充电桩</span><span class="mut">3</span></label>
      <label style="display:flex;align-items:center;gap:10px;padding:8px 16px"><input type="radio" name="ly"><span style="flex:1">固定摄像头</span><span class="mut">6</span></label>
    </div>
    <div class="lbl" style="padding:16px 16px 6px">一起显示（只看）</div>
    <div style="display:flex;flex-direction:column;padding:0 16px;gap:4px">
      <label style="display:flex;gap:8px;align-items:center;min-height:28px"><input type="checkbox" checked>禁行区</label>
      <label style="display:flex;gap:8px;align-items:center;min-height:28px"><input type="checkbox" checked>巡逻路线</label>
      <label style="display:flex;gap:8px;align-items:center;min-height:28px"><input type="checkbox">路网</label>
      <label style="display:flex;gap:8px;align-items:center;min-height:28px"><input type="checkbox" checked>摄像头</label>
    </div>
    <p class="mut" style="margin:auto 16px 16px;font-size:12px">换地图版本、重新建图在「高级」里。</p>
  </aside>
  <figure style="margin:0;position:relative;background:#E9EBEA;min-width:0">
    <div style="position:absolute;left:12px;top:12px;display:flex;gap:8px;z-index:1">
      <div class="seg" role="group" aria-label="工具"><button class="btn sm on" type="button" aria-pressed="true">选择</button><button class="btn sm" type="button">画新防区</button><button class="btn sm" type="button">改形状</button></div>
      <button class="btn sm" type="button">撤销</button>
    </div>
    <svg viewBox="0 0 640 560" style="position:absolute;inset:0;width:100%;height:100%" role="img" aria-label="地图：7 个防区，选中北门">
      <rect x="0" y="0" width="640" height="560" fill="#E9EBEA"/>
      <path d="M50 60 H590 V230 H450 V520 H200 V230 H50 Z" fill="#fff" stroke="#6B7178" stroke-width="2.5"/>
      <rect x="230" y="270" width="190" height="170" fill="#F2F3F1" stroke="#9AA0A6" stroke-dasharray="6 4"/><text x="325" y="360" fill="#5A6068" font-size="14" text-anchor="middle">2 号楼</text>
      <rect x="60" y="70" width="140" height="110" fill="#1F6FC0" fill-opacity=".14" stroke="#1F6FC0" stroke-width="3"/>
      <text x="130" y="130" fill="#0E3F70" font-size="14" font-weight="700" text-anchor="middle">北门</text>
      <g fill="#fff" stroke="#1F6FC0" stroke-width="2.5"><rect x="54" y="64" width="12" height="12"/><rect x="194" y="64" width="12" height="12"/><rect x="54" y="174" width="12" height="12"/><rect x="194" y="174" width="12" height="12"/></g>
      <g fill="#6B7178" fill-opacity=".08" stroke="#6B7178" stroke-width="1.5"><rect x="210" y="70" width="200" height="110"/><rect x="420" y="70" width="160" height="150"/><rect x="210" y="450" width="230" height="60"/><rect x="460" y="300" width="0" height="0"/></g>
      <g fill="#454A51" font-size="13" text-anchor="middle"><text x="310" y="130">北区通道</text><text x="500" y="150">停车场</text><text x="325" y="485">南墙</text></g>
      <path d="M90 200 H560" stroke="#1F6FC0" stroke-width="2" stroke-opacity=".45" fill="none"/>
      <rect x="455" y="235" width="0" height="0"/>
      <path d="M470 240 h60 v40 h-60 z" fill="#C4262B" fill-opacity=".12" stroke="#C4262B" stroke-width="2" stroke-dasharray="5 3"/><text x="500" y="300" fill="#A41E24" font-size="12" text-anchor="middle">水池 · 禁行</text>
      <g><rect x="120" y="58" width="14" height="10" fill="#16191D"/><rect x="560" y="64" width="14" height="10" fill="#16191D"/><rect x="318" y="512" width="14" height="10" fill="#16191D"/></g>
    </svg>
    <figcaption style="position:absolute;right:12px;bottom:12px;background:#fff;border:1px solid #D5D8DC;padding:6px 10px" class="mut">拖角上的点改形状 · 比例 1 格 = 5 米</figcaption>
  </figure>
  <aside aria-label="选中的防区" style="border-left:1px solid #E3E5E8;padding:16px;display:flex;flex-direction:column;gap:14px">
    <h2 class="h2">防区 · 北门</h2>
    <div class="field"><label class="lbl">名字</label><input value="北门"></div>
    <div class="field"><label class="lbl">有人进入时</label><select><option>P1 报警 · 推送保安和经理</option></select></div>
    <div class="field"><label class="lbl">谁去看</label><select><option>离得最近的空闲机器人</option></select><span class="mut" style="font-size:12px">也会先打开摄像头 3</span></div>
    <div class="field"><label class="lbl">布防</label><select><option>跟全站一起</option></select></div>
    <div style="background:#F8F9F8;border:1px solid #E3E5E8;padding:10px 12px"><div class="lbl">大小</div><div>28 × 22 米 · 在第 4 版地图上</div></div>
    <span style="flex:1"></span>
    <button class="btn danger" type="button" style="align-self:flex-start">删除这个防区</button>
  </aside>
</div>
'''
page("S-layout.dc.html","现场设置 现场布置","layout",layout,{"home":B})

days=["一","二","三","四","五","六","日"]
rows=""
for i,d in enumerate(days):
    ext='<div style="position:absolute;left:0;width:29.2%;top:6px;bottom:6px;background:#1F6FC0"></div><div style="position:absolute;left:79.2%;right:0;top:6px;bottom:6px;background:#1F6FC0"></div>'
    if i>=5: ext='<div style="position:absolute;left:0;width:29.2%;top:6px;bottom:6px;background:#1F6FC0"></div><div style="position:absolute;left:66.7%;right:0;top:6px;bottom:6px;background:#1F6FC0"></div>'
    pat=''.join(f'<span style="position:absolute;left:calc({p}% - 5px);top:9px;width:10px;height:10px;border-radius:50%;background:#fff;border:2px solid #0E3F70;box-sizing:border-box"></span>' for p in ([4.2,91.7] if i<5 else [4.2,79.2,91.7]))
    rows+=f'<div style="display:flex;align-items:center;gap:8px"><span style="width:44px;font-weight:600">周{d}</span><div style="position:relative;flex:1;height:32px;background:#F2F3F1;border:1px solid #E3E5E8">{ext}{pat}</div></div>\n'
arming=f'''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">布防与巡逻</h1><p class="mut" style="margin:4px 0 0">什么时候布防、布防时机器人跑哪几轮。两件事在同一张周表上看。</p></div><label style="display:flex;align-items:center;gap:8px;font-weight:600"><input type="checkbox" checked style="width:18px;height:18px">使用这个时间表</label><button class="btn pri" type="button">保存</button></div>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">一周</h2>
    <span style="display:inline-flex;align-items:center;gap:6px" class="mut"><span style="width:16px;height:10px;background:#1F6FC0"></span>布防</span>
    <span style="display:inline-flex;align-items:center;gap:6px" class="mut"><span style="width:10px;height:10px;border-radius:50%;border:2px solid #0E3F70;box-sizing:border-box"></span>一轮巡逻</span>
    <span class="mut">在空白处拖动加布防时段，点圆点改巡逻</span></div>
  <div style="padding:12px 16px;display:flex;flex-direction:column;gap:6px">
    <div style="display:flex;gap:8px"><span style="width:44px"></span><div class="mut" style="flex:1;display:flex;justify-content:space-between;font-size:12px"><span>00:00</span><span>04:00</span><span>08:00</span><span>12:00</span><span>16:00</span><span>20:00</span><span>24:00</span></div></div>
{rows}  </div>
</section>
<div style="display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:20px">
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">巡逻 · 每晚</h2><button class="btn sm" type="button">加一轮</button></div>
  <table style="width:100%;border-collapse:collapse"><thead><tr><th>开始</th><th>路线</th><th>机器人</th><th>大约用时</th><th>电量够不够</th></tr></thead><tbody>
    <tr><td>01:00</td><td>guard-1</td><td>B</td><td>2 小时 30 分</td><td><span class="chip warn">B 只够 2 小时 10 分</span> <span class="new">新</span></td></tr>
    <tr><td>04:00</td><td>guard-1</td><td>A</td><td>2 小时 30 分</td><td><span class="chip ok">够</span></td></tr>
    <tr><td>22:00</td><td>guard-1</td><td>A</td><td>2 小时 30 分</td><td><span class="chip ok">够</span></td></tr>
    <tr><td>周六、日 20:00</td><td>停车场一圈</td><td>谁空闲</td><td>40 分</td><td><span class="chip ok">够</span></td></tr>
  </tbody></table>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">例外日期</h2><button class="btn sm" type="button">加例外</button></div>
  <ul style="list-style:none;margin:0;padding:8px 16px">
    <li style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #E3E5E8"><b style="width:110px">12-24 → 12-26</b><span style="flex:1">全天布防（放假）</span><a href="#">删</a></li>
    <li style="display:flex;gap:10px;padding:8px 0"><b style="width:110px">12-31</b><span style="flex:1">全天撤防（活动）</span><a href="#">删</a></li>
  </ul>
  <p class="mut" style="margin:0;padding:0 16px 14px">加、删例外马上生效，不用按「保存」。</p>
</section>
</div>
'''
page("S-arming.dc.html","现场设置 布防与巡逻","arming",arming,{"home":B})

access='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">来访与授权</h1><p class="mut" style="margin:4px 0 0">有人要来时，先在这里登记：到点只撤防他要去的防区，走了自动恢复。</p></div><button class="btn pri" type="button">登记来访</button></div>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">现在生效 1</h2></div>
  <div style="display:flex;align-items:center;gap:16px;padding:14px 16px;background:#FCF1D6">
    <span class="tri"></span>
    <div style="flex:1"><b>空调维修 · 2 人</b><div style="color:#4A3600">停车场、北区通道 临时撤防 · 09:00 → 12:00（还有 1 小时 40 分）· olga 登记</div></div>
    <button class="btn sm" type="button">延长 1 小时</button><button class="btn sm" type="button">现在结束</button>
  </div>
</section>
<div style="display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:20px">
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">排好的</h2></div>
  <table style="width:100%;border-collapse:collapse"><thead><tr><th>什么时候</th><th>谁</th><th>哪些防区</th><th></th></tr></thead><tbody>
    <tr><td>11-16 14:00 → 17:00</td><td>保洁 3 人</td><td>2 号楼周边</td><td style="text-align:right"><a href="#">改</a></td></tr>
    <tr><td>每周三 07:00 → 08:00</td><td>垃圾车</td><td>南墙</td><td style="text-align:right"><a href="#">改</a></td></tr>
  </tbody></table>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">登记来访</h2></div>
  <div style="padding:16px;display:flex;flex-direction:column;gap:12px">
    <div class="field"><label class="lbl">谁 · 做什么</label><input value="空调维修"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div class="field"><label class="lbl">从</label><input value="11-15 09:00"></div><div class="field"><label class="lbl">到</label><input value="11-15 12:00"></div></div>
    <fieldset style="border:0;margin:0;padding:0"><legend class="lbl" style="padding:0;margin-bottom:6px">撤防哪些防区</legend>
      <div style="display:flex;flex-wrap:wrap;gap:6px"><span class="chip" style="background:#1F6FC0;color:#fff;height:32px">停车场 ✓</span><span class="chip" style="background:#1F6FC0;color:#fff;height:32px">北区通道 ✓</span><span class="chip gray" style="height:32px">北门</span><span class="chip gray" style="height:32px">南墙</span><span class="chip gray" style="height:32px">2 号楼周边</span></div></fieldset>
    <p class="mut" style="margin:0">其余防区照常布防。机器人巡逻会绕开撤防的防区吗？<b style="color:#16191D">不绕</b>，只是不报警。</p>
  </div>
</section>
</div>
<p class="mut" style="margin:0">要全站临时撤防 4 小时，用顶栏的「布防中」菜单。</p>
'''
page("S-access.dc.html","现场设置 来访与授权","access",access,{"home":B})

reports='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">报告与操作记录</h1><p class="mut" style="margin:4px 0 0">给业主看的周报，和谁在什么时候做了什么。</p></div><div class="seg" role="tablist"><button class="btn sm on" type="button" role="tab" aria-selected="true">周报</button><button class="btn sm" type="button" role="tab">操作记录</button></div></div>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">11-08 → 11-14</h2><button class="btn sm" type="button">上一周</button><button class="btn sm" type="button">导出 PDF</button></div>
  <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border-bottom:1px solid #E3E5E8">
    <div style="padding:14px 16px;border-right:1px solid #E3E5E8"><div class="lbl">巡逻完成</div><b style="font-size:24px">26 / 28</b><div class="mut">2 轮电量不够跳过</div></div>
    <div style="padding:14px 16px;border-right:1px solid #E3E5E8"><div class="lbl">巡逻里程</div><b style="font-size:24px">61.4 公里</b></div>
    <div style="padding:14px 16px;border-right:1px solid #E3E5E8"><div class="lbl">报警</div><b style="font-size:24px">23</b><div class="mut">确认有人 4 · 误报 9</div></div>
    <div style="padding:14px 16px;border-right:1px solid #E3E5E8"><div class="lbl">P1 平均接手</div><b style="font-size:24px">48 秒</b><div class="mut">最慢 3 分 10 秒（11-11 03:12）</div></div>
    <div style="padding:14px 16px"><div class="lbl">机器人离线</div><b style="font-size:24px">14 分钟</b><div class="mut">B 东侧通道 Wi-Fi 弱</div></div>
  </div>
  <div style="padding:16px;display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:24px">
    <div><div class="lbl" style="margin-bottom:8px">每天报警</div>
      <svg viewBox="0 0 420 150" style="width:100%;height:150px" role="img" aria-label="每天报警数：周一 2，周二 4，周三 3，周四 6，周五 3，周六 2，周日 3">
        <g fill="#1F6FC0"><rect x="10" y="100" width="40" height="30"/><rect x="70" y="70" width="40" height="60"/><rect x="130" y="85" width="40" height="45"/><rect x="190" y="40" width="40" height="90"/><rect x="250" y="85" width="40" height="45"/><rect x="310" y="100" width="40" height="30"/><rect x="370" y="85" width="40" height="45"/></g>
        <g fill="#16191D" font-size="12" text-anchor="middle"><text x="30" y="95">2</text><text x="90" y="65">4</text><text x="150" y="80">3</text><text x="210" y="35">6</text><text x="270" y="80">3</text><text x="330" y="95">2</text><text x="390" y="80">3</text></g>
        <g fill="#5A6068" font-size="12" text-anchor="middle"><text x="30" y="146">一</text><text x="90" y="146">二</text><text x="150" y="146">三</text><text x="210" y="146">四</text><text x="270" y="146">五</text><text x="330" y="146">六</text><text x="390" y="146">日</text></g>
      </svg></div>
    <div><div class="lbl" style="margin-bottom:8px">报警最多的地方</div>
      <table style="width:100%;border-collapse:collapse"><tbody>
        <tr><td>停车场 · 摄像头 2</td><td style="text-align:right;font-weight:700">9</td><td class="mut">7 次误报</td></tr>
        <tr><td>北门</td><td style="text-align:right;font-weight:700">6</td><td class="mut">2 次有人</td></tr>
        <tr><td>南墙</td><td style="text-align:right;font-weight:700">5</td><td class="mut">2 次有人</td></tr>
      </tbody></table></div>
  </div>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">最近操作</h2><a href="#">看全部操作记录</a></div>
  <table style="width:100%;border-collapse:collapse"><tbody>
    <tr><td style="width:120px">11-15 09:02</td><td style="width:80px">olga</td><td>登记来访：空调维修，停车场、北区通道 到 12:00</td></tr>
    <tr><td>11-15 02:14</td><td>gina</td><td>全部急停，02:16 恢复</td></tr>
    <tr><td>11-14 16:40</td><td>demo</td><td>防区「北门」改大（第 4 版地图）</td></tr>
  </tbody></table>
</section>
'''
page("S-reports.dc.html","现场设置 报告","reports",reports,{"home":B})

system='''
<div style="display:flex;align-items:flex-end;gap:16px"><div style="flex:1"><h1 class="h1">高级</h1><p class="mut" style="margin:4px 0 0">安装、售后用。日常值班不需要来这里。</p></div></div>
<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px">
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">地图版本</h2><button class="btn sm" type="button">重新建图…</button></div>
  <table style="width:100%;border-collapse:collapse"><thead><tr><th>版本</th><th>建于</th><th>状态</th><th></th></tr></thead><tbody>
    <tr><td><b>第 4 版</b></td><td>11-02</td><td><span class="chip ok">在用 · 已确认</span></td><td style="text-align:right"><a href="#">编辑…</a></td></tr>
    <tr><td>第 3 版</td><td>10-20</td><td><span class="chip gray">旧版</span></td><td style="text-align:right"><a href="#">换回这版…</a></td></tr>
  </tbody></table>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">定位</h2></div>
  <div style="padding:12px 16px;display:flex;flex-direction:column;gap:8px">
    <div style="display:flex;gap:10px;align-items:center"><b style="width:24px">A</b><span class="chip ok">定位好</span><span class="mut" style="flex:1">匹配 0.92</span><button class="btn sm" type="button">重新找位置</button></div>
    <div style="display:flex;gap:10px;align-items:center"><b style="width:24px">B</b><span class="chip ok">定位好</span><span class="mut" style="flex:1">匹配 0.88 · 在充电桩</span><button class="btn sm" type="button">重新找位置</button></div>
  </div>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">升级</h2></div>
  <div style="padding:12px 16px;display:flex;align-items:center;gap:12px"><div style="flex:1"><b>v1.21 可以升级</b><div class="mut">现在 v1.20 · 升级要 6 分钟，机器人会停下，白天做</div></div><button class="btn" type="button">看改了什么</button><button class="btn pri" type="button">升级…</button></div>
</section>
<section class="card">
  <div class="cardh"><h2 class="h2" style="flex:1">诊断</h2></div>
  <div style="padding:12px 16px;display:flex;flex-direction:column;gap:8px">
    <div style="display:flex;gap:10px"><span style="flex:1">报警推送</span><span class="mut">11-14 测试通过</span><button class="btn sm" type="button">发测试报警</button></div>
    <div style="display:flex;gap:10px"><span style="flex:1">磁盘</span><span class="mut">71% · 录像保留 30 天</span></div>
    <div style="display:flex;gap:10px"><span style="flex:1">诊断包</span><span class="mut">给售后用</span><button class="btn sm" type="button">打包下载</button></div>
  </div>
</section>
<section class="card" style="grid-column:1 / -1">
  <div class="cardh"><h2 class="h2" style="flex:1">系统</h2></div>
  <div style="padding:12px 16px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px">
    <div class="field"><label class="lbl">站点名字</label><input value="estate-1"></div>
    <div class="field"><label class="lbl">时区</label><select><option>Asia/Kuala_Lumpur</option></select></div>
    <div class="field"><label class="lbl">界面语言</label><select><option>中文</option><option>English</option></select></div>
    <div class="field"><label class="lbl">外观</label><select><option>值班深色、设置浅色</option></select></div>
  </div>
</section>
</div>
'''
page("S-system.dc.html","现场设置 高级","system",system,{"home":B})
print("ok")

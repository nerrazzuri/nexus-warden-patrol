from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
def layer(name,count,status="",sign="",on=False):
    st=f'background:#E3EEF9;box-shadow:inset 0 0 0 2px #1F6FC0;' if on else ''
    return f'''<button type="button" role="radio" aria-checked="{'true' if on else 'false'}" style="{st}display:grid;grid-template-columns:16px minmax(0,1fr) auto;gap:2px 10px;align-items:center;width:100%;text-align:left;padding:10px 16px;border:0;border-bottom:1px solid #E3E5E8;background-color:{'#E3EEF9' if on else '#fff'};font:14px/20px Barlow,'Noto Sans SC',sans-serif;color:#16191D;cursor:pointer">
      <span>{sign}</span><b style="font-weight:{700 if on else 600}">{name}</b><span class="mut">{count}</span>
      {f'<span></span><span style="grid-column:2/4;font-size:12.5px;color:#0E3F70">{status}</span>' if status else ''}</button>'''
mapsvg='''<svg viewBox="0 0 760 640" preserveAspectRatio="xMidYMid meet" style="position:absolute;inset:0;width:100%;height:100%" role="img" aria-label="第 4 版地图：禁行区图层，水池禁行区被缩小，等你确认">
  <path d="M60 60 H700 V260 H520 V600 H240 V260 H60 Z" fill="#fff" stroke="#6B7178" stroke-width="2.5"/>
  <rect x="270" y="300" width="220" height="190" fill="#F2F3F1" stroke="#9AA0A6" stroke-dasharray="6 4"/><text x="380" y="400" fill="#5A6068" font-size="14" text-anchor="middle">2 号楼</text>
  <g fill="none" stroke="#B4B8BE" stroke-width="1.2"><rect x="72" y="72" width="160" height="130"/><rect x="246" y="72" width="230" height="130"/><rect x="490" y="72" width="198" height="176"/><rect x="250" y="510" width="260" height="78"/></g>
  <g fill="#9AA0A6" font-size="12" text-anchor="middle"><text x="152" y="140">北门</text><text x="361" y="140">北区通道</text><text x="589" y="120">停车场</text><text x="380" y="555">南墙</text></g>
  <!-- 水池：原范围虚线，新范围实线 -->
  <defs><pattern id="hz" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="3" height="8" fill="#2A2F35" fill-opacity=".35"/></pattern></defs><rect x="540" y="280" width="140" height="110" fill="none" stroke="#2A2F35" stroke-width="2" stroke-dasharray="7 5"/>
  <rect x="560" y="296" width="96" height="78" fill="url(#hz)" stroke="#2A2F35" stroke-width="3"/>
  <g fill="#fff" stroke="#1F6FC0" stroke-width="2.5"><rect x="554" y="290" width="12" height="12"/><rect x="650" y="290" width="12" height="12"/><rect x="554" y="368" width="12" height="12"/><rect x="650" y="368" width="12" height="12"/></g>
  <text x="608" y="340" fill="#16191D" font-size="13" font-weight="700" text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="4">水池</text>
  <text x="610" y="408" fill="#2A2F35" font-size="11.5" text-anchor="middle">虚线 = 原范围，确认前仍避开</text>
  <rect x="96" y="226" width="110" height="22" fill="none" stroke="#2A2F35" stroke-width="1.5" stroke-dasharray="10 3 2 3"/><text x="151" y="242" fill="#2A2F35" font-size="11.5" text-anchor="middle">限速 0.5</text>
  <path d="M240 260 L240 300" stroke="#16191D" stroke-width="5"/><text x="232" y="290" fill="#16191D" font-size="11.5" text-anchor="end">虚拟墙</text>
  <rect x="300" y="226" width="64" height="26" fill="none" stroke="#6B7178" stroke-width="1.5" stroke-dasharray="3 3"/><text x="332" y="244" fill="#454A51" font-size="11" text-anchor="middle">忽略区</text>
</svg>'''
body=f'''
{phead("布置","地图第 4 版 · 在用。<b>禁行区有 1 处改动等你确认。</b>",'<button class="btn" type="button">历史版本…</button><button class="btn" type="button" disabled title="没有没保存的改动" style="border-style:dashed;color:#6B7178">保存</button>',DISC)}
<div style="flex:1;min-height:0;display:grid;grid-template-columns:256px minmax(0,1fr) 340px">
  <aside aria-label="图层" style="background:#fff;border-right:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0;overflow:auto">
    <div role="radiogroup" aria-label="正在改哪一层">
      {layer("防区","7","","")}
      {layer("禁行区和限速","4","1 处缩小了，等你确认",DISC,True)}
      {layer("巡逻路线","2","","")}
      {layer("布防时巡逻路线","1","","")}
      {layer("路网","41 点 · 1.2 公里","","")}
      {layer("待命点和充电桩","3","第 3 版带过来 2 个，还没留下",DISC)}
      {layer("固定摄像头","6","","")}
      {layer("报警设备","4","门磁、报警按钮","")}
    </div>
    <div style="padding:14px 16px;display:flex;flex-direction:column;gap:6px">
      <span class="lbl">其余图层淡着显示</span>
      <label style="display:flex;gap:8px;align-items:center;min-height:28px"><input type="checkbox" checked>防区</label>
      <label style="display:flex;gap:8px;align-items:center;min-height:28px"><input type="checkbox" checked>摄像头</label>
      <label style="display:flex;gap:8px;align-items:center;min-height:28px"><input type="checkbox">路网</label>
    </div>
  </aside>
  <figure style="margin:0;position:relative;min-width:0;background-color:#ECEEEB;background-image:linear-gradient(#E3E5E2 1px,transparent 1px),linear-gradient(90deg,#E3E5E2 1px,transparent 1px);background-size:24px 24px">
    <div style="position:absolute;left:16px;top:16px;right:16px;display:flex;gap:8px;z-index:1;align-items:center">
      {seg(["选择","画禁行区","画限速区","画虚拟墙","画忽略区"],"选择","工具")}
      <button class="btn" type="button">撤销</button>
    </div>
    {mapsvg}
    <figcaption class="mut" style="position:absolute;left:16px;bottom:14px;background:#fff;border:1px solid #D5D8DC;padding:6px 10px">拖角上的点改形状 · 1 格 = 5 米 · 每次保存留一个版本，可回退；新增、扩大保存即生效，删除、缩小要你确认</figcaption>
  </figure>
  <aside aria-label="选中的区域" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;min-height:0">
    <div style="padding:16px 20px;border-bottom:1px solid #D5D8DC;background:#EEF4FB">
      <div style="display:flex;gap:8px;align-items:center">{DISC}<b>等你确认</b></div>
      <p style="margin:6px 0 10px">你把「水池」缩小了。确认前机器人继续避开原来的范围（虚线）。</p>
      <p class="mut" style="margin:0 0 10px;font-size:13px">确认前再看一遍：水池、楼梯、陡坡、落差都还在禁行区里。</p>
      <button class="btn pri" type="button">输入密码确认…</button>
    </div>
    <div style="padding:16px 20px;display:flex;flex-direction:column;gap:14px;flex:1">
      <h2 class="h2" style="font-size:17px">水池</h2>
      <div class="field"><label class="lbl" for="nm">名字</label><input id="nm" style="{INP}" value="水池"></div>
      <div class="field"><span class="lbl">种类</span>{seg(["禁行","限速","虚拟墙","忽略区"],"禁行","种类")}</div>
      <label style="display:flex;gap:10px;align-items:flex-start"><input type="checkbox" checked style="width:18px;height:18px;margin-top:1px"><span>硬禁区<span class="mut" style="display:block;font-size:13px">水体、落差：遥控也进不去</span></span></label>
      <label style="display:flex;gap:10px;align-items:flex-start"><input type="checkbox" style="width:18px;height:18px;margin-top:1px"><span>临时<span class="mut" style="display:block;font-size:13px">到期站点自动删除</span></span></label>
      <div class="mut" style="font-size:13px">20 × 16 米 · 第 4 版地图 · demo 10:12 改</div>
      <button class="btn danger" type="button" style="margin-top:auto;align-self:flex-start">删除这个区域…</button>
    </div>
  </aside>
</div>
'''
page("S-layout.dc.html","现场设置 现场布置","layout",body,{"home":B},full=True)

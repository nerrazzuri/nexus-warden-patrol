from shell import page
from common import *
B='<span class="chip" style="height:20px;background:#1F6FC0;color:#fff">6</span>'
def sec(name,when,on=False):
    st='background:#E3EEF9;box-shadow:inset 3px 0 0 #1F6FC0;' if on else ''
    return f'<button type="button" role="tab" aria-selected="{"true" if on else "false"}" style="{st}display:block;width:100%;text-align:left;border:0;border-bottom:1px solid #E3E5E8;background-color:{"#E3EEF9" if on else "#fff"};padding:12px 16px;font:14px/20px Barlow,\'Noto Sans SC\',sans-serif;color:#16191D;cursor:pointer"><b>{name}</b><span class="mut" style="display:block;font-size:12.5px">{when}</span></button>'
body=f'''
{phead("维护","地图、定位、诊断、软件升级。安装和售后用，平时不用来这里。")}
<div style="flex:1;min-height:0;display:grid;grid-template-columns:240px minmax(0,1fr)">
  <div role="tablist" aria-orientation="vertical" aria-label="高级" style="background:#fff;border-right:1px solid #D5D8DC;overflow:auto">
    {sec("地图","家具大量移动，或机器人经常迷路")}
    {sec("定位","机器人说不知道自己在哪")}
    {sec("诊断","出现异常，或工程师要日志")}
    {sec("软件升级","公司发了新版本，或升级后要回退",True)}
    {sec("站点","主机状态、备份、遥控速度档")}
  </div>
  <div style="min-width:0;overflow:auto;background:#fff;display:flex;flex-direction:column">
    <section aria-label="现在的版本" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="padding:12px 20px"><h2 class="h2" style="font-size:17px">现在的版本</h2></div>
      <table style="width:100%;border-collapse:collapse"><thead><tr><th>装在哪</th><th>版本</th><th>状态</th><th style="text-align:right">操作</th></tr></thead><tbody>
        <tr><td><b>站点</b></td><td>build 20 · 11-10</td><td class="mut">—</td><td></td></tr>
        <tr><td><b>A</b></td><td>build 20</td><td><span style="display:inline-flex;gap:6px;align-items:center"><span class="sq"></span>和站点一致</span></td><td style="text-align:right"><button class="btn sm" type="button">回退到上一版本…</button></td></tr>
        <tr><td><b>B</b></td><td>build 19 → <b>20 已下载</b></td><td>排好了：充电且空闲时切换</td><td style="text-align:right;white-space:nowrap"><button class="btn sm" type="button">立即切换…</button></td></tr>
      </tbody></table>
    </section>
    <section aria-label="站点上的升级包" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:center;gap:12px;padding:12px 20px"><h2 class="h2" style="font-size:17px;flex:1">站点上的升级包</h2><button class="btn sm" type="button">上传升级包…</button></div>
      <p class="mut" style="margin:0;padding:0 20px 10px;font-size:13px">用公司提供的升级包（.tar.gz）。签名校验不通过的包会被拒绝。在线下载要站点能连上互联网（这个站点还没设置）。</p>
      <div style="display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center">{rule()}
        <div style="padding:12px 20px"><b>robot-build-20.tar.gz</b><div class="mut" style="font-size:13px">11-10 上传 · 签名通过 · 312 MB</div></div>
        <span class="mut" style="padding-right:20px">A 已装 · B 已下载</span>{rule()}
        <div style="padding:12px 20px"><b>robot-build-19.tar.gz</b><div class="mut" style="font-size:13px">10-28 上传 · 签名通过 · 回退用</div></div><span></span>
      </div>
    </section>
    <section aria-label="登录着的 App" style="background:#fff;border-bottom:1px solid #D5D8DC">
      <div style="display:flex;align-items:baseline;gap:12px;padding:12px 20px"><h2 class="h2" style="font-size:17px">登录着的 App</h2><span class="mut" style="font-size:13px">各 App 登录时上报；旧版 App 不上报</span></div>
      <table style="width:100%;border-collapse:collapse"><thead><tr><th>App</th><th>版本</th><th>登录过</th><th>状态</th></tr></thead><tbody>
        <tr><td>网页值班台</td><td>build 20</td><td>41 次</td><td class="mut">正常</td></tr>
        <tr><td>手机 App</td><td>build 20</td><td>17 次</td><td class="mut">正常</td></tr>
        <tr><td>手机 App</td><td>build 15</td><td>2 次</td><td><span style="display:inline-flex;gap:6px;align-items:center"><span class="tri"></span>版本过旧，不兼容此站点</span></td></tr>
      </tbody></table>
    </section>
  </div>
</div>
'''
page("S-system.dc.html","现场设置 高级","system",body,{"home":B},full=True)

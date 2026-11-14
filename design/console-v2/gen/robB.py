from shell import page
from common import *
B='<span class="chip warn" style="height:20px">2</span>'
PAD='display:inline-flex;align-items:center;justify-content:center;padding:0;border:1px solid #6B7178;background:#fff;color:#16191D;border-radius:2px;cursor:pointer'
def tag(x,y,title,val,sel=False,warn=False,w=170):
    bg='#1F6FC0' if sel else '#fff'; fg='#fff' if sel else '#16191D'; bd='#1F6FC0' if sel else ('#D99A00' if warn else '#6B7178')
    sub='#DCEBFA' if sel else ('#7A5200' if warn else '#565B62')
    return f'<g><rect x="{x}" y="{y}" width="{w}" height="46" fill="{bg}" stroke="{bd}" stroke-width="{2 if sel or warn else 1}"/><text x="{x+12}" y="{y+19}" font-size="14" font-weight="700" fill="{fg}">{title}</text><text x="{x+12}" y="{y+37}" font-size="12.5" fill="{sub}">{val}</text></g>'
def lead(x1,y1,x2,y2,sel=False):
    c='#1F6FC0' if sel else '#8A9097'
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{c}" stroke-width="{2 if sel else 1.2}" fill="none"/><circle cx="{x2}" cy="{y2}" r="4" fill="{c}"/>'
robot='''
  <!-- 机身侧视 -->
  <g fill="#E6E8E5" stroke="#2A2F35" stroke-width="2">
    <rect x="300" y="250" width="330" height="96" rx="6"/>
    <rect x="610" y="226" width="78" height="62" rx="4"/>
    <path d="M330 346 l-22 70 l18 64" fill="none" stroke-width="10" stroke="#2A2F35"/>
    <path d="M400 346 l20 66 l-16 68" fill="none" stroke-width="10" stroke="#2A2F35"/>
    <path d="M540 346 l-22 70 l18 64" fill="none" stroke-width="10" stroke="#2A2F35"/>
    <path d="M610 346 l20 66 l-16 68" fill="none" stroke-width="10" stroke="#2A2F35"/>
    <rect x="440" y="226" width="40" height="24" rx="3"/>
    <rect x="352" y="232" width="56" height="18" rx="2"/>
  </g>
  <g fill="#2A2F35"><rect x="300" y="478" width="40" height="6"/><rect x="390" y="478" width="40" height="6"/><rect x="510" y="478" width="40" height="6"/><rect x="600" y="478" width="40" height="6"/></g>
  <circle cx="676" cy="257" r="13" fill="#2A2F35"/><circle cx="676" cy="257" r="6" fill="#5AA2E6"/>
  <rect x="690" y="236" width="6" height="40" fill="#2A2F35"/>
  <rect x="452" y="214" width="16" height="12" fill="#F2B01E" stroke="#2A2F35" stroke-width="1.5"/>
  <rect x="330" y="276" width="120" height="44" fill="#fff" stroke="#2A2F35" stroke-width="1.5"/>
  <text x="342" y="296" font-size="13" font-weight="700" fill="#16191D">A · C40221</text><text x="342" y="313" font-size="11" fill="#565B62">铭牌</text>
  <g fill="#2A2F35"><rect x="365" y="236" width="4" height="10"/><rect x="373" y="236" width="4" height="10"/><rect x="381" y="236" width="4" height="10"/><rect x="389" y="236" width="4" height="10"/></g>
  <path d="M520 250 v-34" stroke="#2A2F35" stroke-width="2.5"/><circle cx="520" cy="214" r="4" fill="#2A2F35"/>
  <rect x="490" y="290" width="110" height="34" fill="#D3D6D2" stroke="#2A2F35" stroke-width="1.5"/><text x="545" y="312" font-size="11" fill="#2A2F35" text-anchor="middle">电池</text>
  <path d="M600 288 h12" stroke="#2A2F35" stroke-width="2"/>
'''
svg=f'''<svg viewBox="-30 0 1010 560" style="width:100%;height:100%" role="img" aria-label="A 的器件图：点部件看状态和操作">
  <defs><pattern id="g" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#E3E5E8"/></pattern></defs>
  
  {robot}
  {lead(676,257,780,150,True)}{tag(780,108,"云台和摄像头","水平 0° · 俯仰 −10°",True,w=180)}
  {lead(696,262,800,262)}{tag(800,240,"雨刷","干净",w=150)}
  {lead(460,216,470,100)}{tag(400,56,"警灯","关",w=140)}
  {lead(380,236,250,150)}{tag(80,108,"喇叭","空闲 · 常用话 3 句",w=170)}
  {lead(520,212,620,86)}{tag(600,40,"天线 · 网络","Wi-Fi 好 · 延迟 38 ms",w=180)}
  {lead(545,324,800,380)}{tag(800,358,"电池","62% · 约 2 小时 40 分",w=170)}
  {lead(330,300,170,300)}{tag(0,278,"铭牌","名字 · 激活码 · 派单 · 解绑",w=170)}
  {lead(470,330,250,430)}{tag(80,410,"主机","存储 64% · v1.20 · 维护",w=170)}
  {lead(420,412,600,470)}{tag(600,450,"腿 · 姿态","站着",w=150)}
</svg>'''
body=f'''
<div style="flex:none;display:flex;align-items:stretch;background:#fff;border-bottom:1px solid #D5D8DC;padding:0 24px;gap:4px" role="tablist" aria-label="机器人">
  <h1 class="h2" style="align-self:center;font-size:18px;margin-right:16px">机器人</h1>
  <button type="button" role="tab" aria-selected="true" style="display:flex;align-items:center;gap:8px;height:52px;padding:0 18px;border:0;background:transparent;box-shadow:inset 0 -3px 0 #1F6FC0;font:700 15px Barlow,'Noto Sans SC',sans-serif;color:#0E3F70"><span class="sq"></span>A · 巡逻中 · 62%</button>
  <button type="button" role="tab" aria-selected="false" style="display:flex;align-items:center;gap:8px;height:52px;padding:0 18px;border:0;background:transparent;font:600 15px Barlow,'Noto Sans SC',sans-serif;color:#2A2F35"><span class="tri" style="border-left-width:6px;border-right-width:6px;border-bottom-width:11px"></span>B · 充电中 · 18%</button>
  <span style="flex:1"></span>
  <span style="align-self:center;display:flex;gap:8px;align-items:center;padding:6px 12px;background:#FCF1D6;color:#4A3600"><span class="tri"></span>C40388 请求加入 · 核对码 482 913 <a href="#">批准…</a></span>
  <button class="btn sm" type="button" style="align-self:center;margin-left:12px">添加</button>
</div>
<div style="flex:none;display:flex;align-items:center;gap:16px;padding:12px 24px;background:#F5F6F4;border-bottom:1px solid #E3E5E8">
  <b style="font-size:16px">在跑 guard-1 第 3 圈 · 还要约 40 分</b><span class="mut">22:00 按日程开始 · 派单 自动 · 上次联系 2 秒前</span>
  <span style="flex:1"></span>
  <button class="btn sm" type="button">停下当前任务</button><button class="btn sm" type="button">停下并回家</button>
  <select aria-label="派一次巡逻" style="height:32px;border:1px solid #6B7178;border-radius:2px;padding:0 8px;font:inherit"><option>派一次：停车场一圈</option></select><button class="btn sm" type="button">排上</button>
</div>
<div style="flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 380px">
  <figure style="margin:0;position:relative;min-width:0;background-color:#FAFBFA;background-image:linear-gradient(#E6E8E5 1px,transparent 1px),linear-gradient(90deg,#E6E8E5 1px,transparent 1px);background-size:20px 20px">
    {svg}
    <figcaption class="mut" style="position:absolute;left:24px;bottom:16px">点一个部件，右边就是它的状态和操作。B 换到这张图时，天线会标黄「换网待批」。</figcaption>
  </figure>
  <aside aria-label="云台和摄像头" style="background:#fff;border-left:1px solid #D5D8DC;display:flex;flex-direction:column;padding:20px;gap:16px">
    <div style="display:flex;align-items:baseline"><h2 class="h2" style="flex:1;font-size:18px">云台和摄像头</h2><span class="chip ok">正常</span></div>
    <div style="position:relative;aspect-ratio:16/9;{NOISE};border:1px solid #2E333A;color:#ECEDEA">
      <div style="position:absolute;left:0;right:0;top:0;padding:6px 10px;background:rgba(0,0,0,.6);display:flex;gap:8px"><span>前摄像头</span><span style="flex:1"></span><span style="color:#FF6166;font-weight:700">● 实时</span></div>
    </div>
    <div style="display:flex;gap:20px;align-items:center">
      {dpad(PAD)}
      <dl style="margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 12px"><dt class="mut">水平</dt><dd style="margin:0;font-weight:700">0°</dd><dt class="mut">俯仰</dt><dd style="margin:0;font-weight:700">−10°</dd></dl>
    </div>
    <p class="mut" style="margin:0">每点一下转 15°。中间的圆是回正前方。</p>
    <div style="border-top:1px solid #E3E5E8;padding-top:14px">
      <h3 class="h2" style="margin-bottom:8px">别的部件</h3>
      <div style="display:flex;flex-wrap:wrap;gap:6px"><button class="btn sm" type="button">喇叭 · 喊话</button><button class="btn sm" type="button">警灯</button><button class="btn sm" type="button">雨刷</button><button class="btn sm" type="button">腿 · 姿态</button><button class="btn sm" type="button">电池</button><button class="btn sm" type="button">天线 · 网络</button><button class="btn sm" type="button">主机 · 维护</button><button class="btn sm" type="button">铭牌 · 管理</button></div>
    </div>
    <a href="#" style="margin-top:auto">今天的经过和 30 天报警 4 条</a>
  </aside>
</div>
'''
page("R-B.dc.html","机器人 方案B","robots",body,{"home":B},full=True)

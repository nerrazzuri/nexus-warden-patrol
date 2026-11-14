# 管理端公用壳：浅色，顶栏同保安端结构，左侧二级导航
HEAD='''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&display=swap">
<style>
body{{margin:0}}
a{{color:#1A5FA6}}a:hover{{color:#0E3F70}}
.btn{{height:40px;padding:0 16px;border:1px solid #6B7178;border-radius:2px;background:#fff;color:#16191D;font:600 14px Barlow,"Noto Sans SC","Microsoft YaHei UI",sans-serif;display:inline-flex;align-items:center;gap:8px;cursor:pointer;white-space:nowrap;text-decoration:none}}
.btn.sm{{height:32px;padding:0 12px;font-size:13px}}
.btn.pri{{background:#1F6FC0;border-color:#1F6FC0;color:#fff;font-weight:700}}
.btn.danger{{border-color:#C4262B;color:#B0202A}}
.btn.stop{{background:#D42F33;border-color:#D42F33;color:#fff;font-weight:700}}
.seg{{display:inline-flex;border:1px solid #C9CDD2}}
.seg .btn{{border:0;background:transparent;border-radius:0}}
.seg .btn+.btn{{border-left:1px solid #C9CDD2}}
.seg .btn.on{{background:#1F6FC0;color:#fff}}
.lbl{{font-size:12px;font-weight:600;letter-spacing:.06em;color:#5A6068}}
.mut{{color:#565B62}}
.ring{{display:inline-block;flex:none;width:12px;height:12px;border:3px solid #C4262B;border-radius:50%;box-sizing:border-box}}
.tri{{display:inline-block;flex:none;width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-bottom:12px solid #D99A00}}
.sq{{display:inline-block;flex:none;width:9px;height:9px;background:#1E8A47}}
.h1{{margin:0;font-size:24px;line-height:30px;font-weight:700}}
.h2{{margin:0;font-size:16px;line-height:22px;font-weight:600}}
.card{{background:#fff;border:1px solid #D5D8DC}}
.cardh{{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid #E3E5E8}}
th{{text-align:left;font-size:12px;font-weight:600;letter-spacing:.06em;color:#5A6068;padding:10px 12px;border-bottom:1px solid #D5D8DC;background:#F8F9F8}}
td{{padding:10px 12px;border-bottom:1px solid #E3E5E8;vertical-align:middle}}
.chip{{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 8px;font-size:12px;font-weight:700}}
.ok{{background:#E4F3E9;color:#17703A}} .warn{{background:#FCF1D6;color:#7A5200}} .bad{{background:#FBE5E5;color:#A41E24}} .gray{{background:#ECEEF0;color:#454A51}}
.field{{display:flex;flex-direction:column;gap:4px}}
.field input,.field select{{height:40px;border:1px solid #6B7178;border-radius:2px;padding:0 10px;font:inherit;background:#fff;color:#16191D}}
.snav a{{display:flex;align-items:center;gap:8px;min-height:36px;margin:0 8px;padding:0 10px;color:#A9AEB4;text-decoration:none;font-weight:600;border-radius:2px}}
.snav a[aria-current]{{background:#1F6FC0;color:#fff}} .snav .g{{color:#A9AEB4}}
.snav .g{{padding:14px 16px 4px}}
.new{{display:inline-block;padding:0 6px;border:1px solid #1F6FC0;color:#1A5FA6;font-size:11px;font-weight:700;line-height:16px}}
</style>
</helmet>
<div style="width:1536px;height:960px;box-sizing:border-box;background:#F2F3F1;color:#16191D;font-family:Barlow,'Noto Sans SC','Microsoft YaHei UI',sans-serif;font-size:14px;line-height:20px;font-variant-numeric:tabular-nums;display:flex;flex-direction:column">
  <header style="height:60px;flex:none;display:flex;align-items:center;gap:16px;padding:0 16px;border-bottom:1px solid #2E333A;background:#0A0C0E;color:#ECEDEA">
    <div style="display:flex;flex-direction:column;line-height:14px"><b style="font-size:13px;letter-spacing:.12em">NEXUS</b><span style="font-size:11px;letter-spacing:.12em;color:#B4B8BE">WARDEN</span></div>
    <span style="color:#B4B8BE">estate-1</span>
    <nav aria-label="主导航" style="display:flex;margin-left:8px">
      <a href="#" style="height:60px;display:flex;align-items:center;padding:0 14px;color:#B4B8BE;text-decoration:none;font-weight:600">值班</a>
      <a href="#" style="height:60px;display:flex;align-items:center;padding:0 14px;color:#B4B8BE;text-decoration:none;font-weight:600">记录与录像</a>
      <a href="#" aria-current="page" style="height:60px;display:flex;align-items:center;padding:0 14px;color:#ECEDEA;text-decoration:none;font-weight:700;box-shadow:inset 0 -3px 0 #1F6FC0">现场设置</a>
    </nav>
    <div style="flex:1"></div>
    <span style="display:inline-flex;align-items:center;gap:8px;height:32px;padding:0 12px;background:#20242A;color:#ECEDEA;font-weight:600">撤防 · 19:00 布防</span>
    <span style="display:inline-flex;align-items:center;gap:8px;height:32px;padding:0 12px;background:#20242A;font-weight:600">机器人 2/2 在线</span>
    <a href="#" style="display:inline-flex;align-items:center;gap:8px;height:32px;padding:0 12px;background:#20242A;color:#B4B8BE;font-weight:600;text-decoration:none">未处理 0</a>
    <span style="font-size:16px;font-weight:600">10:20</span>
    <span style="color:#B4B8BE">{who}</span>
    <button class="btn stop" type="button"><span style="width:12px;height:12px;border:2px solid #fff;border-radius:50%;box-sizing:border-box"></span>全部急停</button>
  </header>
  <div style="flex:1;min-height:0;display:grid;grid-template-columns:232px minmax(0,1fr)">
    <nav class="snav" aria-label="现场设置" style="background:#15181B;border-right:1px solid #15181B;padding:8px 0;overflow:auto">
{nav}
    </nav>
    <main style="{mainstyle}">
{body}
    </main>
  </div>
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":1536,"height":960}}}}'>
class Component extends DCLogic {{
  renderVals() {{ return {{}}; }}
}}
</script>
</body>
</html>
'''
NAV=[("日常",[("home","概况",""),("robots","机器人",""),("users","人员","")]),
     ("现场",[("layout","布置",""),("arming","布防与巡逻",""),("access","授权","")]),
     ("记录",[("reports","报告","")]),
     ("高级",[("system","维护","")])]
ROLE={"who":"demo · 管理员","allow":None}
def nav(cur, badges={}):
    out=[]
    for g,items in NAV:
        items=[it for it in items if ROLE["allow"] is None or it[0] in ROLE["allow"]]
        if not items: continue
        out.append(f'      <div class="g lbl">{g}</div>')
        for k,label,_ in items:
            b=badges.get(k,"")
            cur_attr=' aria-current="page"' if k==cur else ''
            out.append(f'      <a href="#"{cur_attr}><span style="flex:1">{label}</span>{b}</a>')
    return "\n".join(out)
def page(fn,title,cur,body,badges={},full=False):
    ms='min-width:0;min-height:0;overflow:hidden;display:flex;flex-direction:column' if full else 'min-width:0;min-height:0;overflow:auto;padding:24px 32px;display:flex;flex-direction:column;gap:20px'
    import os
    d='/tmp/claude-1000/-home-liang-Projects-D1-Max/ecced633-c546-490e-ade6-e46e90a431ed/scratchpad/dcanvas/project/'
    open(os.path.join(d,fn),'w').write(HEAD.format(title=title,nav=nav(cur,badges),body=body,mainstyle=ms,who=ROLE["who"]))

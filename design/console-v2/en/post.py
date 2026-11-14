import re,sys
P='dcanvas/project/'
def fix(name,fn):
    p=P+name+'-en.dc.html'
    try: s=open(p).read()
    except FileNotFoundError: return
    open(p,'w').write(fn(s))
def layout(s): return s.replace('aria-selected="false">Virtual wall</button>','aria-selected="false">Wall</button>').replace('aria-selected="false">Speed limit</button>','aria-selected="false">Speed</button>')
def users(s): return s.replace('>Normal<','>Active<').replace('guard-1','guard&#8209;1')
def access(s):
    days=['Mo','Tu','We','Th','Fr','Sa','Su']; i=[0]
    def r(m):
        v='>'+days[i[0]%7]+'<'; i[0]+=1; return v
    s=re.sub(r'>[MTWFS]<',r,s)
    s=s.replace('placeholder="Leave blank for no expiry"','placeholder="No expiry"')
    s=s.replace('class="lbl" style="padding:8px 0 8px 20px">Users<','class="lbl" style="padding:8px 0 8px 20px">Who<').replace('class="lbl">Users<','class="lbl">Who<')
    return s
def robot(s): return s.replace('placeholder="Type a message; press Enter to speak"','placeholder="Type a message"')
def mrobot(s): return s.replace('guard-1','guard&#8209;1')
fix('S-layout',layout); fix('S-users',users); fix('S-access',access); fix('G-robot',robot); fix('M-robot',mrobot)
def malarm(s): return s.replace('on duty:<b>gina</b>(online),<b style="color:#FF8A8D">not yet assigned</b>。','on duty: <b>gina</b> (online), <b style="color:#FF8A8D">not yet assigned</b>.')
fix('M-alarm',malarm)

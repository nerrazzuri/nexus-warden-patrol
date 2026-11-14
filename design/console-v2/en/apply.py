import re,json,sys
D=json.load(open('en/dict.json'))
CJK=re.compile(r'[一-鿿]')
F=sys.argv[1:]
miss={}
for f in F:
    s=open(f'dcanvas/project/{f}.dc.html').read()
    parts=re.split(r'(<style.*?</style>|<!--.*?-->)',s,flags=re.S); out=[]
    for p in parts:
        if p.startswith('<style') or p.startswith('<!--'): out.append(p); continue
        def tx(m):
            raw=m.group(1); k=raw.strip()
            if not CJK.search(k): return '>'+raw+'<'
            if k in D: return '>'+raw.replace(k,D[k])+'<'
            miss.setdefault(k,f); return '>'+raw+'<'
        p=re.sub(r'>([^<>]+)<',tx,p)
        def at(m):
            k=m.group(2)
            if CJK.search(k):
                if k in D: k=D[k]
                else: miss.setdefault(k,f)
            return m.group(1)+k.replace('"','&quot;')+m.group(3)
        p=re.sub(r'((?:title|aria-label|placeholder|value|alt)=")([^"]*)(")',at,p)
        out.append(p)
    s=''.join(out).replace('lang="zh-CN"','lang="en"')
    open(f'dcanvas/project/{f}-en.dc.html','w').write(s)
json.dump(miss,open('en/miss.json','w'),ensure_ascii=False,indent=0)
print('missing',len(miss))
for k,f in miss.items(): print(f,'|',k)

import re, json, os, sys
P = '/tmp/claude-1000/-home-liang-Projects-D1-Max/ecced633-c546-490e-ade6-e46e90a431ed/scratchpad/dcanvas/project/'
D = json.load(open('/home/liang/Projects/D1_Max/wt-redesign/design/console-v2/en/dict.json'))
A = json.load(open('app_dict.json')) if os.path.exists('app_dict.json') else {}
D.update(A)
CJK = re.compile(r'[一-鿿]')
names = [b['name'] for f in ('now_boards.json', 'site_boards.json', 'parity_boards.json') for b in json.load(open(f))]
miss = {}
for n in names:
    s = open(P + n + '.dc.html').read()
    svgs = []
    def svgtx(m):
        k = m.group(1).strip()
        if CJK.search(k):
            if k in D: return '>' + m.group(1).replace(k, D[k]) + '<'
            miss.setdefault(k, n)
        return m.group(0)
    def keep(m):
        v = re.sub(r'>([^<>]+)<', svgtx, m.group(0))
        v = re.sub(r'aria-label="([^"]*)"', lambda a: 'aria-label="' + D.get(a.group(1), a.group(1)) + '"', v)
        svgs.append(v); return f'<i data-svg="{len(svgs)-1}"></i>'
    s = re.sub(r'<svg.*?</svg>', keep, s, flags=re.S)
    parts = re.split(r'(<style.*?</style>|<!--.*?-->)', s, flags=re.S); out = []
    for p in parts:
        if p.startswith('<style') or p.startswith('<!--'): out.append(p); continue
        def tx(m):
            raw = m.group(1); k = raw.strip()
            if not CJK.search(k): return '>' + raw + '<'
            if k in D: return '>' + raw.replace(k, D[k]) + '<'
            miss.setdefault(k, n); return '>' + raw + '<'
        p = re.sub(r'>([^<>]+)<', tx, p)
        def at(m):
            k = m.group(2)
            if CJK.search(k):
                if k in D: k = D[k]
                else: miss.setdefault(k, n)
            return m.group(1) + k.replace('"', '&quot;') + m.group(3)
        p = re.sub(r'((?:title|aria-label|placeholder|value|alt)=")([^"]*)(")', at, p)
        out.append(p)
    s = ''.join(out).replace('lang="zh-CN"', 'lang="en"')
    s = re.sub(r'<i data-svg="(\d+)"></i>', lambda m: svgs[int(m.group(1))], s)
    if n == 'App-N-robot': s = s.replace('<button type="button">中文</button>', '<button type="button">Chinese</button>')
    open(P + n + '-en.dc.html', 'w').write(s)
json.dump(miss, open('miss.json', 'w'), ensure_ascii=False, indent=0)
print('missing', len(miss))

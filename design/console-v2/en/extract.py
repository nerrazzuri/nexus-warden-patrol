import re,json,sys,html
F=["V4-normal","V4-alarm","G-playback","G-multi","G-compact","G-records","S-home","S-layout","S-arming","S-access","R-A","R-A2","S-users","S-system","S-reports","S-log"]
CJK=re.compile(r'[　-〿一-鿿＀-￯]')
segs={}
for f in F:
    s=open(f'dcanvas/project/{f}.dc.html').read()
    s=re.sub(r'<style.*?</style>','',s,flags=re.S)
    # text nodes
    for t in re.findall(r'>([^<>]+)<',s):
        t=t.strip()
        if CJK.search(t): segs.setdefault(t,[]).append(f)
    for t in re.findall(r'(?:title|aria-label|placeholder|value|alt)="([^"]*)"',s):
        if CJK.search(t): segs.setdefault(t,[]).append(f)
    for t in re.findall(r'<text[^>]*>([^<]*)</text>',s):
        pass
json.dump({k:sorted(set(v)) for k,v in segs.items()},open('en/segs.json','w'),ensure_ascii=False,indent=0)
print(len(segs), sum(len(k) for k in segs))

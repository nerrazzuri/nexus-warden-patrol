// 把 .dc.html 拆成普通页面截图：node preview.js in.dc.html out.png W H
const fs=require('fs');const path=require('path');
const {chromium}=require('/tmp/claude-1000/-home-liang/ecced633-c546-490e-ade6-e46e90a431ed/scratchpad/pw/node_modules/playwright');
(async()=>{const [,,inp,out,W,H]=process.argv;const s=fs.readFileSync(inp,'utf8');
const helmet=s.match(/<helmet>([\s\S]*?)<\/helmet>/)[1];const body=s.split('</helmet>')[1].split('</x-dc>')[0];
const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">${helmet}</head><body>${body}</body></html>`;
const tmp=out.replace(/\.png$/,'.html');fs.writeFileSync(tmp,html);
const b=await chromium.launch({channel:'chrome'});const p=await b.newPage({viewport:{width:+W,height:+H}});
await p.goto('file://'+path.resolve(tmp));await p.waitForTimeout(1500);await p.screenshot({path:out});await b.close();})();

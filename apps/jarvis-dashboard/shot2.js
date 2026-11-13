const { chromium } = require('playwright');
const S=process.argv[2];
(async()=>{const b=await chromium.launch();
for (const [m,w,h,name] of [["real",1100,900,"desk"],["demo",1100,900,"demo"],["real",390,844,"phone"]]) {
 const p=await b.newPage({viewport:{width:w,height:h},deviceScaleFactor:name==="phone"?3:2});
 await p.goto(`file://${S}/page_${m}.html`);
 if(name==="desk"){await p.waitForTimeout(450);await p.screenshot({path:`${S}/mid.png`});}
 await p.waitForTimeout(3200);
 if(name==="desk"){await p.click('.mx-row summary');await p.waitForTimeout(400);}
 await p.screenshot({path:`${S}/${name}.png`,fullPage:true});await p.close();}
await b.close();})();

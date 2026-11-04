import puppeteer from "puppeteer-core"; import fs from "fs";
const OUT = process.env.OUT, UI = process.env.UI || "en", D = `${OUT}/fr_${UI}`; fs.rmSync(D, { recursive: true, force: true }); fs.mkdirSync(D);
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--autoplay-policy=no-user-gesture-required"] });
const p = await b.newPage(); await p.setViewport({ width: process.env.GLASSES ? 1200 : 1000, height: 600, deviceScaleFactor: 1.5 });
const w = s => new Promise(r => setTimeout(r, s * 1000));
await p.goto(`http://127.0.0.1:8790/?ui=${UI}#run=8e1456e529ca&view=coach&go=watch`, { waitUntil: "load" }); await w(1.5);
await p.addStyleTag({ content: ".coachv .exit, .coachv .wcap, .coachv .bar, .coachv .verifybtn, .coachv .hrow { display:none !important }" });
if (process.env.GLASSES) {  // 안경 화면(600x600)을 오른쪽 아래에 작게: 같은 짝 코드로 따라 하기 화면을 따라간다. 실제 기기가 아니라 시뮬레이터에서만 확인했다고 적는다
  await p.evaluate((ui) => {
    const box = document.createElement("div"); box.id = "glassinset";
    box.innerHTML = `<div class="gl">${ui === "en" ? "Glasses view (Meta Ray-Ban Display simulator)" : "안경 화면 (Meta Ray-Ban Display 시뮬레이터)"}</div><div class="gf"><iframe src="/glasses?run=8e1456e529ca&lang=${ui}&m=${ui}&s=${C.pair}"></iframe></div>`;
    document.querySelector(".coachv").appendChild(box);
  }, UI);
  await p.addStyleTag({ content: `.coachv { padding-right:440px !important; } #glassinset { position:fixed; right:18px; top:50%; transform:translateY(-50%); z-index:50; display:flex; flex-direction:column; align-items:flex-end; gap:6px; }
    #glassinset .gl { width:400px; text-align:center; font:600 16px/1.3 system-ui, sans-serif; color:#c7d0f0; background:rgba(11,16,21,.6); padding:4px 8px; border-radius:99px; }
    #glassinset .gf { width:400px; height:400px; border-radius:14px; overflow:hidden; border:2px solid #3a4580; background:#000; box-shadow:0 12px 30px rgba(0,0,0,.5); }
    #glassinset iframe { width:600px; height:600px; border:0; transform:scale(.6667); transform-origin:0 0; }` });
  await w(2);
}
const t0 = Date.now(), list = []; let n = 0, last = 0;
while (Date.now() - t0 < Number(process.env.SECS || 32) * 1000) {
  const t = Date.now(); await p.screenshot({ path: `${D}/${String(n).padStart(5, "0")}.jpg`, type: "jpeg", quality: 88 });
  list.push(t); n++; const i = await p.evaluate(() => S.idx); if (i !== last) { console.log("move ->", i + 1, ((t - t0) / 1000).toFixed(1)); last = i; }
}
let c = ""; for (let k = 0; k < n; k++) { c += `file '${String(k).padStart(5, "0")}.jpg'\nduration ${((k + 1 < n ? list[k + 1] : list[k] + 100) - list[k]) / 1000}\n`; }
fs.writeFileSync(`${D}/list.txt`, c); console.log("frames", n, "fps", (n / ((Date.now() - t0) / 1000)).toFixed(1));
await b.close();

import puppeteer from "puppeteer-core"; import fs from "fs";
const OUT = process.env.OUT, UI = process.env.UI || "en", D = `${OUT}/fr_${UI}`; fs.rmSync(D, { recursive: true, force: true }); fs.mkdirSync(D);
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--autoplay-policy=no-user-gesture-required"] });
const p = await b.newPage(); await p.setViewport({ width: 1000, height: 600, deviceScaleFactor: 1.5 });
const w = s => new Promise(r => setTimeout(r, s * 1000));
await p.goto(`http://127.0.0.1:8790/?ui=${UI}#run=8e1456e529ca&view=coach&go=watch`, { waitUntil: "load" }); await w(1.5);
await p.addStyleTag({ content: ".coachv .exit, .coachv .wcap, .coachv .bar, .coachv .verifybtn, .coachv .hrow { display:none !important }" });
const t0 = Date.now(), list = []; let n = 0, last = 0;
while (Date.now() - t0 < Number(process.env.SECS || 32) * 1000) {
  const t = Date.now(); await p.screenshot({ path: `${D}/${String(n).padStart(5, "0")}.jpg`, type: "jpeg", quality: 88 });
  list.push(t); n++; const i = await p.evaluate(() => S.idx); if (i !== last) { console.log("move ->", i + 1, ((t - t0) / 1000).toFixed(1)); last = i; }
}
let c = ""; for (let k = 0; k < n; k++) { c += `file '${String(k).padStart(5, "0")}.jpg'\nduration ${((k + 1 < n ? list[k + 1] : list[k] + 100) - list[k]) / 1000}\n`; }
fs.writeFileSync(`${D}/list.txt`, c); console.log("frames", n, "fps", (n / ((Date.now() - t0) / 1000)).toFixed(1));
await b.close();

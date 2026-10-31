// 끝 화면 '오늘 한 것 보내기' 확인: 공유 창에 넘기는 글·링크를 가로채 출력
import puppeteer from "puppeteer-core";
const [ui, out] = [process.argv[2] || "ko", process.argv[3]];
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
const p = await b.newPage(); await p.setViewport({ width: 1100, height: 800 });
await p.evaluateOnNewDocument(() => { navigator.share = d => { window.__shared = d; return Promise.resolve(); }; });
await p.goto(`http://127.0.0.1:8790/?ui=${ui}#run=8e1456e529ca&view=coach`, { waitUntil: "networkidle0" });
await new Promise(r => setTimeout(r, 1500));
const r = await p.evaluate(async () => {
  C.help = true; C.max = { 0: 1, 2: 2, 6: 2, 4: 3 }; S.idx = 11; coachEnd(true);
  const btn = [...document.querySelectorAll("#csum button")].find(x => /보내기|Share/.test(x.textContent));
  btn.click(); await new Promise(r => setTimeout(r, 300));
  return { buttons: [...document.querySelectorAll("#csum button")].map(x => x.textContent), shared: window.__shared };
});
console.log(JSON.stringify(r, null, 1));
if (out) await p.screenshot({ path: out });
await b.close();

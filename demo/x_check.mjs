// 한 언어 더 확인: 3번 화면 확인 상자 → '확인했어요' → 카드 글자 고르기 → 태블릿·안경에 두 줄
import puppeteer from "puppeteer-core";
const [run, out] = [process.argv[2], process.argv[3]];
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new" });
const p = await b.newPage(); await p.setViewport({ width: 1100, height: 900 });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8790/?ui=ko#run=${run}&view=use`, { waitUntil: "networkidle0" }); await wait(800);
const before = await p.evaluate(() => ({ rows: document.querySelectorAll(".xtab tbody tr").length, seg: [...document.querySelectorAll(".seg button")].map(x => x.textContent) }));
await p.evaluate(() => document.querySelector("#xbox").scrollIntoView()); if (out) await p.screenshot({ path: out + "_box.png" });
await p.evaluate(() => [...document.querySelectorAll("#xbox button")].find(x => /확인했어요/.test(x.textContent)).click()); await wait(800);
const seg = await p.evaluate(() => [...document.querySelectorAll(".seg button")].map(x => x.textContent));
await p.evaluate(() => setLang("x")); await p.goto(`http://127.0.0.1:8790/?ui=ko#run=${run}&view=tablet`, { waitUntil: "networkidle0" }); await wait(800);
const tab = await p.evaluate(() => document.querySelector(".tab .txt, .tab .say, .tab")?.innerText.slice(0, 200));
if (out) await p.screenshot({ path: out + "_tab.png" });
await p.goto(`http://127.0.0.1:8790/glasses?run=${run}&lang=x&m=ko`, { waitUntil: "networkidle0" }); await wait(1500);
const gl = await p.evaluate(() => document.querySelector(".say")?.innerText);
console.log(JSON.stringify({ before, seg, tab, gl }, null, 1));
await b.close();

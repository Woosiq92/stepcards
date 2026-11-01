// 11-01 검수 결함 다시 재현: 번역 확인 풀림·네트워크 실패·빠른 넘김·영어 단수·기록지 두 언어
import puppeteer from "puppeteer-core";
const run = process.argv[2], W = ms => new Promise(r => setTimeout(r, ms));
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
const p = await b.newPage(); const errs = []; p.on("pageerror", e => errs.push(e.message)); await p.setViewport({ width: 1100, height: 800 });
await p.setRequestInterception(true);
p.on("request", r => /\/(illustrate|coach|verify|translate|upload|agent)\b/.test(r.url()) && r.method() === "POST" ? r.abort() : r.continue());
const out = {};
// 1
await p.goto(`http://127.0.0.1:8790/?ui=ko#run=${run}&view=edit`, { waitUntil: "networkidle0" }); await W(800);
await p.evaluate(async () => { localStorage.setItem("lang", "x"); S.data.cards[0].ko = "밑단을 천천히 위로 접으세요."; await saveNow(); });
out.extraAfterEdit = await p.evaluate(() => S.data.extra);
await p.evaluate(() => go({ run: S.run, view: "use" })); await W(800);
out.segOn = await p.evaluate(() => [...document.querySelectorAll(".seg button")].map(x => x.textContent + (x.classList.contains("on") ? "*" : "")).join(" | "));
out.printFirst = await p.evaluate(() => document.querySelector(".pcard .txt").innerText);
// 2
await p.evaluate(() => go({ run: S.run, view: "edit" })); await W(800);
await p.evaluate(() => illustrateCard(0)); await W(800);
out.busyAfterFail = await p.evaluate(() => S.busy.size);
// 4
await p.evaluate(() => { setLang("both"); go({ run: S.run, view: "use" }); }); await W(800);
out.recordRow = await p.evaluate(() => document.querySelector(".record tbody tr td:nth-child(3)").innerText);
// 5·6
await p.goto(`http://127.0.0.1:8790/?ui=en#run=${run}&view=coach`, { waitUntil: "networkidle0" }); await W(1500);
out.sum = await p.evaluate(async () => {
  C.started = true; C.help = true; C.max = {}; S.idx = 0; C.shown = -1; coachCard(true);
  coachFlip(1); coachFlip(1);                 // 0, 1 빨리 넘김
  C.since = Date.now() - 5000; coachFlip(1);  // 2 는 5초 머묾
  coachEnd(true); return document.querySelector(".sumgrid")?.innerText.replace(/\n/g, " / ");
});
console.log(JSON.stringify({ ...out, errs }, null, 1)); await b.close();

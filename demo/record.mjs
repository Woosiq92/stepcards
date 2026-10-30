// 데모용 화면 녹화: 실제 앱을 자동으로 조작하며 장면별 webm을 남긴다
// 사용: node demo/record.mjs <장면> [실행 id]   장면 = making | edit | use | coach
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const [scene, runId] = process.argv.slice(2);
const BASE = "http://127.0.0.1:8790";
const OUT = new URL("./out/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const wait = ms => new Promise(r => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new",
  protocolTimeout: 0,  // 카드 만들기가 몇 분 걸려서 기본 3분 제한에 걸렸음
  args: ["--window-size=1600,900", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 900 });
await page.evaluateOnNewDocument(() => { try { localStorage.setItem("lang", "both"); localStorage.setItem("ui", "en"); } catch {} });
const smoothScroll = (y, ms = 1500) => page.evaluate((y, ms) => new Promise(r => {
  const y0 = scrollY, t0 = performance.now();
  const step = t => { const k = Math.min(1, (t - t0) / ms); scrollTo(0, y0 + (y - y0) * (0.5 - Math.cos(Math.PI * k) / 2)); k < 1 ? requestAnimationFrame(step) : r(); };
  requestAnimationFrame(step);
}), y, ms);
const clickText = async (sel, text) => {
  const el = await page.evaluateHandle((sel, text) => [...document.querySelectorAll(sel)].find(e => e.textContent.includes(text)), sel, text);
  await el.click();
};

if (scene === "making") {
  // 처음 화면 → 영상 넣기 → 만드는 과정이 끝날 때까지
  await page.goto(BASE + "/", { waitUntil: "networkidle0" });
  const rec = await page.screencast({ path: OUT + "making.webm" });
  await wait(3000);
  const input = await page.$("#file");
  await input.uploadFile(new URL("../samples/pov_latte_narrated.mp4", import.meta.url).pathname);
  await page.waitForFunction(() => location.hash.includes("making"), { timeout: 120000 });
  await page.waitForFunction(() => document.body.innerText.includes("Your cards are ready") || document.body.innerText.includes("Stopped with an error"), { timeout: 900000, polling: 2000 });
  await wait(2500);
  await clickText("button", "Check the cards");
  await wait(3000);
  await rec.stop();
  console.log(await page.evaluate(() => location.hash));
}

if (scene === "making_done") {
  // 다 만들어진 진행판 → 카드 확인하러 가기
  await page.goto(`${BASE}/#run=${runId}&view=making`, { waitUntil: "networkidle0" });
  await wait(800);
  const rec = await page.screencast({ path: OUT + "making_done.webm" });
  await wait(3500);
  await clickText("button", "Check the cards");
  await wait(3000);
  await rec.stop();
}

if (scene === "edit") {
  // 확인할 곳으로 이동 → 문장 고치기 → 자동 저장·검사 통과 → 다른 장면 고르기
  await page.goto(`${BASE}/#run=${runId}&view=edit`, { waitUntil: "networkidle0" });
  await wait(800);
  const rec = await page.screencast({ path: OUT + "edit.webm" });
  await wait(2500);
  await smoothScroll(900, 1800); await wait(1200); await smoothScroll(0, 1200); await wait(800);
  // 교사가 고친 문장이 규칙을 어기면 그 카드에 바로 표시되고, 다시 고치면 통과
  const row = "#row5";
  await page.evaluate(r => document.querySelector(r).scrollIntoView({ block: "center", behavior: "smooth" }), row); await wait(1800);
  const ta = await page.$(`${row} textarea.say`);
  const original = await page.evaluate(el => el.value, ta);
  await ta.click({ clickCount: 3 }); await wait(300);
  await ta.type("도구를 들고 " + original, { delay: 80 });
  await page.waitForFunction(r => document.querySelector(r).classList.contains("has-bad"), { timeout: 20000 }, row);
  await wait(3500);
  await ta.click({ clickCount: 3 }); await wait(300);
  await ta.type(original, { delay: 80 });
  await page.waitForFunction(r => !document.querySelector(r).classList.contains("has-bad") && document.querySelector("#saved").textContent.includes("Saved"), { timeout: 20000 }, row);
  await wait(3000);

  // 2번 카드에서 다른 장면 고르기
  await page.evaluate(() => document.querySelector("#row1").scrollIntoView({ block: "center", behavior: "smooth" })); await wait(1800);
  await page.click("#row1 .linkbtn"); await wait(2000);
  const frames = await page.$$("#row1 .strip button");
  await frames[Math.min(frames.length - 1, 6)].click();
  await page.waitForFunction(() => !document.querySelector("#row1 .busy"), { timeout: 60000, polling: 500 });
  await wait(2500);
  await rec.stop();
}

if (scene === "use") {
  await page.goto(`${BASE}/#run=${runId}&view=use`, { waitUntil: "networkidle0" });
  await wait(800);
  const rec = await page.screencast({ path: OUT + "use.webm" });
  await wait(2500);
  await smoothScroll(500, 2000); await wait(1500); await smoothScroll(1700, 2500); await wait(1500); await smoothScroll(0, 1200); await wait(500);
  await clickText("button.choice", "Tablet");
  await wait(2500);
  for (let i = 0; i < 4; i++) { await page.keyboard.press("ArrowRight"); await wait(1800); }
  await rec.stop();
}

if (scene === "coach") {
  // 카메라 대신 녹화 영상을 흘려 따라 하기를 보여 준다(화면에 그렇게 밝힘)
  const [startCard, clip] = [Number(process.argv[4] || 1), process.argv[5] || "coach.mp4"];
  await page.goto(`${BASE}/#run=${runId}&view=coach`, { waitUntil: "networkidle0" });
  await page.evaluate(n => { S.idx = n - 1; coachCard(); }, startCard);
  await wait(500);
  const rec = await page.screencast({ path: OUT + "coach.webm" });
  await wait(2500);
  await page.evaluate(clip => {
    const v = document.querySelector("#cvid"); v.src = `/runs/${S.run}/${clip}`; v.muted = true;
    v.onended = () => { C.running = false; }; return v.play().then(() => coachStart());
  }, clip);
  await page.waitForFunction(() => document.querySelector("#cvid").ended, { timeout: 300000, polling: 1000 });
  await wait(1500);
  await rec.stop();
}

if (scene === "edit2") {
  // 데모 v2 장면 4: 문장 고치기(빨강 → 통과) → 한 카드를 사진 → 그림 → 움직임으로 바꿔 보기
  await page.goto(`${BASE}/#run=${runId}&view=edit`, { waitUntil: "networkidle0" });
  await wait(800);
  const rec = await page.screencast({ path: OUT + "edit2.webm" });
  await wait(2000);
  const row = "#row2";
  await page.evaluate(r => document.querySelector(r).scrollIntoView({ block: "center", behavior: "smooth" }), row); await wait(1500);
  const ta = await page.$(`${row} textarea.say`);
  const original = await page.evaluate(el => el.value, ta);
  await ta.click({ clickCount: 3 }); await wait(300);
  await ta.type("냅킨을 들고 " + original, { delay: 70 });
  await page.waitForFunction(r => document.querySelector(r).classList.contains("has-bad"), { timeout: 20000 }, row);
  await wait(3000);
  await ta.click({ clickCount: 3 }); await wait(300);
  await ta.type(original, { delay: 70 });
  await page.waitForFunction(r => !document.querySelector(r).classList.contains("has-bad") && document.querySelector("#saved").textContent.includes("Saved"), { timeout: 20000 }, row);
  await wait(2000);
  const view = async label => { await clickText(`${row} .seg.mini button`, label); await wait(2800); };
  await view("Photo"); await view("Drawing"); await view("Motion"); await wait(1500);
  await view("Drawing");  // 원래 보기로 돌려 둔다
  await rec.stop();
}

if (scene === "montage") {
  // 데모 v2 장면 7: 과제별 카드 묶음을 차례로(실행 id 를 쉼표로)
  const runs = runId.split(",");
  await page.goto(`${BASE}/#run=${runs[0]}&view=edit`, { waitUntil: "networkidle0" });
  const rec = await page.screencast({ path: OUT + "montage.webm" });
  for (const r of runs) {
    await page.goto(`${BASE}/#run=${r}&view=edit`, { waitUntil: "networkidle0" });
    await wait(2200); await smoothScroll(700, 1500); await wait(800);
  }
  await rec.stop();
}

await browser.close();

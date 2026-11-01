// 데모 v3 화면 녹화(새 디자인): 실제 앱을 자동으로 조작해 장면별 webm 을 남긴다
// 사용: node demo/record_v3.mjs <장면>   장면 = coach | help | making | edit | glimmer | home | jobs
// coach·making 은 실제 Meta API 를 부른다(따라 하기 판단, 카드 만들기). 나머지는 이미 있는 카드만 보여 준다
import puppeteer from "puppeteer-core";
import { mkdirSync, writeFileSync, cpSync, rmSync } from "node:fs";

const scene = process.argv[2];
const BASE = "http://127.0.0.1:8790";
const L = process.env.DEMO_LANG || "en";  // 화면 언어: en | ko(한글판)
const KO = L === "ko", tx = (en, ko) => KO ? ko : en;
const RUN = KO ? "d3d3d3d3d3k1" : "d3d3d3d3d301";  // 냅킨 견본의 데모 전용 복사본(견본은 건드리지 않는다)
const OUT = new URL(`./out/v3${process.env.DEMO_LANG === "ko" ? "ko" : ""}/`, import.meta.url).pathname;
const NAPKIN = new URL("../samples/napkin_butterfly.mp4", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });
const wait = ms => new Promise(r => setTimeout(r, ms));

const browsers = [];
const errs = [];
async function open(path, w, h) {  // 화면마다 브라우저를 따로: 헤드리스에서 뒤에 깔린 탭은 그리지 않아 녹화가 시작되지 않았다
  const browser = await puppeteer.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: "new", protocolTimeout: 0,
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"],
  });
  browsers.push(browser);
  const p = (await browser.pages())[0] || await browser.newPage();
  p.on("pageerror", e => errs.push(e.message));
  await p.setViewport({ width: w, height: h });
  await p.evaluateOnNewDocument(l => { try { const L = l; localStorage.setItem("lang", L); localStorage.setItem("ui", L); localStorage.setItem("help", "on"); } catch {} }, L);
  await p.goto(BASE + path, { waitUntil: "load" }); await wait(1500);  // 안경·현황판은 계속 묻느라 networkidle 이 안 온다
  return p;
}
const smooth = (p, y, ms = 1500) => p.evaluate((y, ms) => new Promise(r => {
  const y0 = scrollY, t0 = performance.now();
  const step = t => { const k = Math.min(1, (t - t0) / ms); scrollTo(0, y0 + (y - y0) * (0.5 - Math.cos(Math.PI * k) / 2)); k < 1 ? requestAnimationFrame(step) : r(); };
  requestAnimationFrame(step);
}), y, ms);
const clickText = async (p, sel, text) => {
  const el = await p.evaluateHandle((sel, text) => [...document.querySelectorAll(sel)].find(e => e.textContent.includes(text)), sel, text);
  await el.click();
};

// 프레임마다 브라우저가 붙인 실제 시각으로 저장(page.screencast 는 프레임을 놓치면 길이가 줄거나 늘어 화면끼리 시간이 어긋났다)
// 결과: <name>/ 아래 jpg + frames.txt(ffconcat, 프레임별 길이). 0초 = 녹화 시작(mark "rec" 와 같은 순간)
// 거의 멈춘 화면(안경·현황판)은 크롬이 프레임을 보내지 않아 변화를 놓쳤다(카드 3 이 통째로 빠짐): 0.25초마다 스크린샷으로
async function shots(page, name) {
  const dir = OUT + name + "/"; rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
  const times = [], start = Date.now() / 1000; let on = true;
  const loop = (async () => { while (on) { const t = Date.now() / 1000, k = times.length; await page.screenshot({ path: dir + `f${String(k).padStart(5, "0")}.jpg`, type: "jpeg", quality: 85 }); times.push(t); await wait(Math.max(0, 250 - (Date.now() / 1000 - t) * 1000)); } })();
  return { async stop() {
    on = false; await loop; const end = Date.now() / 1000, lines = ["ffconcat version 1.0"];
    times.forEach((t, k) => { if (k === 0) lines.push("file f00000.jpg", `duration ${Math.max(0.001, t - start).toFixed(3)}`); lines.push(`file f${String(k).padStart(5, "0")}.jpg`, `duration ${((k + 1 < times.length ? times[k + 1] : end) - t).toFixed(3)}`); });
    lines.push(`file f${String(times.length - 1).padStart(5, "0")}.jpg`);
    writeFileSync(dir + "frames.txt", lines.join("\n") + "\n");
  } };
}
async function rec(page, name) {
  const dir = OUT + name + "/"; rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
  const cdp = await page.createCDPSession(), frames = [], start = Date.now() / 1000;
  cdp.on("Page.screencastFrame", f => {
    const k = frames.length; frames.push(f.metadata.timestamp);
    writeFileSync(dir + `f${String(k).padStart(5, "0")}.jpg`, Buffer.from(f.data, "base64"));
    cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 75, everyNthFrame: 2 });
  return { async stop() {
    const end = Date.now() / 1000;
    await cdp.send("Page.stopScreencast");
    const lines = ["ffconcat version 1.0"];
    frames.forEach((t, k) => {
      const t1 = k + 1 < frames.length ? frames[k + 1] : end;
      if (k === 0) lines.push(`file f00000.jpg`, `duration ${Math.max(0.001, frames[0] - start).toFixed(3)}`);
      lines.push(`file f${String(k).padStart(5, "0")}.jpg`, `duration ${Math.max(0.001, t1 - t).toFixed(3)}`);
    });
    lines.push(`file f${String(frames.length - 1).padStart(5, "0")}.jpg`);
    writeFileSync(dir + "frames.txt", lines.join("\n") + "\n");
  } };
}
const t0 = Date.now(), marks = [];
const mark = what => { marks.push({ t: +((Date.now() - t0) / 1000).toFixed(1), what }); console.log(marks.at(-1).t, what); };

if (scene === "coach") {
  // 냅킨 시범 영상을 카메라 대신 흘리고(앱의 '영상 파일로 시험하기'), 실제 Muse Spark 판단으로 카드가 넘어가는 것을 1~6번 카드까지
  const p = await open(`/?ui=${L}#run=${RUN}&view=coach`, 1440, 900);
  await wait(1200);
  const pair = await p.evaluate(() => C.pair);
  const g = await open(`/glasses?run=${RUN}&lang=${L}&m=${L}&s=${pair}`, 600, 600);
  const [r1, r2] = await Promise.all([rec(p, "coach"), shots(g, "coach_glasses")]);
  mark("rec");
  await wait(1500);
  const input = await p.$('#cstart input[type=file]');
  await input.uploadFile(NAPKIN); mark("video start");
  let last = 0;
  while (true) {  // 카드가 바뀔 때마다 영상 시각과 함께 적는다
    const s = await p.evaluate(() => ({ i: S.idx, vt: document.querySelector("#cvid").currentTime, lv: C.lv }));
    if (s.i !== last) { mark(`card ${s.i + 1} at video ${s.vt.toFixed(1)}s`); last = s.i; }
    if (s.vt > 70) break;
    await wait(250);
  }
  await wait(1000);
  await r1.stop(); await r2.stop();
}

if (scene === "help") {
  // 7번 카드(안 보이는 겹을 펴는 어려운 단계): 도움 단추로 글 → 그림 → 소리 → 움직임, 다 쓰면 '도와줘요' → 교사 현황판 '갈게요' → 학습자·안경에 '오고 있어요'
  const RUN = "d3h" + Date.now().toString(36);  // 매번 새 복사본: 현황판에 앞선 시험의 줄이 남지 않게
  cpSync(new URL(`../runs/${KO ? "d3d3d3d3d3k1" : "d3d3d3d3d301"}`, import.meta.url).pathname, new URL(`../runs/${RUN}`, import.meta.url).pathname, { recursive: true });
  const p = await open(`/?ui=${L}#run=${RUN}&view=coach`, 1440, 900);
  await wait(1200);
  await p.addStyleTag({ content: ".coachv .cam{visibility:hidden}" });  // 이 장면은 카메라를 켜지 않는다(빈 검은 창 숨김, 'Camera off' 표시는 그대로)
  const pair = await p.evaluate(() => C.pair);
  await fetch(`${BASE}/api/runs/${RUN}/call`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ s: pair, ack: true }) }).catch(() => {});
  await p.evaluate(() => { $("#cstart").hidden = true; C.started = true; setHelp(true); S.idx = 6; C.lv = 1; C.since = Date.now(); coachCard(true); glassesSync(true); });
  const g = await open(`/glasses?run=${RUN}&lang=${L}&m=${L}&s=${pair}`, 600, 600);
  const tch = await open(`/?ui=${L}#run=${RUN}&view=use`, 1000, 640);
  await wait(1500);
  const recs = await Promise.all([rec(p, "help"), shots(g, "help_glasses"), shots(tch, "help_teacher")]);
  mark("rec"); await wait(2500);
  for (let k = 0; k < 3; k++) { await p.click("#ccall"); mark(`help -> lv ${await p.evaluate(() => C.lv)}`); await wait(k === 2 ? 5000 : 3200); }
  await p.click("#ccall"); mark("ask for help");
  await tch.waitForFunction(() => document.querySelector("#liveboard .liverow.call button"), { timeout: 15000, polling: 300 });
  mark("teacher sees call"); await wait(2500);
  await tch.click("#liveboard .liverow.call button"); mark("on my way");
  await p.waitForFunction(() => /on the way|Help is coming|오고 있어요/.test(document.querySelector("#cpill")?.textContent + document.querySelector("#ccall")?.textContent), { timeout: 15000, polling: 200 });
  mark("learner sees help coming"); await wait(4000);
  for (const r of recs) await r.stop();
}

if (scene === "making") {
  // 처음 화면에서 냅킨 시범 영상을 넣고(Meta API) 카드가 다 될 때까지
  const p = await open(`/?ui=${L}`, 1440, 900);
  const rec = await p.screencast({ path: OUT + "making.webm" });
  mark("rec"); await wait(2000);
  await (await p.$("#file")).uploadFile(process.argv[3] || NAPKIN);  // 같은 파일이면 앞서 만든 카드로 바로 간다: 새로 만드는 모습은 바이트가 다른 복사본으로 mark("upload");
  await p.waitForFunction(() => location.hash.includes("making"), { timeout: 120000 });
  mark("making " + await p.evaluate(() => location.hash));
  await p.waitForFunction(() => /Your cards are ready|Stopped with an error|카드가 다 만들어졌어요|만들다가 멈췄어요/.test(document.body.innerText), { timeout: 900000, polling: 2000 });
  mark("done"); await wait(2500);
  await clickText(p, "button", tx("Check the cards", "카드 확인하러 가기")); await wait(3500);
  await rec.stop();
}

if (scene === "edit") {
  // 문장 하나 고치기(규칙 위반 빨강 → 되돌리면 통과) → 한 카드를 사진 · 움직임 · 3D 로 바꿔 보기
  const p = await open(`/?ui=${L}#run=${RUN}&view=edit`, 1440, 900);
  await wait(1000);
  const rec = await p.screencast({ path: OUT + "edit.webm" });
  mark("rec"); await wait(2500);
  const row = "#row1";
  await p.evaluate(r => document.querySelector(r).scrollIntoView({ block: "center", behavior: "smooth" }), row); await wait(1800);
  const ta = await p.$(`${row} textarea.say[lang=ko]`);  // 규칙 검사는 한국어 문장에 걸린다
  const original = await p.evaluate(el => el.value, ta);
  await ta.click({ clickCount: 3 }); await wait(300);
  await ta.type("냅킨을 들고 " + original, { delay: 70 }); mark("typed two actions");
  await p.waitForFunction(r => document.querySelector(r).classList.contains("has-bad"), { timeout: 20000 }, row);
  mark("red"); await wait(3500);
  await ta.click({ clickCount: 3 }); await wait(300);
  await ta.type(original, { delay: 55 });
  await p.waitForFunction(r => !document.querySelector(r).classList.contains("has-bad") && /Saved|저장됨/.test(document.querySelector("#saved").textContent), { timeout: 20000 }, row);
  mark("passed"); await wait(2000);
  const view = async label => { await clickText(p, `${row} .seg.mini button`, label); mark(label); await wait(3000); };
  await view(tx("Photo", "사진")); await view(tx("Motion", "움직임")); await view("3D"); await wait(2500);
  await rec.stop();
}

if (scene === "glimmer") {
  // 이 맥에서(Muse Glimmer) 끝까지 만든 실제 실행 기록
  const p = await open(`/?ui=${L}#run=6d5279d1379e&view=making`, 1440, 900);
  await wait(1200);
  const rec = await p.screencast({ path: OUT + "glimmer.webm" });
  mark("rec"); await wait(3000); await smooth(p, 600, 2500); await wait(3000); await smooth(p, 1400, 2500); await wait(2500);
  await rec.stop();
}

if (scene === "home") {
  const p = await open(`/?ui=${L}`, 1440, 900);
  await wait(1500);
  const rec = await p.screencast({ path: OUT + "home.webm" });
  mark("rec"); await wait(5000);
  const y = await p.evaluate(() => { const h = [...document.querySelectorAll("h2,h3")].find(e => /disabilit|장애/i.test(e.textContent)); return h ? h.getBoundingClientRect().top + scrollY - 80 : 900; });
  await smooth(p, y, 2500); mark("jobs"); await wait(5000);
  await rec.stop();
}

if (scene === "jobs") {
  // 국가 장애인 일자리 직무 카드: D&D 케어 승하차(사람을 돕는 일: 카메라 꺼짐) → 수어 인사(마주 보기) 태블릿
  const p = await open(`/?ui=${L}#run=07bd2594965b&view=coach`, 1440, 900);
  await wait(1500);
  const rec = await p.screencast({ path: OUT + "jobs.webm" });
  mark("rec"); await wait(4500);
  await p.goto(`${BASE}/?ui=${L}#run=07bd2594965b&view=tablet`, { waitUntil: "networkidle0" }); mark("car tablet"); await wait(3000);
  await p.keyboard.press("ArrowRight"); await wait(2500);
  await p.goto(`${BASE}/?ui=${L}#run=f3d1c1514436&view=tablet`, { waitUntil: "networkidle0" }); mark("sign tablet"); await wait(3500);
  await p.keyboard.press("ArrowRight"); await wait(3000);
  await rec.stop();
}

writeFileSync(OUT + `${scene}.marks.json`, JSON.stringify({ marks, errs }, null, 1));
console.log(JSON.stringify({ marks, errs }));
await Promise.race([Promise.all(browsers.map(b => b.close())), wait(8000)]);  // 영상이 도는 탭은 가끔 닫히지 않고 멈춘다
process.exit(0);

// 데모 v3 화면 녹화(새 디자인): 실제 앱을 자동으로 조작해 장면별 webm 을 남긴다
// 사용: node demo/record_v3.mjs <장면>   장면 = coach | help | making | edit | glimmer | home | jobs
// coach·making 은 실제 Meta API 를 부른다(따라 하기 판단, 카드 만들기). 나머지는 이미 있는 카드만 보여 준다
import puppeteer from "puppeteer-core";
import { mkdirSync, writeFileSync, cpSync, rmSync } from "node:fs";

const scene = process.argv[2];
const BASE = "http://127.0.0.1:8790";
const L = process.env.DEMO_LANG || "en";  // 화면 언어: en | ko(한글판)
const KO = L === "ko", tx = (en, ko) => KO ? ko : en;
const RUN = process.env.DEMO_RUN || (KO ? "d3d3d3d3d3k1" : "d3d3d3d3d301");  // 냅킨 견본의 데모 전용 복사본(견본은 건드리지 않는다)
const OUT = process.env.OUT_DIR || new URL(`./out/v3${process.env.DEMO_LANG === "ko" ? "ko" : ""}/`, import.meta.url).pathname;  // OUT_DIR: 데모 녹화를 덮지 않고 시험만 할 때
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
  // 2배 해상도로 찍어 1920 영상에서 글자가 또렷하게. 따라 하기(실제 판단)는 1배: 2배 녹화가 브라우저를 무겁게 해 판단이 밀렸다(넘김 지연 중간 23초)
  await p.setViewport({ width: w, height: h, deviceScaleFactor: ["coach", "watch", "learn"].includes(scene) ? 1 : 2 });
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
  let paused = 0, cut = 0;  // pause(): 기다리는 동안 버리고 그만큼 시각을 당긴다(영상에서 잘린 시간은 자막으로 밝힌다)
  cdp.on("Page.screencastFrame", f => {
    if (paused) { cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {}); return; }
    const k = frames.length; frames.push(f.metadata.timestamp - cut);
    writeFileSync(dir + `f${String(k).padStart(5, "0")}.jpg`, Buffer.from(f.data, "base64"));
    cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, everyNthFrame: 2, maxWidth: 3840, maxHeight: 2400 });
  return { pause() { paused = Date.now() / 1000; }, resume() { cut += Date.now() / 1000 - paused; paused = 0; }, async stop() {
    const end = Date.now() / 1000 - cut;
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
  const p = await open(`/?ui=${L}#run=${RUN}&view=coach`, 1152, 720);  // 작은 창: 카메라·판단 줄이 영상에서 크게 보이게
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
    const s = await p.evaluate(() => ({ i: S.idx, vt: document.querySelector("#cvid").currentTime, lv: C.lv, ended: document.querySelector("#cvid").ended, fin: !!document.querySelector("#csum") }));
    if (s.fin) { mark(`end screen at video ${s.vt.toFixed(1)}s`); break; }
    if (s.i !== last) { mark(`card ${s.i + 1} at video ${s.vt.toFixed(1)}s`); last = s.i; }
    if (s.vt > Number(process.env.UNTIL || 70) || s.ended) break;
    await wait(250);
  }
  await wait(1000);
  await r1.stop(); await r2.stop();
}

const SAMPLE = process.env.LEARN_RUN || "8e1456e529ca";  // 냅킨 견본: 시범 영상(demo.mp4)은 견본에서만 열린다. 이 두 장면은 견본을 읽기만 한다
if (scene === "watch") {
  // 먼저 보기(11-04 판): 왼쪽 시범 영상은 지금 카드 구간만 틀고 그 단계 끝에서 멈춰 실제 Muse Spark 판단을 기다린다. 오른쪽은 그 카드
  const p = await open(`/?ui=${L}#run=${SAMPLE}&view=coach`, 1280, 800);
  await wait(1200);
  const r1 = await rec(p, "watch");
  mark("rec"); await wait(2500);
  await p.evaluate(() => coachWatch()); mark("video start");
  let last = 0;
  while (true) {
    const s = await p.evaluate(() => ({ i: S.idx, vt: document.querySelector("#cvid").currentTime, paused: document.querySelector("#cvid").paused, fin: !!document.querySelector("#csum") }));
    if (s.fin) { mark("end screen"); break; }
    if (s.i !== last) { mark(`card ${s.i + 1} at video ${s.vt.toFixed(1)}s`); last = s.i; }
    if (s.i + 1 >= Number(process.env.UNTIL_CARD || 6)) { await wait(6000); break; }
    await wait(250);
  }
  await r1.stop();
}

if (scene === "learn") {
  // 회차 기록 · 3단계 카드 없이(11-04): 시범 영상을 카메라 스트림으로 흘려(captureStream) 실제 카메라 경로를 그대로 탄다.
  // 1회차(2단계, 녹화 안 함) → 2회차(3단계 카드 없이, 녹화) → 끝 화면의 '카메라가 확인한 카드'와 '지난번보다 도움이 줄어든 카드'
  const p = await open(`/?ui=${L}#run=${SAMPLE}&view=coach`, 1280, 800);
  await p.evaluate(() => { try { localStorage.removeItem("steps"); } catch {} });
  await p.evaluate(sample => {
    navigator.mediaDevices.getUserMedia = async () => {
      document.querySelector("#feedvid")?.remove();
      const hv = document.createElement("video"); hv.id = "feedvid"; hv.muted = true; hv.playsInline = true; hv.src = `/api/runs/${sample}/demo.mp4`;
      hv.style.cssText = "position:fixed;left:0;top:0;width:4px;height:4px;opacity:0;pointer-events:none"; document.body.append(hv);
      await hv.play(); const st = hv.captureStream(), tr = st.getVideoTracks()[0], gs = tr.getSettings.bind(tr);
      tr.getSettings = () => ({ ...gs(), facingMode: "environment" });  // 뒤카메라처럼(노트북 앞카메라로 보면 사진을 돌린다)
      return st;
    };
    // 카메라로 흘리는 시범 영상도 '먼저 보기'처럼: 지금 카드 구간을 틀고, 넘어갈 때까지 그 단계를 되풀이한다(학습자는 다음 카드가 나올 때까지 기다린다).
    // 그냥 흘리면 판단(3~10초)보다 영상이 앞서가 카드가 저절로 열리고 끝에는 손으로 넘겼다(11-04 첫 녹화). 두 회차 모두 같은 방식
    let idx = -1;
    setInterval(() => { const hv = document.querySelector("#feedvid"); if (!hv || !C.running) return; const cs = S.data.cards, c = cs[S.idx];
      if (idx !== S.idx) { idx = S.idx; if (hv.currentTime < c.start - 1.5 || hv.currentTime > c.end + 1) hv.currentTime = Math.max(0, c.start - 1); return; }
      if (hv.currentTime > c.end + 0.5) { const pe = S.idx ? cs[S.idx - 1].end : c.start - 1; hv.currentTime = Math.max(0, Math.min(c.start - 1, pe + 0.5)); } }, 300);
  }, SAMPLE);
  const PREV = process.env.PREV_SUP && JSON.parse(process.env.PREV_SUP);  // 1회차를 이미 실제로 돌렸으면 그 기록(카드별 도움 크기)을 넣고 2회차만 찍는다
  if (PREV) await p.evaluate((prev, sample) => { const cards = {}; S.data.cards.forEach((c, i) => { cards[c.n] = { s: prev[i], how: i === S.data.cards.length - 1 ? "manual" : "auto" }; });
    localStorage.setItem("steps", JSON.stringify({ [sample]: [{ at: Date.now() - 600000, help: true, bare: false, fin: true, cards }] })); }, PREV, SAMPLE);
  const done = async () => {  // 한 카드에 60초 넘게 머물거나, 시범 영상이 끝나고 25초가 지나도 끝 화면이 안 나오면 손으로 넘긴다(끝 화면에 '직접 넘김'으로 그대로 남는다)
    let endedAt = 0;
    while (!(await p.evaluate(() => !!document.querySelector("#csum")))) {
      const ended = await p.evaluate(() => !!document.querySelector("#feedvid")?.ended);
      if (ended && !endedAt) endedAt = Date.now();
      const onCard = await p.evaluate(() => (Date.now() - (C.cardAt || Date.now())) / 1000);
      if (onCard > 60 || (endedAt && Date.now() - endedAt > 25000)) { await p.evaluate(() => document.querySelector("#cnext").click()); mark("hand next"); await wait(1500); continue; }
      await wait(1000);
    }
  };
  if (!PREV) {
    await p.evaluate(() => coachCamera()); mark("run 1 start");
    await done(); mark("run 1 end " + JSON.stringify(await p.evaluate(() => ({ moves: (C.moves || []).length, sup: C.sup }))));
    await wait(1500);
  }
  const r1 = await rec(p, "learn");
  mark("rec"); await wait(1500);
  await p.evaluate(() => { S.idx = 0; route(); }); await wait(800);
  await p.evaluate(() => { C.bare = true; coachCamera(); }); mark("run 2 start");
  let last = 0;
  const watchCards = setInterval(async () => { const i = await p.evaluate(() => S.idx).catch(() => last); if (i !== last) { mark(`card ${i + 1}`); last = i; } }, 300);
  await done(); clearInterval(watchCards);
  mark("end screen " + JSON.stringify(await p.evaluate(() => [...document.querySelectorAll("#csum .d")].map(x => x.textContent))));
  await wait(6000);
  await r1.stop();
}

if (scene === "dance") {
  // 몸 보이기(11-04): 춤 시범을 카메라 스트림으로 흘리고(전체 → 60%로 당겨 발이 잘림 → 다시 전체), 기기 안 자세 인식 안내가 바뀌는 모습
  const R = "d8e60e3947bd";
  const p = await open(`/?ui=${L}#run=${R}&view=coach`, 1280, 800);
  await p.evaluate(r => { window.__zoom = 1;
    navigator.mediaDevices.getUserMedia = async () => {
      const hv = document.createElement("video"); hv.muted = true; hv.loop = true; hv.src = `/api/runs/${r}/demo.mp4`;
      hv.style.cssText = "position:fixed;left:0;top:0;width:4px;height:4px;opacity:0;pointer-events:none"; document.body.append(hv); await hv.play(); hv.currentTime = 30;
      const c = document.createElement("canvas"); c.width = 1280; c.height = 720; const x = c.getContext("2d");
      (function loop() { const z = window.__zoom, sw = hv.videoWidth * z, sh = hv.videoHeight * z, sx = Math.max(0, Math.min(hv.videoWidth - sw, hv.videoWidth * 0.62 - sw / 2));
        x.drawImage(hv, sx, 0, sw, sh, 0, 0, 1280, 720); requestAnimationFrame(loop); })();  // 비율을 지킨 채 당긴다(카메라에 다가선 것과 같다)
      const st = c.captureStream(15), tr = st.getVideoTracks()[0], gs = tr.getSettings.bind(tr); tr.getSettings = () => ({ ...gs(), facingMode: "user" }); return st;
    }; }, R);
  await p.evaluate(() => document.querySelectorAll(".csteps button")[1].click());
  await p.waitForFunction(() => /in view/i.test(document.querySelector("#cpose")?.textContent || ""), { timeout: 60000, polling: 300 });
  const r1 = await rec(p, "dance"); mark("rec"); await wait(5000);
  await p.evaluate(() => { window.__zoom = 0.6; }); mark("zoom in");
  await p.waitForFunction(() => /out of view|step back/i.test(document.querySelector("#cpose")?.textContent || ""), { timeout: 20000, polling: 200 }); mark("feet out"); await wait(4500);
  await p.evaluate(() => { window.__zoom = 1; }); mark("zoom out");
  await p.waitForFunction(() => /in view/i.test(document.querySelector("#cpose")?.textContent || ""), { timeout: 20000, polling: 200 }); mark("whole body"); await wait(3500);
  await r1.stop();
}

if (scene === "help") {
  // 7번 카드(안 보이는 겹을 펴는 어려운 단계): 도움 단추로 글 → 그림 → 소리 → 움직임, 다 쓰면 '도와줘요' → 교사 현황판 '갈게요' → 학습자·안경에 '오고 있어요'
  const RUN = "d3h" + Date.now().toString(36);  // 매번 새 복사본: 현황판에 앞선 시험의 줄이 남지 않게
  cpSync(new URL(`../runs/${process.env.DEMO_RUN || (KO ? "d3d3d3d3d3k1" : "d3d3d3d3d301")}`, import.meta.url).pathname, new URL(`../runs/${RUN}`, import.meta.url).pathname, { recursive: true });
  const p = await open(`/?ui=${L}#run=${RUN}&view=coach`, 1152, 720);
  await wait(1200);
  await p.addStyleTag({ content: ".coachv .cam{visibility:hidden}" });  // 이 장면은 카메라를 켜지 않는다(빈 검은 창 숨김, 'Camera off' 표시는 그대로)
  const pair = await p.evaluate(() => C.pair);
  await fetch(`${BASE}/api/runs/${RUN}/call`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ s: pair, ack: true }) }).catch(() => {});
  await p.evaluate(hi => { $("#cstart").hidden = true; C.started = true; setHelp(true); S.idx = hi; C.lv = 1; C.since = Date.now(); coachCard(true); glassesSync(true); }, +(process.env.HELP_IDX || 6));
  const g = await open(`/glasses?run=${RUN}&lang=${L}&m=${L}&s=${pair}`, 600, 600);
  const tch = await open(`/?ui=${L}#run=${RUN}&view=use`, 760, 480);  // 좁은 창: 현황판 줄(도와줘요·갈게요)이 영상에서 크게
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
  const recr = await rec(p, "making");
  mark("rec"); await wait(2000);
  await (await p.$("#file")).uploadFile(process.argv[3] || NAPKIN);  // 같은 파일이면 앞서 만든 카드로 바로 간다: 새로 만드는 모습은 바이트가 다른 복사본으로 mark("upload");
  await p.waitForFunction(() => location.hash.includes("making"), { timeout: 120000 });
  mark("making " + await p.evaluate(() => location.hash));
  await p.waitForFunction(() => /Your cards are ready|Stopped with an error|카드가 다 만들어졌어요|만들다가 멈췄어요/.test(document.body.innerText), { timeout: 900000, polling: 2000 });
  mark("done"); await wait(2500);
  await clickText(p, "button", tx("Check the cards", "카드 확인하러 가기")); await wait(1500);
  const ti = await p.$("input.titlein");  // 새로 만든 묶음은 제목이 비어 '과제 이름(예: …)'이 그대로 보였다
  if (ti) { await ti.click(); await ti.type(tx("Napkin butterfly fold", "냅킨 나비 접기"), { delay: 40 }); await p.keyboard.press("Tab"); }
  await wait(2500);
  await recr.stop();
}

if (scene === "edit") {
  // 문장 하나 고치기(규칙 위반 빨강 → 되돌리면 통과) → 한 카드를 사진 · 움직임 · 3D 로 바꿔 보기
  const p = await open(`/?ui=${L}#run=${RUN}&view=edit`, 1440, 900);
  await wait(1000);
  const recr = await rec(p, "edit");
  mark("rec"); await wait(2500);
  const row = "#row1";
  await p.evaluate(r => document.querySelector(r).scrollIntoView({ block: "center", behavior: "smooth" }), row); await wait(1800);
  const ta = await p.$(`${row} textarea.say[lang=${L === "en" ? "en" : "ko"}]`);  // 화면 언어의 문장을 고친다(두 동작 규칙은 두 언어 다 있다)
  const original = await p.evaluate(el => el.value, ta);
  await ta.click({ clickCount: 3 }); await wait(300);
  const two = L === "en" ? "Pick up the napkin and " + original[0].toLowerCase() + original.slice(1) : "냅킨을 들고 " + original;
  await ta.type(two, { delay: 70 }); mark("typed two actions");
  await p.waitForFunction(r => document.querySelector(r).classList.contains("has-bad"), { timeout: 20000 }, row);
  mark("red"); await wait(3500);
  await ta.click({ clickCount: 3 }); await wait(300);
  await ta.type(original, { delay: 55 });
  await p.waitForFunction(r => !document.querySelector(r).classList.contains("has-bad") && /Saved|저장됨/.test(document.querySelector("#saved").textContent), { timeout: 20000 }, row);
  mark("passed"); await wait(2000);
  const view = async label => { await clickText(p, `${row} .seg.mini button`, label); mark(label); await wait(3000); };
  await view(tx("Photo", "사진")); await view(tx("Motion", "움직임")); await view("3D"); await wait(2500);
  await recr.stop();
}

if (scene === "agent") {
  // Muse Spark에게 부탁하기: 부탁 → (기다림은 잘라 냄) → 고칠 안과 검사 횟수 → 적용
  const p = await open(`/?ui=${L}#run=${RUN}&view=edit`, 1440, 900);
  await wait(1000);
  await p.evaluate(() => document.querySelector("#askin").scrollIntoView({ block: "center" })); await wait(500);
  const recr = await rec(p, "agent");
  mark("rec"); await wait(1500);
  await p.click("#askin"); await wait(300);
  await p.type("#askin", tx("Simpler words for a learner who reads little", "글을 잘 못 읽는 사람도 알기 쉽게"), { delay: 55 }); await wait(600);
  await p.click("form.ask button"); mark("asked"); await wait(1500);
  recr.pause(); const tw = Date.now();
  await p.waitForSelector("#askres .askbox .askrow, #askres .askbox .btn", { timeout: 180000 });
  await wait(300); recr.resume(); mark(`answer after ${((Date.now() - tw) / 1000 + 1.5).toFixed(1)}s`);
  const info = await p.evaluate(() => ({ changes: S.ask?.changes?.length, checks: S.ask?.checks, cost: S.ask?.cost, problems: S.ask?.problems?.length, note: S.ask?.note }));
  marks.push({ t: 0, what: "agent", ...info, wait_s: +((Date.now() - tw) / 1000 + 1.5).toFixed(1) });
  await wait(3000);
  await p.evaluate(() => document.querySelector("#askres").scrollIntoView({ block: "start", behavior: "smooth" })); await wait(4000);
  await p.evaluate(() => document.querySelector("#askres .askbtns").scrollIntoView({ block: "center", behavior: "smooth" })); await wait(2500);
  if (info.changes) { await p.click("#askres .askbtns .btn.primary"); mark("applied"); await wait(3000); }
  await recr.stop();
}

if (scene === "glimmer") {
  // 이 맥에서(Muse Glimmer) 끝까지 만든 실제 실행 기록
  const p = await open(`/?ui=${L}#run=6d5279d1379e&view=making`, 1440, 900);
  await wait(1200);
  const recr = await rec(p, "glimmer");
  mark("rec"); await wait(3000); await smooth(p, 600, 2500); await wait(3000); await smooth(p, 1400, 2500); await wait(2500);
  await recr.stop();
}

if (scene === "home") {
  const p = await open(`/?ui=${L}`, 1440, 900);
  await wait(1500);
  const recr = await rec(p, "home");
  mark("rec"); await wait(5000);
  const y = await p.evaluate(() => { const h = [...document.querySelectorAll("h2,h3")].find(e => /disabilit|장애/i.test(e.textContent)); return h ? h.getBoundingClientRect().top + scrollY - 80 : 900; });
  await smooth(p, y, 2500); mark("jobs"); await wait(5000);
  await recr.stop();
}

if (scene === "jobs") {
  // 국가 장애인 일자리 직무 카드: D&D 케어 승하차(사람을 돕는 일: 카메라 꺼짐) → 수어 인사(마주 보기) 태블릿
  const p = await open(`/?ui=${L}#run=07bd2594965b&view=coach`, 1440, 900);
  await wait(1500);
  const recr = await rec(p, "jobs");
  mark("rec"); await wait(4500);
  await p.goto(`${BASE}/?ui=${L}#run=07bd2594965b&view=tablet`, { waitUntil: "networkidle0" }); mark("car tablet"); await wait(3000);
  await p.keyboard.press("ArrowRight"); await wait(2500);
  await p.goto(`${BASE}/?ui=${L}#run=f3d1c1514436&view=tablet`, { waitUntil: "networkidle0" }); mark("sign tablet"); await wait(3500);
  await p.keyboard.press("ArrowRight"); await wait(3000);
  await recr.stop();
}

if (scene === "breadth") {
  // 같은 과정으로 만든 다른 일들: 견본 카드 묶음을 태블릿 화면으로 차례로(라떼·찌개·서랍장·춤·돌봄·수어)
  const sets = ["9ba0bf565609", "06d0c8e9935c", "fa37916f40e3", "d8e60e3947bd", "07bd2594965b"];  // 내레이션 순서(카페 음료·찌개·서랍장·춤 → 돌봄)
  const p = await open(`/?ui=${L}#run=${sets[0]}&view=tablet`, 1440, 900);
  const recr = await rec(p, "breadth");
  mark("rec");
  for (const r of sets) {
    await p.goto(`${BASE}/?ui=${L}#run=${r}&view=tablet`, { waitUntil: "load" }); await wait(700);
    await p.keyboard.press("ArrowRight"); mark(r); await wait(2600);
  }
  await recr.stop();
}

writeFileSync(OUT + `${scene}.marks.json`, JSON.stringify({ marks, errs }, null, 1));
console.log(JSON.stringify({ marks, errs }));
await Promise.race([Promise.all(browsers.map(b => b.close())), wait(8000)]);  // 영상이 도는 탭은 가끔 닫히지 않고 멈춘다
process.exit(0);

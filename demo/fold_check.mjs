// 3D 접기 만들기 확인: 고치기 화면에서 '3D 접기 만들기'를 실제로 돌리고, 진행 기록·3D 그림을 남긴다
import puppeteer from "puppeteer-core";
const [run, out] = [process.argv[2], process.argv[3]], W = ms => new Promise(r => setTimeout(r, ms));
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new", protocolTimeout: 900000, args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
const p = await b.newPage(); const errs = []; p.on("pageerror", e => errs.push(e.message)); p.on("console", m => m.type() === "error" && errs.push(m.text()));
await p.setViewport({ width: 1200, height: 900 });
await p.goto(`http://127.0.0.1:8790/?ui=ko#run=${run}&view=edit`, { waitUntil: "load" }); await W(4000);
if (process.argv[4] !== "skip") {
  await p.click("#f3go");
  await p.waitForFunction(() => /넣었어요|못했어요/.test(document.querySelector(".f3log")?.innerText || ""), { timeout: 900000, polling: 2000 });
  console.log(await p.$eval(".f3log", e => e.innerText));
  await W(1500);
}
const prog = await p.evaluate(() => S.data.fold);
console.log(JSON.stringify(prog));
for (const n of [1, 3, 6, 12]) { const u = await p.evaluate(n => window.Fold3D.still(n), n); if (u) (await import("node:fs")).writeFileSync(`${out}_still${n}.jpg`, Buffer.from(u.split(",")[1], "base64")); }
await p.evaluate(() => document.querySelector("canvas.fold3d")?.scrollIntoView()); await W(1200);
await p.screenshot({ path: out + "_edit.png" });
console.log("errors", errs); await b.close();

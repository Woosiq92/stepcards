// 접기 엔진 시험(node test_fold.mjs). 3D 화면과 검사기가 같은 static/fold.js 를 쓴다
import assert from "node:assert/strict";
import { initial, apply, run, bbox, totalArea, facesAt, area } from "./static/fold.js";
const near = (a, b, e = 1e-6) => assert.ok(Math.abs(a - b) < e, `${a} != ${b}`);
let s = initial();

// 1. 밑단을 위로 반 접기: 면적 그대로, 높이 절반, 두 겹
let r = apply(s, { op: "fold", from: "bottom", to: "top", dir: "valley" });
assert.equal(r.problem, undefined); near(totalArea(r.state), 1); near(bbox(r.state).h, 0.5); near(bbox(r.state).w, 1);
assert.equal(facesAt(r.state, [0.5, 0.25]).length, 2);
const half = r.state;

// 2. 정사각형 위 왼쪽 모서리를 가운데로: 넓이 1/8 삼각형이 뒤집혀 맨 위로, 면적 그대로
r = apply(s, { op: "fold", from: "top-left", to: "center", dir: "valley" });
assert.equal(r.problem, undefined); near(totalArea(r.state), 1);
const topL = Math.max(...r.state.faces.map(f => f.layer)), flap = r.state.faces.filter(f => f.layer === topL);
assert.equal(flap.length, 1); assert.equal(flap[0].poly.length, 3); near(area(flap[0].poly), 1 / 8);
assert.equal(flap[0].up, false);
// 산접기면 같은 조각이 맨 아래로
const m = apply(s, { op: "fold", from: "top-left", to: "center", dir: "mountain" }).state;
assert.ok(m.faces.find(f => !f.up).layer < Math.min(...m.faces.filter(f => f.up).map(f => f.layer)));

// 3. 뒤집기: 겹 순서 반대, 앞뒤 바뀜, 면적 그대로
const f = apply(half, { op: "flip" });
near(totalArea(f.state), 1);
assert.deepEqual(f.state.faces.map(x => x.up).sort(), half.faces.map(x => !x.up).sort());

// 4. 맨 위 한 겹만 접기: 아래 겹은 그대로
r = apply(half, { op: "fold", from: "top-left", to: "bottom-left", layers: "top" });
assert.equal(r.problem, undefined); near(totalArea(r.state), 1);

// 4-2. 맨 아래 한 겹만(뒤에 숨은 겹 꺼내기): 위 겹은 그대로, 면적 그대로
const top0 = half.faces.find(f => f.layer === Math.max(...half.faces.map(x => x.layer)));
r = apply(half, { op: "fold", from: "top-left", to: "bottom-left", layers: "bottom", dir: "mountain" });
assert.equal(r.problem, undefined); near(totalArea(r.state), 1);
assert.ok(r.state.faces.some(f => f.id === top0.id && JSON.stringify(f.poly) === JSON.stringify(top0.poly)), "위 겹은 그대로");

// 5. 검사기가 잡는 것
assert.match(apply(s, { op: "fold", from: "middle", to: "top" }).problem, /named point/);
assert.match(apply(s, { op: "fold", from: "top", to: "top" }).problem, /same point/);
assert.match(apply(s, { op: "spin" }).problem, /unknown op/);
assert.match(apply(half, { op: "fold", from: [0.5, 0.9], to: "top", layers: 0 }).problem, /layers/);
assert.match(apply(s, { op: "fold", from: "top", to: [0.5, -1] }).problem, /whole cloth|nothing moves/);

// 6. 프로그램 전체: 없는 카드·빈 동작 보고, 정상 단계는 프레임으로
const p = run({ shape: { w: 1, h: 1 }, steps: [
  { n: 1, ops: [{ op: "fold", from: "bottom", to: "top" }] },
  { n: 2, ops: [{ op: "fold", from: "top-left", to: "center" }, { op: "fold", from: "top-right", to: "center" }] },
  { n: 3, ops: [{ op: "flip" }] }, { n: 9, ops: [] }] }, [1, 2, 3]);
assert.deepEqual(p.problems, ["step for card n=9: no such card"]);
assert.equal(p.frames.length, 3); near(totalArea(p.final), 1);
assert.equal(p.frames[1].anims.length, 2);
console.log("fold engine: all checks passed");

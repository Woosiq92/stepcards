// 접기 엔진: 종이·천을 평평한 다각형 면들로 보고, 접는 선으로 면을 나눠 뒤집어 쌓는다(평면 접기).
// 브라우저(3D 화면)와 node 시험이 같이 쓴다. 3D 그리기는 fold3d.js, 여기는 계산만.
// 좌표: 이미지처럼 왼쪽 위가 (0,0), 오른쪽·아래로 커진다. 모델이 쓰는 점은 '지금 천 전체 테두리 상자' 기준 0~1.

const EPS = 1e-7;
export const NAMED = {
  "top-left": [0, 0], "top": [0.5, 0], "top-right": [1, 0], "left": [0, 0.5], "center": [0.5, 0.5],
  "right": [1, 0.5], "bottom-left": [0, 1], "bottom": [0.5, 1], "bottom-right": [1, 1],
};
export const OPS = ["fold", "tuck", "flip", "rotate", "pinch"];

export function initial(shape = {}) {
  const w = +shape.w > 0 ? +shape.w : 1, h = +shape.h > 0 ? +shape.h : 1;
  return { faces: [{ id: 0, poly: [[0, 0], [w, 0], [w, h], [0, h]], layer: 0, up: true }], next: 1, sx: 1 };
}
const clone = s => ({ ...s, faces: s.faces.map(f => ({ ...f, poly: f.poly.map(p => [...p]) })) });

export function bbox(s) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const f of s.faces) for (const [x, y] of f.poly) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 };
}
export function area(poly) { let a = 0; for (let i = 0; i < poly.length; i++) { const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length]; a += x1 * y2 - x2 * y1; } return Math.abs(a) / 2; }
export const totalArea = s => s.faces.reduce((a, f) => a + area(f.poly), 0);

function inside(poly, [x, y]) {  // 경계 위도 안으로 본다
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    const cross = (xj - xi) * (y - yi) - (yj - yi) * (x - xi);
    if (Math.abs(cross) < 1e-6 && Math.min(xi, xj) - 1e-6 <= x && x <= Math.max(xi, xj) + 1e-6 && Math.min(yi, yj) - 1e-6 <= y && y <= Math.max(yi, yj) + 1e-6) return true;
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c;
  }
  return c;
}
export const facesAt = (s, p) => s.faces.filter(f => inside(f.poly, p));

// 점 표기 → 실제 좌표. 이름("top-left") 또는 [x, y](0~1, 지금 천 테두리 기준)
export function point(s, v) {
  const b = bbox(s), q = typeof v === "string" ? NAMED[v] : Array.isArray(v) && v.length === 2 && v.every(Number.isFinite) ? v : null;
  return q ? [b.x0 + q[0] * b.w, b.y0 + q[1] * b.h] : null;
}
const side = (p, o, d) => (p[0] - o[0]) * d[1] - (p[1] - o[1]) * d[0];  // 선(o, 방향 d)의 어느 쪽인지

function clip(poly, o, d, keep) {  // keep 쪽(부호) 반평면으로 자르기
  const out = [];
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length], sa = side(a, o, d) * keep, sb = side(b, o, d) * keep;
    if (sa >= -EPS) out.push(a);
    if ((sa > EPS && sb < -EPS) || (sa < -EPS && sb > EPS)) { const t = sa / (sa - sb); out.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]); }
  }
  const clean = out.filter((p, i) => { const q = out[(i + 1) % out.length]; return Math.hypot(p[0] - q[0], p[1] - q[1]) > 1e-9; });
  return clean.length >= 3 && area(clean) > 1e-9 ? clean : null;
}
function reflect([x, y], o, d) {
  const L = Math.hypot(d[0], d[1]), ux = d[0] / L, uy = d[1] / L, px = x - o[0], py = y - o[1], t = px * ux + py * uy;
  return [o[0] + 2 * t * ux - px, o[1] + 2 * t * uy - py];
}

/* 한 동작을 적용한다. 돌려주는 것: { state(뒤), anim(3D 화면이 움직일 정보), problem(검사기 문장, 있으면 실패) }
   fold : from 점을 to 점으로 가져가 접기(접는 선 = 두 점의 수직이등분선). dir valley=위로 겹침, mountain=아래로.
          layers "all" | "top" | "bottom"(맨 아래 한 겹: 뒤에 숨은 겹을 꺼낼 때) | 숫자(from 점에서 위에서부터 몇 겹)
   tuck : fold 와 같지만 접힌 부분이 맨 위 한 겹 '아래'로 들어간다(주머니에 넣기)
   flip : 천을 뒤집기(axis vertical=좌우로 넘김, horizontal=위아래로)
   rotate : 바닥에서 돌리기(deg, 시계 방향 +)
   pinch : 가운데를 집어 모으기(axis vertical=좌우에서 가운데로) — 모양만 근사 */
export function apply(s, op) {
  if (!op || !OPS.includes(op.op)) return { problem: `unknown op "${op?.op}" (use ${OPS.join(", ")})` };
  if (op.op === "flip") {
    const b = bbox(s), v = op.axis !== "horizontal", cx = b.x0 + b.w / 2, cy = b.y0 + b.h / 2;
    const top = Math.max(...s.faces.map(f => f.layer)), bot = Math.min(...s.faces.map(f => f.layer));
    const t = clone(s);
    for (const f of t.faces) { f.poly = f.poly.map(([x, y]) => v ? [2 * cx - x, y] : [x, 2 * cy - y]).reverse(); f.layer = top + bot - f.layer; f.up = !f.up; }
    return { state: t, anim: { kind: "flip", axis: v ? "vertical" : "horizontal", c: [cx, cy] } };
  }
  if (op.op === "rotate") {
    const deg = +op.deg; if (!Number.isFinite(deg) || !deg) return { problem: "rotate needs deg (e.g. 90 or -90)" };
    const b = bbox(s), c = [b.x0 + b.w / 2, b.y0 + b.h / 2], r = deg * Math.PI / 180, cs = Math.cos(r), sn = Math.sin(r);
    const t = clone(s);
    for (const f of t.faces) f.poly = f.poly.map(([x, y]) => [c[0] + (x - c[0]) * cs - (y - c[1]) * sn, c[1] + (x - c[0]) * sn + (y - c[1]) * cs]);
    return { state: t, anim: { kind: "rotate", c, deg } };
  }
  if (op.op === "pinch") {
    const b = bbox(s), v = op.axis !== "horizontal", k = 0.55, cx = b.x0 + b.w / 2, cy = b.y0 + b.h / 2;
    const t = clone(s);
    for (const f of t.faces) f.poly = f.poly.map(([x, y]) => v ? [cx + (x - cx) * (Math.abs(y - cy) < b.h * 0.18 ? k : 0.9), y] : [x, cy + (y - cy) * (Math.abs(x - cx) < b.w * 0.18 ? k : 0.9)]);
    return { state: t, anim: { kind: "pinch", axis: v ? "vertical" : "horizontal", c: [cx, cy] } };
  }
  // fold / tuck
  const P = point(s, op.from), Q = point(s, op.to);
  if (!P) return { problem: `"from" must be a named point (${Object.keys(NAMED).join(", ")}) or [x, y] between 0 and 1` };
  if (!Q) return { problem: `"to" must be a named point or [x, y] between 0 and 1` };
  if (Math.hypot(P[0] - Q[0], P[1] - Q[1]) < 1e-6) return { problem: `"from" and "to" are the same point` };
  const at = facesAt(s, P);
  if (!at.length) return { problem: `"from" point is not on the cloth (the current shape does not cover it)` };
  const o = [(P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2], d = [-(Q[1] - P[1]), Q[0] - P[0]];  // 접는 선: 가운데를 지나고 PQ에 수직
  const mv = Math.sign(side(P, o, d));
  const levels = [...new Set(at.map(f => f.layer))].sort((a, b) => b - a);
  const L = op.layers ?? "all", n = L === "top" ? 1 : Number.isInteger(L) && L > 0 ? L : null;
  if (L !== "all" && L !== "bottom" && !n) return { problem: `"layers" must be "all", "top", "bottom" or a whole number` };
  const minLayer = n ? levels[Math.min(n, levels.length) - 1] : -Infinity, maxLayer = L === "bottom" ? levels[levels.length - 1] : Infinity;  // bottom: 맨 아래 한 겹만(뒤에 숨은 겹 꺼내기)
  const stay = [], moving = [];
  for (const f of s.faces) {
    if (f.layer < minLayer || f.layer > maxLayer) { stay.push(f); continue; }
    const a = clip(f.poly, o, d, mv), b = clip(f.poly, o, d, -mv);
    if (b) stay.push({ ...f, poly: b });
    if (a) moving.push({ ...f, poly: a });
  }
  if (!moving.length) return { problem: `nothing moves: the fold line does not cut the chosen layers` };
  if (!stay.length) return { problem: `the whole cloth would move: "to" should be a point the cloth folds onto` };
  const top = Math.max(...s.faces.map(f => f.layer)), bot = Math.min(...s.faces.map(f => f.layer));
  const mTop = Math.max(...moving.map(f => f.layer)), mBot = Math.min(...moving.map(f => f.layer));
  const valley = op.dir !== "mountain";
  let place;
  if (op.op === "tuck") {  // 맨 위 한 겹 바로 아래로(주머니)
    const under = Math.max(...stay.filter(f => f.layer < top).map(f => f.layer), bot - 1);
    place = l => under + (top - under) * (0.2 + 0.6 * (mTop - l + 1) / (mTop - mBot + 2));
  } else place = valley ? l => top + 1 + (mTop - l) : l => bot - 1 - (l - mBot);
  let id = s.next;
  const moved = moving.map(f => ({ id: id++, from: f.id, poly: f.poly.map(p => reflect(p, o, d)).reverse(), layer: place(f.layer), up: !f.up }));
  const state = { ...s, faces: [...stay.map(f => ({ ...f, poly: f.poly.map(p => [...p]) })), ...moved], next: id };
  return { state, anim: { kind: "fold", o, d, p: P, q: Q, valley: op.op === "tuck" ? false : valley, moving: moving.map((f, i) => ({ before: f, after: moved[i] })) } };
}

// 카드별 접기 프로그램 전체를 검사하며 적용. problems 는 검사기 문장(카드 번호 포함)
export function run(program, cardNs) {
  const problems = [], frames = [];
  let s = initial(program?.shape);
  const known = new Set(cardNs);
  for (const st of program?.steps || []) {
    if (!known.has(st.n)) { problems.push(`step for card n=${st.n}: no such card`); continue; }
    if ((st.ops || []).length > 4) problems.push(`card n=${st.n}: more than 4 moves; one card is one action`);
    const before = s, anims = [];
    for (const op of st.ops || []) {
      const r = apply(s, op);
      if (r.problem) { problems.push(`card n=${st.n}: ${r.problem}`); continue; }
      const b = bbox(r.state);
      if (b.w < 0.02 || b.h < 0.02) { problems.push(`card n=${st.n}: the cloth becomes a line`); continue; }
      anims.push({ from: s, to: r.state, ...r.anim }); s = r.state;
    }
    frames.push({ n: st.n, before, after: s, anims });
  }
  return { problems, frames, final: s };
}

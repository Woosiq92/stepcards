// 3D 접기 카드: fold.js 가 계산한 면을 three.js 로 그리고, 카드마다 '이전 모양 → 이번 접기'를 되풀이해 보여 준다.
// 렌더러는 하나만 두고(브라우저 WebGL 개수 한도), 화면에 보이는 <canvas class="fold3d" data-n> 마다 그려서 옮겨 붙인다.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
import { run, bbox } from "./fold.js";

const W = 480, H = 360, LAYER = 0.006, PAUSE0 = 0.5, MOVE = 3.2, PAUSE1 = 1.2;  // 접기 한 번 3.2초(선 보이기 0.8 · 넘기기 1.8 · 쓸어 누르기 0.6)
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setSize(W, H, false); renderer.setPixelRatio(1); renderer.setClearColor(0xf4f1ea, 1);  // 종이색 바탕(검사용 jpeg 도 같은 바탕)
const ink = new THREE.LineBasicMaterial({ color: 0x11183a });
let memo = { key: "", res: null };

function result() {
  const g = window.Fold3D?.source?.(); if (!g?.program) return null;
  const key = JSON.stringify(g.program) + g.cardNs.join(",");
  if (memo.key !== key) memo = { key, res: run(g.program, g.cardNs), color: g.program.shape?.color || "#c0392b" };
  return memo;
}
const shade = (hex, k) => { const c = new THREE.Color(hex); c.multiplyScalar(k); return c; };
const backOf = hex => new THREE.Color(hex).lerp(new THREE.Color(0xffffff), 0.45);  // 뒷면은 밝게: 접혀 올라온 조각이 구분되게

// 면 하나: 앞(위)과 뒤 색을 달리하고, 먹선 테두리를 붙인다. 바닥 평면(XZ), 이미지의 아래쪽 = 보는 사람 쪽(+Z)
function faceMesh(f, rank, color) {
  const shape = new THREE.Shape(f.poly.map(([x, y]) => new THREE.Vector2(x, -y)));
  const geo = new THREE.ShapeGeometry(shape);
  const g = new THREE.Group();
  const front = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: f.up ? shade(color, 1) : backOf(color), side: THREE.FrontSide }));
  const back = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: f.up ? backOf(color) : shade(color, 1), side: THREE.BackSide }));
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo), ink);
  g.add(front, back, edge);
  g.rotation.x = -Math.PI / 2;  // 모양의 (x, -y) → 바닥의 (x, y)
  g.position.y = rank * LAYER;
  return g;
}
function ranks(faces) { const ls = [...new Set(faces.map(f => f.layer))].sort((a, b) => a - b); return f => ls.indexOf(f.layer) + 1; }
function stateGroup(st, color, skip = new Set()) {
  const g = new THREE.Group(), rk = ranks(st.faces);
  for (const f of st.faces) if (!skip.has(f.id)) g.add(faceMesh(f, rk(f), color));
  return g;
}
const ease = t => t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;

// 접는 방향 화살표: from → to 위로 굽은 선
function arrow(p, q, lift) {
  const a = new THREE.Vector3(p[0], lift, p[1]), b = new THREE.Vector3(q[0], lift, q[1]);
  const m = a.clone().add(b).multiplyScalar(0.5); m.y += a.distanceTo(b) * 0.45;
  const curve = new THREE.QuadraticBezierCurve3(a, m, b);
  const g = new THREE.Group(), mat = new THREE.MeshBasicMaterial({ color: 0x2f63f4 });
  g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.012, 6), mat));
  const tip = new THREE.Mesh(new THREE.ConeGeometry(0.04, 0.1, 12), mat);
  tip.position.copy(b); tip.lookAt(curve.getPoint(0.9)); tip.rotateX(-Math.PI / 2);
  g.add(tip); return g;
}

// 종이접기 도해 표시: 접는 선(골 = 점선, 산 = 점-선), 잡을 곳 손가락 점
const blue = new THREE.MeshBasicMaterial({ color: 0x2f63f4 }), creaseMat = new THREE.MeshBasicMaterial({ color: 0x11183a });
function creaseSeg(an) {  // 천 위에 실제로 생기는 접는 선 구간(움직이는 조각의 꼭짓점 중 선 위에 있는 것)
  const L = Math.hypot(an.d[0], an.d[1]), u = [an.d[0] / L, an.d[1] / L];
  let lo = Infinity, hi = -Infinity;
  for (const m of an.moving) for (const [x, y] of m.before.poly) {
    const px = x - an.o[0], py = y - an.o[1];
    if (Math.abs(px * u[1] - py * u[0]) < 1e-6) { const k = px * u[0] + py * u[1]; lo = Math.min(lo, k); hi = Math.max(hi, k); }
  }
  return lo < hi ? [[an.o[0] + lo * u[0], an.o[1] + lo * u[1]], [an.o[0] + hi * u[0], an.o[1] + hi * u[1]]] : null;
}
function crease(seg, valley, y) {
  const g = new THREE.Group(); if (!seg) return g;
  const [a, b] = seg, len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const pattern = valley ? [0.045, 0.03] : [0.045, 0.022, 0.008, 0.022];  // 골접기 점선, 산접기 점-선
  let k = 0, i = 0;
  while (k < len) {
    const l = Math.min(pattern[i % pattern.length], len - k);
    if (i % 2 === 0) {
      const s = new THREE.Vector3(a[0] + (b[0] - a[0]) * k / len, y, a[1] + (b[1] - a[1]) * k / len);
      const e = new THREE.Vector3(a[0] + (b[0] - a[0]) * (k + l) / len, y, a[1] + (b[1] - a[1]) * (k + l) / len);
      g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.LineCurve3(s, e), 1, 0.006, 5), creaseMat));
    }
    k += l; i++;
  }
  return g;
}
function finger(pos, pulse) {
  const g = new THREE.Group();
  g.add(new THREE.Mesh(new THREE.SphereGeometry(0.028, 16, 12), blue));
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.05 + 0.02 * pulse, 0.006, 6, 24), blue);
  ring.rotation.x = Math.PI / 2; g.add(ring);
  g.position.copy(pos); return g;
}
const clamp01 = x => Math.max(0, Math.min(1, x));

// 한 동작이 t(0~1)만큼 진행된 장면. 접기는 세 구간: 선·잡을 곳 보이기(0~0.25) → 넘기기(~0.8) → 접힌 선 쓸어 누르기
function animGroup(an, t, color) {
  const g = new THREE.Group();
  let e = ease(t);
  if (an.kind === "fold") {
    e = ease(clamp01((t - 0.25) / 0.55));
    const movedIds = new Set(an.moving.map(m => m.after.id));
    g.add(stateGroup(an.to, color, movedIds));
    const top = Math.max(...an.to.faces.map(f => f.layer)), rk = ranks(an.to.faces);
    const axisO = new THREE.Vector3(an.o[0], 0, an.o[1]), axisD = new THREE.Vector3(an.d[0], 0, an.d[1]).normalize();
    // 움직이는 쪽이 위로 들리는 회전 방향을 고른다(골접기는 위로, 산접기는 아래로 넘어간다)
    const probe = new THREE.Vector3(an.p[0], 0, an.p[1]).sub(axisO).applyAxisAngle(axisD, Math.PI / 2);
    const sign = (probe.y > 0 ? 1 : -1) * (an.valley ? 1 : -1);
    const rkBefore = ranks(an.from.faces);
    for (const m of an.moving) {  // 접기 전 높이에서 시작해, 반 바퀴 돌고 나면 접은 뒤 높이에 놓이게(회전이 높이를 뒤집으므로 축 높이로 보탠다)
      const hb = rkBefore(m.before) * LAYER, ha = rk(m.after) * LAYER;
      const piece = faceMesh(m.before, 0, color);
      const pivot = new THREE.Group(); pivot.position.copy(axisO); pivot.position.y = e * (hb + ha) + Math.sin(Math.PI * e) * 0.02;
      piece.position.set(-axisO.x, hb, -axisO.z);
      pivot.add(piece); pivot.setRotationFromAxisAngle(axisD, sign * Math.PI * e);
      g.add(pivot);
    }
    const hy = (an.to.faces.length + 2) * LAYER + 0.01, seg = creaseSeg(an);
    if (t < 0.25 || t > 0.8) g.add(crease(seg, an.valley, hy));
    if (t < 0.25) {  // 잡을 곳과 방향
      g.add(arrow(an.p, an.q, hy));
      g.add(finger(new THREE.Vector3(an.p[0], hy, an.p[1]), Math.sin(t * 40) * 0.5 + 0.5));
    } else if (t <= 0.8) {  // 손가락이 모서리를 잡고 같이 넘어간다
      const pivot = new THREE.Group(); pivot.position.copy(axisO); pivot.position.y = e * 2 * hy;
      pivot.add(finger(new THREE.Vector3(an.p[0] - axisO.x, hy, an.p[1] - axisO.z), 0));
      pivot.setRotationFromAxisAngle(axisD, sign * Math.PI * e); g.add(pivot);
    } else if (seg) {  // 접힌 선을 따라 쓸어 누르기
      const k = clamp01((t - 0.8) / 0.2);
      g.add(finger(new THREE.Vector3(seg[0][0] + (seg[1][0] - seg[0][0]) * k, hy, seg[0][1] + (seg[1][1] - seg[0][1]) * k), 0));
    }
  } else if (an.kind === "flip") {
    const st = stateGroup(an.from, color), pivot = new THREE.Group();
    pivot.position.set(an.c[0], 0, an.c[1]); st.position.set(-an.c[0], 0, -an.c[1]);
    pivot.add(st); pivot.position.y = Math.sin(Math.PI * e) * 0.35;
    pivot.rotation[an.axis === "vertical" ? "z" : "x"] = Math.PI * e;
    g.add(pivot);
  } else if (an.kind === "rotate") {
    const st = stateGroup(an.from, color), pivot = new THREE.Group();
    pivot.position.set(an.c[0], 0, an.c[1]); st.position.set(-an.c[0], 0, -an.c[1]);
    pivot.add(st); pivot.rotation.y = -an.deg * Math.PI / 180 * e; g.add(pivot);
  } else {  // pinch: 같은 면들의 꼭짓점을 이어서 옮긴다
    const mix = { ...an.from, faces: an.from.faces.map((f, i) => ({ ...f, poly: f.poly.map((p, j) => { const q = an.to.faces[i]?.poly[j] || p; return [p[0] + (q[0] - p[0]) * e, p[1] + (q[1] - p[1]) * e]; }) })) };
    g.add(stateGroup(mix, color));
  }
  return g;
}

function frameScene(fr, time, color) {
  const n = fr.anims.length, total = PAUSE0 + n * MOVE + PAUSE1, t = time % total;
  if (!n || t >= PAUSE0 + n * MOVE) return { group: stateGroup(fr.after, color), b: bbox(fr.after) };
  if (t < PAUSE0) { const g = n ? animGroup(fr.anims[0], 0, color) : stateGroup(fr.before, color); return { group: g, b: bbox(fr.before) }; }
  const k = Math.floor((t - PAUSE0) / MOVE), an = fr.anims[k];
  return { group: animGroup(an, (t - PAUSE0 - k * MOVE) / MOVE, color), b: bbox(an.from) };
}

// 카메라: 하는 사람 눈높이에서 앞쪽 위로 내려다본다. 한 카드 안에서는 이전·이후 모양을 다 담는 크기로 고정
function view(fr) {
  const a = bbox(fr.before), b = bbox(fr.after);
  const x0 = Math.min(a.x0, b.x0), x1 = Math.max(a.x1, b.x1), y0 = Math.min(a.y0, b.y0), y1 = Math.max(a.y1, b.y1);
  const cx = (x0 + x1) / 2, cz = (y0 + y1) / 2, size = Math.max(x1 - x0, y1 - y0, 0.3);
  const cam = new THREE.PerspectiveCamera(38, W / H, 0.01, 50);
  cam.position.set(cx, size * 1.55, cz + size * 1.05); cam.lookAt(cx, 0, cz);
  return cam;
}

export function draw(fr, time, color, target) {
  const scene = new THREE.Scene();
  scene.add(new THREE.AmbientLight(0xffffff, 1.7));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(0.4, 2, 1.2); scene.add(sun);
  scene.add(frameScene(fr, time, color).group);
  renderer.render(scene, view(fr));
  const ctx = target.getContext("2d");
  ctx.clearRect(0, 0, target.width, target.height);
  ctx.drawImage(renderer.domElement, 0, 0, target.width, target.height);
  scene.traverse(o => { o.geometry?.dispose(); if (o.material && o.material !== ink) o.material.dispose(); });
}

// 화면에 보이는 3D 카드만 그린다(약 30fps)
let last = 0;
const clock = new WeakMap();  // 3D 카드마다 따로 흐르는 시간
function loop(now) {
  requestAnimationFrame(loop);
  if (now - last < 33) return; last = now;
  const m = result(); if (!m) return;
  for (const cv of document.querySelectorAll("canvas.fold3d")) {
    const r = cv.getBoundingClientRect();
    if (!r.width || r.bottom < 0 || r.top > innerHeight) continue;
    const fr = m.res.frames.find(f => f.n === +cv.dataset.n);
    if (!fr) continue;
    const c = clock.get(cv) || { t: 0, at: now }, speed = window.Fold3D.slow ? 0.5 : 1;  // 느리게(0.5배)·멈춤은 화면 단추가 바꾼다
    if (!cv.dataset.paused) c.t += (now - c.at) / 1000 * speed;
    c.at = now; clock.set(cv, c);
    draw(fr, c.t, m.color, cv);
  }
}
requestAnimationFrame(loop);
// 카드 n 의 time 초 장면 한 장(jpeg data URL). 시각을 안 주면 끝 모양(검사·대조용)
export function still(n, time) {
  const m = result(), fr = m?.res.frames.find(f => f.n === n); if (!fr) return null;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  draw(fr, time ?? PAUSE0 + fr.anims.length * MOVE + 0.01, m.color, cv);  // 마지막 멈춤 구간 = 이번 카드가 끝난 모습
  return cv.toDataURL("image/jpeg", 0.85);
}
window.Fold3D = Object.assign(window.Fold3D || {}, { still, ready: true, check: (program, ns) => run(program, ns).problems });

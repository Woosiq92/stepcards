// 3D 접기 카드: fold.js 가 계산한 면을 three.js 로 그리고, 카드마다 '이전 모양 → 이번 접기'를 되풀이해 보여 준다.
// 렌더러는 하나만 두고(브라우저 WebGL 개수 한도), 화면에 보이는 <canvas class="fold3d" data-n> 마다 그려서 옮겨 붙인다.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
import { run, bbox } from "./fold.js";

const W = 480, H = 360, LAYER = 0.006, PAUSE0 = 0.7, MOVE = 1.6, PAUSE1 = 1.2;
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setSize(W, H, false); renderer.setPixelRatio(1); renderer.setClearColor(0xf4f1ea, 1);  // 종이색 바탕(검사용 jpeg 도 같은 바탕)
const ink = new THREE.LineBasicMaterial({ color: 0x1c2b33 });
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
  const g = new THREE.Group(), mat = new THREE.MeshBasicMaterial({ color: 0x0866ff });
  g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.012, 6), mat));
  const tip = new THREE.Mesh(new THREE.ConeGeometry(0.04, 0.1, 12), mat);
  tip.position.copy(b); tip.lookAt(curve.getPoint(0.9)); tip.rotateX(-Math.PI / 2);
  g.add(tip); return g;
}

// 한 동작이 t(0~1)만큼 진행된 장면
function animGroup(an, t, color) {
  const g = new THREE.Group(), e = ease(t);
  if (an.kind === "fold") {
    const movedIds = new Set(an.moving.map(m => m.after.id));
    g.add(stateGroup(an.to, color, movedIds));
    const top = Math.max(...an.to.faces.map(f => f.layer)), rk = ranks(an.to.faces);
    const axisO = new THREE.Vector3(an.o[0], 0, an.o[1]), axisD = new THREE.Vector3(an.d[0], 0, an.d[1]).normalize();
    // 움직이는 쪽이 위로 들리는 회전 방향을 고른다(골접기는 위로, 산접기는 아래로 넘어간다)
    const probe = new THREE.Vector3(an.p[0], 0, an.p[1]).sub(axisO).applyAxisAngle(axisD, Math.PI / 2);
    const sign = (probe.y > 0 ? 1 : -1) * (an.valley ? 1 : -1);
    for (const m of an.moving) {
      const piece = faceMesh(m.before, rk(m.after) || top, color);
      const pivot = new THREE.Group(); pivot.position.copy(axisO);
      piece.position.x -= axisO.x; piece.position.z -= axisO.z; piece.position.y = (rk(m.after)) * LAYER;
      pivot.add(piece); pivot.setRotationFromAxisAngle(axisD, sign * Math.PI * e);
      g.add(pivot);
    }
    if (t < 0.15) g.add(arrow(an.p, an.q, (an.from.faces.length + 1) * LAYER + 0.01));
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
function loop(now) {
  requestAnimationFrame(loop);
  if (now - last < 33) return; last = now;
  const m = result(); if (!m) return;
  for (const cv of document.querySelectorAll("canvas.fold3d")) {
    const r = cv.getBoundingClientRect();
    if (!r.width || r.bottom < 0 || r.top > innerHeight) continue;
    const fr = m.res.frames.find(f => f.n === +cv.dataset.n);
    if (fr) draw(fr, (now - (+cv.dataset.t0 || 0)) / 1000, m.color, cv);
  }
}
requestAnimationFrame(loop);
// 끝 모양 한 장(검사용): 카드 n 이 끝난 뒤의 모습을 jpeg data URL 로
export function still(n) {
  const m = result(), fr = m?.res.frames.find(f => f.n === n); if (!fr) return null;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  draw(fr, PAUSE0 + fr.anims.length * MOVE + 0.01, m.color, cv);  // 마지막 멈춤 구간 = 이번 카드가 끝난 모습
  return cv.toDataURL("image/jpeg", 0.85);
}
window.Fold3D = Object.assign(window.Fold3D || {}, { still, ready: true, check: (program, ns) => run(program, ns).problems });

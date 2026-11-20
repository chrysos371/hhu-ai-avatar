import * as THREE from 'three';
import { avatarPose, type AvatarPoseInput } from './avatarPose';

export type RendererStatus = 'loading' | 'ready' | 'fallback' | 'lost';
export type AvatarRig = { present: (input: AvatarPoseInput) => void; dispose: () => void };

/** Project-owned procedural character. No fetched model, textures, or face data. */
export function createAvatarRig(host: HTMLElement, initial: AvatarPoseInput,
  onStatus: (status: RendererStatus) => void): AvatarRig {
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setClearColor(0x0b1625, 0);
  renderer.setPixelRatio(Math.min(2, Math.max(1, window.devicePixelRatio || 1)));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.setAttribute('aria-hidden', 'true');
  canvas.style.width = canvas.style.height = '100%';
  canvas.style.display = 'block';
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1.8, 1.8, 1.8, -1.8, .1, 30);
  camera.position.set(0, 0, 7);
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const sphere = new THREE.SphereGeometry(1, 32, 24); geometries.add(sphere);
  function material(color: number) {
    const value = new THREE.MeshLambertMaterial({ color }); materials.add(value); return value;
  }
  const skin = material(0xf3d3bd), hair = material(0x243b52), jacket = material(0x426e88);
  const shirt = material(0xb0d8df), white = material(0xf0f5f6), iris = material(0x243b52);
  const mouthMaterial = material(0x824c51), accent = material(0x78bdcd);
  const root = new THREE.Group(), head = new THREE.Group();
  scene.add(root); root.add(head);
  function ellipsoid(parent: THREE.Group, paint: THREE.Material,
    position: [number, number, number], scale: [number, number, number]) {
    const mesh = new THREE.Mesh(sphere, paint); mesh.position.set(...position); mesh.scale.set(...scale);
    parent.add(mesh); return mesh;
  }
  ellipsoid(root, jacket, [0, -1.18, -.03], [.69, .68, .34]);
  ellipsoid(root, shirt, [0, -1.12, .07], [.36, .56, .35]);
  for (const side of [-1, 1]) {
    ellipsoid(root, jacket, [side * .70, -1.2, -.03], [.22, .55, .25]);
    const collar = ellipsoid(root, white, [side * .17, -.83, .35], [.13, .27, .045]);
    collar.rotation.z = side * .42;
    ellipsoid(head, skin, [side * .82, .37, 0], [.13, .20, .12]);
  }
  ellipsoid(root, accent, [0, -1.14, .43], [.095, .12, .035]);
  ellipsoid(root, skin, [0, -.64, 0], [.22, .24, .20]);
  ellipsoid(head, hair, [0, .42, -.18], [.91, 1.01, .61]);
  ellipsoid(head, skin, [0, .35, 0], [.83, .93, .62]);
  const cap = new THREE.SphereGeometry(1, 32, 20, 0, Math.PI * 2, 0, Math.PI / 2.3); geometries.add(cap);
  const hairCap = new THREE.Mesh(cap, hair); hairCap.position.set(0, .40, -.05);
  hairCap.scale.set(.93, 1.0, .69); head.add(hairCap);
  const bang = ellipsoid(head, hair, [-.26, 1.04, .47], [.48, .16, .19]); bang.rotation.z = -.35;
  ellipsoid(head, skin, [0, .28, .625], [.075, .09, .08]);
  const eyes: THREE.Mesh[] = [], pupils: THREE.Mesh[] = [], brows: THREE.Mesh[] = [];
  for (const side of [-1, 1]) {
    eyes.push(ellipsoid(head, white, [side * .30, .46, .608], [.13, .17, .035]));
    pupils.push(ellipsoid(head, iris, [side * .30, .45, .644], [.06, .095, .025]));
    ellipsoid(head, white, [side * .30 - .018, .48, .668], [.018, .024, .009]);
    brows.push(ellipsoid(head, hair, [side * .30, .70, .57], [.15, .025, .025]));
  }
  const mouth = ellipsoid(head, mouthMaterial, [0, .015, .605], [.19, .018, .025]);
  scene.add(new THREE.HemisphereLight(0xe5f6ff, 0x243b52, 2.2));
  const key = new THREE.DirectionalLight(0xffeee0, 2.4); key.position.set(-3, 4, 6); scene.add(key);
  const rim = new THREE.DirectionalLight(0x78bdcd, 1.1); rim.position.set(3, 1, -2); scene.add(rim);
  let disposed = false, lost = false, current = initial;
  let observer: ResizeObserver | null = null;
  function present(input: AvatarPoseInput) {
    current = input;
    if (disposed || lost) return;
    const pose = avatarPose(input);
    mouth.scale.set(pose.mouthWidth, pose.mouthHeight, .025);
    head.rotation.z = pose.headRoll;
    eyes.forEach(eye => { eye.scale.y = .17 * pose.eyeHeight; });
    pupils.forEach(pupil => { pupil.scale.y = .095 * pose.eyeHeight; });
    brows.forEach((brow, index) => {
      brow.rotation.z = (index === 0 ? 1 : -1) * pose.browTilt;
      brow.position.y = .70 + pose.browLift;
    });
    try {
      renderer.render(scene, camera);
      canvas.dataset.renderCount = String(renderer.info.render.frame);
      canvas.dataset.mediaTime = String(pose.mediaTime);
      canvas.dataset.mouthOpen = pose.open.toFixed(3);
      canvas.dataset.mouthHeight = pose.mouthHeight.toFixed(4);
    } catch {
      lost = true; onStatus('fallback');
    }
  }
  function resize() {
    if (disposed) return;
    const width = Math.max(1, Math.min(4096, host.clientWidth || 240));
    const height = Math.max(1, Math.min(4096, host.clientHeight || 208));
    camera.left = -1.8 * width / height; camera.right = -camera.left; camera.updateProjectionMatrix();
    renderer.setSize(width, height, false); present(current);
  }
  function contextLost(event: Event) {
    event.preventDefault(); lost = true;
    if (!disposed) onStatus('lost');
  }
  function contextRestored() {
    if (disposed) return;
    lost = false; present(current); if (!lost) onStatus('ready');
  }
  function dispose() {
    if (disposed) return;
    disposed = true; observer?.disconnect(); window.removeEventListener('resize', resize);
    canvas.removeEventListener('webglcontextlost', contextLost);
    canvas.removeEventListener('webglcontextrestored', contextRestored);
    geometries.forEach(geometry => geometry.dispose()); materials.forEach(paint => paint.dispose());
    renderer.dispose(); renderer.forceContextLoss(); canvas.dataset.disposed = 'true';
    canvas.remove();
  }
  try {
    host.appendChild(canvas);
    canvas.addEventListener('webglcontextlost', contextLost);
    canvas.addEventListener('webglcontextrestored', contextRestored);
    if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(host); }
    else window.addEventListener('resize', resize);
    resize(); if (!lost) onStatus('ready');
    return { present, dispose };
  } catch (error) { dispose(); throw error; }
}

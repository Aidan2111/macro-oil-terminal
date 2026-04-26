"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { hasWebGPU as hasWebGPUSync } from "@/lib/has-webgpu";
import type {
  Vector3 as TVector3,
  Line as TLine,
  Material as TMaterial,
  BufferGeometry as TBufferGeometry,
  Texture as TTexture,
} from "three";
import type { Vessel, FlagCategory } from "./types";
import { CATEGORY_COLORS } from "./types";
import {
  latLonToCartesian,
  greatCirclePoints,
  solarUnitVector,
} from "@/lib/globe-physics";
import { GlobeSilhouette } from "@/components/illustrations/GlobeSilhouette";

type Props = {
  vessels: Vessel[];
  visibleCategories: Set<FlagCategory>;
  onVesselClick: (v: Vessel | null) => void;
  /** Optional — when provided, the globe draws a faint trail per mmsi. */
  trails?: Record<string, Array<[number, number]>>;
  /** Test-only override; when set, forces the fallback branch. */
  forceFallback?: boolean;
};

/**
 * WebGPU / TSL fleet globe. Ported from webgpu_components.py in the
 * Streamlit app — same earth textures, same colour graph, same
 * category palette. In jsdom / non-WebGPU browsers we render a static
 * placeholder so the component stays mountable in tests.
 */
export function FleetGlobe({
  vessels,
  visibleCategories,
  onVesselClick,
  trails,
  forceFallback,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState<"checking" | "ok" | "fallback">("checking");

  // Only touch `navigator.gpu` on the client; SSR-safe via the
  // shared helper.
  const hasWebGPU = useMemo(() => hasWebGPUSync(), []);

  useEffect(() => {
    if (forceFallback) {
      setReady("fallback");
      return;
    }
    if (typeof window === "undefined" || typeof navigator === "undefined") {
      setReady("fallback");
      return;
    }

    let disposed = false;
    let cleanup: (() => void) | undefined;

    (async () => {
      try {
        if (!canvasRef.current) return;
        if (hasWebGPU) {
          cleanup = await bootWebGPU({
            canvas: canvasRef.current,
            vessels,
            visibleCategories,
            onVesselClick,
            trails,
          });
        } else {
          cleanup = await bootWebGL({
            canvas: canvasRef.current,
            vessels,
            visibleCategories,
            onVesselClick,
            trails,
          });
        }
        if (!disposed) setReady("ok");
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("[FleetGlobe] boot failed, falling back", err);
        if (!disposed) setReady("fallback");
      }
    })();

    return () => {
      disposed = true;
      cleanup?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceFallback, hasWebGPU]);

  // When data changes after boot, push updates through the ref-held API
  // attached to the canvas element by the boot function.
  useEffect(() => {
    const api = (canvasRef.current as unknown as { __globeApi?: GlobeApi } | null)
      ?.__globeApi;
    if (!api) return;
    api.updateVessels(vessels, visibleCategories);
    if (trails) api.updateTrails(trails);
  }, [vessels, visibleCategories, trails]);

  // SSR + jsdom fallback — never attempts to touch WebGPU.
  if (ready === "fallback" || (!hasWebGPU && ready === "checking")) {
    return (
      <div
        data-testid="fleet-globe-fallback"
        className="relative flex h-full min-h-[480px] w-full items-center justify-center overflow-hidden rounded-lg border border-border bg-bg-2 text-sm text-text-secondary"
        ref={containerRef}
      >
        <div className="flex flex-col items-center gap-3 text-center px-6">
          <GlobeSilhouette className="text-text-muted" size={104} />
          <div className="font-medium text-text-primary">
            {typeof navigator !== "undefined" && !hasWebGPU
              ? "Your browser does not support 3D fleet view"
              : "Preparing 3D fleet view"}
          </div>
          <div className="max-w-sm text-xs text-text-muted">
            {typeof navigator !== "undefined" && !hasWebGPU
              ? "Open this page in Chrome or Edge (version 113 or newer) to see the live globe."
              : "First paint in progress — the globe loads after WebGPU initialises."}
          </div>
          <div className="text-xs text-text-muted">
            {vessels.length} vessel{vessels.length === 1 ? "" : "s"} staged
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative h-full min-h-[480px] w-full overflow-hidden rounded-lg border border-border bg-bg-1"
    >
      <canvas
        ref={canvasRef}
        aria-label="Interactive 3D vessel tracking globe"
        className="block h-full w-full"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Globe API — shared between WebGPU + WebGL paths so the React layer can
// push updates without caring which renderer is behind it.
// ---------------------------------------------------------------------------

type GlobeApi = {
  updateVessels: (vessels: Vessel[], visible: Set<FlagCategory>) => void;
  updateTrails: (trails: Record<string, Array<[number, number]>>) => void;
};

type BootArgs = {
  canvas: HTMLCanvasElement;
  vessels: Vessel[];
  visibleCategories: Set<FlagCategory>;
  onVesselClick: (v: Vessel | null) => void;
  trails?: Record<string, Array<[number, number]>>;
};

// NASA Blue Marble textures — CC, distributed as three.js example assets
const EARTH_DAY = "https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg";
const EARTH_NIGHT = "https://threejs.org/examples/textures/planets/earth_lights_2048.png";

const MAX_INSTANCES = 2000;

async function bootWebGPU({
  canvas,
  vessels,
  visibleCategories,
  onVesselClick,
  trails,
}: BootArgs): Promise<() => void> {
  const THREE = await import("three");
  const { WebGPURenderer, MeshBasicNodeMaterial } = await import("three/webgpu");
  const TSL = await import("three/tsl");
  const { OrbitControls } = await import("three/addons/controls/OrbitControls.js");

  const {
    color,
    mix,
    dot,
    normalize,
    positionWorld,
    normalLocal,
    timerLocal,
    mx_fractal_noise_float,
    uniform,
    texture: texNode,
    uv,
    float,
    smoothstep,
    clamp,
    pow,
    cameraPosition,
    vec3,
  } = TSL as typeof import("three/tsl") & {
    // Some TSL helpers aren't in the exported .d.ts yet
    [k: string]: unknown;
  };

  // --- Scene
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
  camera.position.set(0, 0.6, 3.2);

  const renderer = new WebGPURenderer({ canvas, antialias: true, alpha: true });
  await renderer.init();
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
  renderer.setSize(canvas.clientWidth || 600, canvas.clientHeight || 480, false);
  renderer.setClearColor(new THREE.Color(0x000000), 0);

  // --- Textures
  const texLoader = new THREE.TextureLoader();
  texLoader.setCrossOrigin("anonymous");
  const load = (url: string) =>
    new Promise<TTexture | null>((resolve) => {
      texLoader.load(url, (t) => resolve(t), undefined, () => resolve(null));
    });
  const [dayTex, nightTex] = await Promise.all([load(EARTH_DAY), load(EARTH_NIGHT)]);

  // --- Earth
  const earthGeo = new THREE.SphereGeometry(1, 64, 64);
  const sunUnif = uniform(
    new THREE.Vector3().fromArray(solarUnitVector(new Date())),
  );

  const earthMat = new MeshBasicNodeMaterial();
  if (dayTex && nightTex) {
    const sampleDay = texNode(dayTex, uv());
    const sampleNight = texNode(nightTex, uv());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const lambert = dot(normalLocal, (sunUnif as unknown) as any);
    const dayW = clamp(lambert, float(0), float(1));
    const nightW = clamp(lambert.negate(), float(0), float(1));
    earthMat.colorNode = sampleDay.mul(dayW).add(sampleNight.mul(nightW));
  } else if (dayTex) {
    earthMat.colorNode = texNode(dayTex, uv());
  } else {
    earthMat.colorNode = color("#1b3550");
  }
  const earth = new THREE.Mesh(earthGeo, earthMat);
  scene.add(earth);

  // --- Atmosphere rim
  const atmoGeo = new THREE.SphereGeometry(1.015, 64, 64);
  const atmoMat = new MeshBasicNodeMaterial();
  atmoMat.side = THREE.BackSide;
  atmoMat.transparent = true;
  atmoMat.blending = THREE.AdditiveBlending;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewDir = normalize((cameraPosition as any).sub(positionWorld as any));
  const rim = pow(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    float(1).sub(dot(normalLocal, viewDir as any) as any),
    float(3),
  ).mul(float(0.4));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  atmoMat.colorNode = color("#22d3ee").mul(rim as any);
  const atmo = new THREE.Mesh(atmoGeo, atmoMat);
  scene.add(atmo);

  // --- Instanced vessels
  const dotGeo = new THREE.IcosahedronGeometry(0.005, 0);
  const dotMat = new MeshBasicNodeMaterial();
  (dotMat as unknown as { vertexColors: boolean }).vertexColors = true;
  const instanced = new THREE.InstancedMesh(dotGeo, dotMat, MAX_INSTANCES);
  instanced.count = 0;
  instanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  const colorAttr = new THREE.InstancedBufferAttribute(
    new Float32Array(MAX_INSTANCES * 3),
    3,
  );
  instanced.instanceColor = colorAttr;
  scene.add(instanced);

  // --- Trails container (plain group, re-populated on updateTrails)
  const trailGroup = new THREE.Group();
  scene.add(trailGroup);

  // --- Lighting / controls / resize / raycast — shared with WebGL path below
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minDistance = 1.5;
  controls.maxDistance = 6;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 0.5;

  // --- Auto-rotate after 10s idle
  let lastInteraction = performance.now();
  const bumpInteraction = () => {
    lastInteraction = performance.now();
    controls.autoRotate = false;
  };
  canvas.addEventListener("pointerdown", bumpInteraction);
  canvas.addEventListener("wheel", bumpInteraction, { passive: true });

  // --- Raycaster for click-to-inspect
  const raycaster = new THREE.Raycaster();
  const mouseNdc = new THREE.Vector2();
  let pressedAt = 0;
  let pressedX = 0;
  let pressedY = 0;
  const vesselsByIndex: Vessel[] = [];
  canvas.addEventListener("pointerdown", (e) => {
    pressedAt = performance.now();
    pressedX = e.clientX;
    pressedY = e.clientY;
  });
  canvas.addEventListener("pointerup", (e) => {
    // Only treat as click if released within 300ms and within 5px
    const dt = performance.now() - pressedAt;
    const dx = Math.abs(e.clientX - pressedX);
    const dy = Math.abs(e.clientY - pressedY);
    if (dt > 300 || dx > 5 || dy > 5) return;
    const rect = canvas.getBoundingClientRect();
    mouseNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouseNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouseNdc, camera);
    raycaster.params.Mesh = { threshold: 0.01 };
    const hits = raycaster.intersectObject(instanced, false);
    if (hits.length) {
      const id = hits[0].instanceId;
      if (typeof id === "number" && vesselsByIndex[id]) {
        onVesselClick(vesselsByIndex[id]);
      }
    }
  });

  // --- Resize observer
  const ro = new ResizeObserver(() => {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  });
  ro.observe(canvas);

  // --- Populate initial vessels
  const dummy = new THREE.Object3D();
  const colorTmp = new THREE.Color();
  const targetPositions: TVector3[] = [];
  const currentPositions: TVector3[] = [];
  let lerpStart = 0;
  let lerpDuration = 600;

  function writeInstances(list: Vessel[], visible: Set<FlagCategory>) {
    vesselsByIndex.length = 0;
    const n = Math.min(list.length, MAX_INSTANCES);
    targetPositions.length = n;
    while (currentPositions.length < n) currentPositions.push(new THREE.Vector3());
    for (let i = 0; i < n; i++) {
      const v = list[i];
      vesselsByIndex[i] = v;
      const [x, y, z] = latLonToCartesian(v.lat, v.lon, 1.01);
      targetPositions[i] = new THREE.Vector3(x, y, z);
      if (currentPositions[i].lengthSq() === 0) currentPositions[i].set(x, y, z);
      colorTmp.set(CATEGORY_COLORS[v.flag_category]);
      const alpha = visible.has(v.flag_category) ? 1 : 0;
      colorAttr.setXYZ(i, colorTmp.r * alpha, colorTmp.g * alpha, colorTmp.b * alpha);
    }
    instanced.count = n;
    colorAttr.needsUpdate = true;
    lerpStart = performance.now();
    lerpDuration = 600;
  }

  function writeTrails(tr: Record<string, Array<[number, number]>>) {
    // wipe existing
    while (trailGroup.children.length) {
      const c = trailGroup.children.pop()!;
      (c as TLine).geometry?.dispose?.();
      ((c as TLine).material as TMaterial | undefined)?.dispose?.();
    }
    for (const mmsi of Object.keys(tr)) {
      const pts = tr[mmsi];
      if (pts.length < 2) continue;
      const positions: number[] = [];
      const colors: number[] = [];
      const base = CATEGORY_COLORS[
        (vessels.find((v) => v.mmsi === mmsi)?.flag_category || "other") as FlagCategory
      ];
      const c = new THREE.Color(base);
      for (let i = 0; i < pts.length - 1; i++) {
        const seg = greatCirclePoints(
          pts[i][0],
          pts[i][1],
          pts[i + 1][0],
          pts[i + 1][1],
          6,
        );
        for (let s = 0; s < seg.length - 1; s++) {
          const [x1, y1, z1] = latLonToCartesian(seg[s][0], seg[s][1], 1.012);
          const [x2, y2, z2] = latLonToCartesian(seg[s + 1][0], seg[s + 1][1], 1.012);
          positions.push(x1, y1, z1, x2, y2, z2);
          // fade older (lower i) to faint, newer to bright
          const a = (i + s / seg.length) / Math.max(1, pts.length - 1);
          colors.push(c.r * a, c.g * a, c.b * a, c.r * a, c.g * a, c.b * a);
        }
      }
      const geom = new THREE.BufferGeometry();
      geom.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(positions, 3),
      );
      geom.setAttribute(
        "color",
        new THREE.Float32BufferAttribute(colors, 3),
      );
      const mat = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.6,
      });
      trailGroup.add(new THREE.LineSegments(geom, mat));
    }
  }

  writeInstances(vessels, visibleCategories);
  if (trails) writeTrails(trails);

  (canvas as unknown as { __globeApi: GlobeApi }).__globeApi = {
    updateVessels: (list, visible) => writeInstances(list, visible),
    updateTrails: (tr) => writeTrails(tr),
  };

  // --- Animation loop
  let raf = 0;
  const tick = () => {
    raf = requestAnimationFrame(tick);
    // auto-rotate after idle
    if (performance.now() - lastInteraction > 10_000) {
      controls.autoRotate = true;
    }
    controls.update();

    // Smooth lerp on position updates
    if (targetPositions.length) {
      const t = Math.min(1, (performance.now() - lerpStart) / lerpDuration);
      for (let i = 0; i < targetPositions.length; i++) {
        const curr = currentPositions[i];
        const tgt = targetPositions[i];
        curr.x = THREE.MathUtils.lerp(curr.x, tgt.x, t);
        curr.y = THREE.MathUtils.lerp(curr.y, tgt.y, t);
        curr.z = THREE.MathUtils.lerp(curr.z, tgt.z, t);
        dummy.position.copy(curr);
        dummy.scale.setScalar(1);
        dummy.updateMatrix();
        instanced.setMatrixAt(i, dummy.matrix);
      }
      instanced.instanceMatrix.needsUpdate = true;
    }

    // Refresh sun direction every second — slow enough to not dominate CPU
    (sunUnif as unknown as { value: TVector3 }).value.fromArray(
      solarUnitVector(new Date()),
    );

    renderer.renderAsync(scene, camera).catch(() => {});
  };
  raf = requestAnimationFrame(tick);

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect();
    controls.dispose();
    earthGeo.dispose();
    earthMat.dispose();
    atmoGeo.dispose();
    atmoMat.dispose();
    dotGeo.dispose();
    dotMat.dispose();
    dayTex?.dispose();
    nightTex?.dispose();
    while (trailGroup.children.length) {
      const c = trailGroup.children.pop()!;
      (c as TLine).geometry?.dispose?.();
      ((c as TLine).material as TMaterial | undefined)?.dispose?.();
    }
    renderer.dispose();
  };
}

async function bootWebGL({
  canvas,
  vessels,
  visibleCategories,
  onVesselClick,
  trails,
}: BootArgs): Promise<() => void> {
  const THREE = await import("three");
  const { OrbitControls } = await import("three/addons/controls/OrbitControls.js");

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
  camera.position.set(0, 0.6, 3.2);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
  renderer.setSize(canvas.clientWidth || 600, canvas.clientHeight || 480, false);
  renderer.setClearColor(0x000000, 0);

  const texLoader = new THREE.TextureLoader();
  texLoader.setCrossOrigin("anonymous");
  const dayTex = await new Promise<TTexture | null>((res) =>
    texLoader.load(EARTH_DAY, (t) => res(t), undefined, () => res(null)),
  );

  const earth = new THREE.Mesh(
    new THREE.SphereGeometry(1, 64, 64),
    new THREE.MeshStandardMaterial({
      map: dayTex ?? null,
      color: dayTex ? 0xffffff : 0x1b3550,
      roughness: 0.9,
      metalness: 0.05,
    }),
  );
  scene.add(earth);

  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const sun = new THREE.DirectionalLight(0xffffff, 1.1);
  const s = solarUnitVector(new Date());
  sun.position.set(s[0] * 3, s[1] * 3, s[2] * 3);
  scene.add(sun);

  const dotGeo = new THREE.IcosahedronGeometry(0.005, 0);
  const dotMat = new THREE.MeshBasicMaterial({ vertexColors: true });
  const instanced = new THREE.InstancedMesh(dotGeo, dotMat, MAX_INSTANCES);
  instanced.count = 0;
  instanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  const colorAttr = new THREE.InstancedBufferAttribute(
    new Float32Array(MAX_INSTANCES * 3),
    3,
  );
  instanced.instanceColor = colorAttr;
  scene.add(instanced);

  const trailGroup = new THREE.Group();
  scene.add(trailGroup);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minDistance = 1.5;
  controls.maxDistance = 6;
  controls.autoRotateSpeed = 0.5;

  let lastInteraction = performance.now();
  const bump = () => {
    lastInteraction = performance.now();
    controls.autoRotate = false;
  };
  canvas.addEventListener("pointerdown", bump);
  canvas.addEventListener("wheel", bump, { passive: true });

  const raycaster = new THREE.Raycaster();
  const mouseNdc = new THREE.Vector2();
  const vesselsByIndex: Vessel[] = [];
  let pressedAt = 0;
  let pressedX = 0;
  let pressedY = 0;
  canvas.addEventListener("pointerdown", (e) => {
    pressedAt = performance.now();
    pressedX = e.clientX;
    pressedY = e.clientY;
  });
  canvas.addEventListener("pointerup", (e) => {
    const dt = performance.now() - pressedAt;
    if (dt > 300) return;
    if (Math.abs(e.clientX - pressedX) > 5) return;
    if (Math.abs(e.clientY - pressedY) > 5) return;
    const rect = canvas.getBoundingClientRect();
    mouseNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouseNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouseNdc, camera);
    const hits = raycaster.intersectObject(instanced, false);
    if (hits.length) {
      const id = hits[0].instanceId;
      if (typeof id === "number" && vesselsByIndex[id]) {
        onVesselClick(vesselsByIndex[id]);
      }
    }
  });

  const ro = new ResizeObserver(() => {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  });
  ro.observe(canvas);

  const dummy = new THREE.Object3D();
  const colorTmp = new THREE.Color();
  const targetPositions: TVector3[] = [];
  const currentPositions: TVector3[] = [];
  let lerpStart = 0;

  function writeInstances(list: Vessel[], visible: Set<FlagCategory>) {
    vesselsByIndex.length = 0;
    const n = Math.min(list.length, MAX_INSTANCES);
    targetPositions.length = n;
    while (currentPositions.length < n) currentPositions.push(new THREE.Vector3());
    for (let i = 0; i < n; i++) {
      const v = list[i];
      vesselsByIndex[i] = v;
      const [x, y, z] = latLonToCartesian(v.lat, v.lon, 1.01);
      targetPositions[i] = new THREE.Vector3(x, y, z);
      if (currentPositions[i].lengthSq() === 0) currentPositions[i].set(x, y, z);
      colorTmp.set(CATEGORY_COLORS[v.flag_category]);
      const alpha = visible.has(v.flag_category) ? 1 : 0;
      colorAttr.setXYZ(i, colorTmp.r * alpha, colorTmp.g * alpha, colorTmp.b * alpha);
    }
    instanced.count = n;
    colorAttr.needsUpdate = true;
    lerpStart = performance.now();
  }

  function writeTrails(tr: Record<string, Array<[number, number]>>) {
    while (trailGroup.children.length) {
      const c = trailGroup.children.pop()!;
      (c as TLine).geometry?.dispose?.();
      ((c as TLine).material as TMaterial | undefined)?.dispose?.();
    }
    for (const mmsi of Object.keys(tr)) {
      const pts = tr[mmsi];
      if (pts.length < 2) continue;
      const positions: number[] = [];
      for (let i = 0; i < pts.length - 1; i++) {
        const seg = greatCirclePoints(
          pts[i][0],
          pts[i][1],
          pts[i + 1][0],
          pts[i + 1][1],
          6,
        );
        for (let s = 0; s < seg.length - 1; s++) {
          const [x1, y1, z1] = latLonToCartesian(seg[s][0], seg[s][1], 1.012);
          const [x2, y2, z2] = latLonToCartesian(seg[s + 1][0], seg[s + 1][1], 1.012);
          positions.push(x1, y1, z1, x2, y2, z2);
        }
      }
      const geom = new THREE.BufferGeometry();
      geom.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(positions, 3),
      );
      const base = CATEGORY_COLORS[
        (vessels.find((v) => v.mmsi === mmsi)?.flag_category || "other") as FlagCategory
      ];
      const mat = new THREE.LineBasicMaterial({
        color: base,
        transparent: true,
        opacity: 0.4,
      });
      trailGroup.add(new THREE.LineSegments(geom, mat));
    }
  }

  writeInstances(vessels, visibleCategories);
  if (trails) writeTrails(trails);

  (canvas as unknown as { __globeApi: GlobeApi }).__globeApi = {
    updateVessels: writeInstances,
    updateTrails: writeTrails,
  };

  let raf = 0;
  const tick = () => {
    raf = requestAnimationFrame(tick);
    if (performance.now() - lastInteraction > 10_000) {
      controls.autoRotate = true;
    }
    controls.update();
    if (targetPositions.length) {
      const t = Math.min(1, (performance.now() - lerpStart) / 600);
      for (let i = 0; i < targetPositions.length; i++) {
        const curr = currentPositions[i];
        const tgt = targetPositions[i];
        curr.x = THREE.MathUtils.lerp(curr.x, tgt.x, t);
        curr.y = THREE.MathUtils.lerp(curr.y, tgt.y, t);
        curr.z = THREE.MathUtils.lerp(curr.z, tgt.z, t);
        dummy.position.copy(curr);
        dummy.updateMatrix();
        instanced.setMatrixAt(i, dummy.matrix);
      }
      instanced.instanceMatrix.needsUpdate = true;
    }
    renderer.render(scene, camera);
  };
  raf = requestAnimationFrame(tick);

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect();
    controls.dispose();
    (earth.geometry as TBufferGeometry).dispose();
    (earth.material as TMaterial).dispose();
    dotGeo.dispose();
    dotMat.dispose();
    dayTex?.dispose();
    while (trailGroup.children.length) {
      const c = trailGroup.children.pop()!;
      (c as TLine).geometry?.dispose?.();
      ((c as TLine).material as TMaterial | undefined)?.dispose?.();
    }
    renderer.dispose();
  };
}

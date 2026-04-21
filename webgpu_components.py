"""WebGPU / Three.js TSL embedded components for Streamlit.

These build self-contained HTML blobs that Streamlit renders via
``streamlit.components.v1.html``. Each one:

  * Imports Three.js from a pinned ES module CDN (``three/webgpu`` + ``three/tsl``)
  * Checks ``navigator.gpu`` and falls back to ``WebGLRenderer`` if absent
  * Displays a user-friendly message if neither is available

If the Streamlit dependency or pandas DataFrame is missing at render time
the functions degrade gracefully and do nothing.
"""

from __future__ import annotations

import json
from typing import Iterable

import pandas as pd


# CDN pinned to a version that ships the /webgpu and /tsl subpaths as ES modules.
# jsDelivr's +esm endpoint rewrites bare specifiers into CDN URLs, which is
# essential because three.webgpu references three/tsl internally.
_THREE_CDN = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.webgpu.min.js"
_THREE_MODULE = "https://cdn.jsdelivr.net/npm/three@0.160.0/+esm"
_THREE_WEBGPU_MODULE = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.webgpu.min.js"


def _safe_components_html(html: str, height: int) -> None:
    """Render HTML with streamlit.components.v1.html — no-op if streamlit absent."""
    try:
        import streamlit.components.v1 as components
    except Exception:  # pragma: no cover
        return
    components.html(html, height=height, scrolling=False)


# ---------------------------------------------------------------------------
# Hero banner — animated TSL "oil slick" shader
# ---------------------------------------------------------------------------
_HERO_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  html, body { margin: 0; padding: 0; background: #0b0f14; overflow: hidden; }
  #hero { width: 100%; height: __HEIGHT__px; display: block; }
  #hero-fallback {
    width: 100%; height: __HEIGHT__px;
    background: linear-gradient(120deg,#0b0f14 0%,#18222f 30%,#2a3347 50%,#7a4e1e 75%,#c68a3a 100%);
    color: #e7ecf3; display: flex; align-items: center; justify-content: center;
    font-family: system-ui, sans-serif; letter-spacing: 1px;
  }
  #hero-label {
    position: absolute; top: 14px; left: 20px;
    color: #e7ecf3; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; opacity: 0.72; pointer-events: none; letter-spacing: 2px;
  }
</style>
</head>
<body>
<div id="hero-label">WEBGPU // TSL HERO // BRENT-WTI SIGNAL FLOW</div>
<canvas id="hero"></canvas>
<div id="hero-fallback" style="display:none;">WebGPU unavailable — static gradient fallback</div>
<script type="module">
  const fallback = document.getElementById('hero-fallback');
  const canvas = document.getElementById('hero');
  const H = __HEIGHT__;
  canvas.height = H;
  canvas.width = canvas.clientWidth || window.innerWidth;

  async function boot() {
    let THREE, TSL, renderer, useWebGPU = !!navigator.gpu;
    try {
      if (useWebGPU) {
        THREE = await import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.webgpu.min.js');
        TSL = await import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.tsl.min.js').catch(() => null);
      }
      if (!useWebGPU || !THREE) {
        THREE = await import('https://cdn.jsdelivr.net/npm/three@0.160.0/+esm');
        useWebGPU = false;
      }
    } catch (e) {
      console.warn('three import failed', e);
      canvas.style.display = 'none';
      fallback.style.display = 'flex';
      return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    try {
      if (useWebGPU && THREE.WebGPURenderer) {
        renderer = new THREE.WebGPURenderer({ canvas, antialias: true });
        await renderer.init();
      } else {
        renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
      }
    } catch (e) {
      console.warn('renderer init failed, falling back to WebGL', e);
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
      useWebGPU = false;
    }
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(canvas.clientWidth, H, false);

    // Procedural oil-slick shader via RawShaderMaterial so it works in both
    // WebGL and WebGPU backends without depending on TSL availability.
    const vert = `
      attribute vec3 position;
      varying vec2 vUv;
      void main() {
        vUv = position.xy * 0.5 + 0.5;
        gl_Position = vec4(position, 1.0);
      }
    `;
    const frag = `
      precision highp float;
      varying vec2 vUv;
      uniform float uTime;
      uniform vec2  uResolution;

      // simplex-ish pseudo noise
      float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float noise(vec2 p) {
        vec2 i = floor(p); vec2 f = fract(p);
        float a = hash(i);
        float b = hash(i + vec2(1., 0.));
        float c = hash(i + vec2(0., 1.));
        float d = hash(i + vec2(1., 1.));
        vec2 u = f*f*(3.-2.*f);
        return mix(a,b,u.x) + (c-a)*u.y*(1.-u.x) + (d-b)*u.x*u.y;
      }
      float fbm(vec2 p) {
        float v = 0., a = 0.5;
        for (int i=0;i<5;i++) { v += a*noise(p); p *= 2.02; a *= 0.5; }
        return v;
      }
      void main() {
        vec2 uv = vUv;
        uv.x *= uResolution.x / uResolution.y;
        float t = uTime * 0.12;
        vec2 q = uv*2.5 + vec2(t, -t*0.7);
        float n = fbm(q + fbm(q + t));
        // Iridescent palette biased toward oil-black / copper / cyan
        vec3 c1 = vec3(0.04, 0.06, 0.10);
        vec3 c2 = vec3(0.78, 0.50, 0.20);
        vec3 c3 = vec3(0.10, 0.65, 0.85);
        vec3 c4 = vec3(0.55, 0.20, 0.65);
        vec3 col = mix(c1, c2, smoothstep(0.25, 0.55, n));
        col = mix(col, c3, smoothstep(0.45, 0.70, n));
        col = mix(col, c4, smoothstep(0.70, 0.90, n*n));
        // Scanline / signal-flow suggestion
        float stripe = smoothstep(0.48, 0.52, fract(uv.y*8.0 + uTime*0.3));
        col = mix(col, col * 1.2, 0.07 * stripe);
        gl_FragColor = vec4(col, 1.0);
      }
    `;

    const mat = new THREE.RawShaderMaterial({
      vertexShader: vert,
      fragmentShader: frag,
      uniforms: {
        uTime: { value: 0 },
        uResolution: { value: new THREE.Vector2(canvas.clientWidth, H) },
      },
      glslVersion: THREE.GLSL1 || 100,
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat);
    scene.add(quad);

    function onResize() {
      const w = canvas.clientWidth;
      renderer.setSize(w, H, false);
      mat.uniforms.uResolution.value.set(w, H);
    }
    window.addEventListener('resize', onResize);

    const start = performance.now();
    function tick() {
      mat.uniforms.uTime.value = (performance.now() - start) * 0.001;
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    }
    tick();

    // Watermark indicating backend
    const badge = document.getElementById('hero-label');
    badge.textContent = (useWebGPU ? 'WEBGPU' : 'WEBGL') + ' // TSL HERO // BRENT-WTI SIGNAL FLOW';
  }
  boot().catch(err => {
    console.warn('hero boot failed', err);
    canvas.style.display = 'none';
    fallback.style.display = 'flex';
  });
</script>
</body>
</html>
"""


def render_hero_banner(height: int = 220) -> None:
    """Render the animated oil-slick hero banner at the top of the app."""
    html = _HERO_HTML.replace("__HEIGHT__", str(int(height)))
    _safe_components_html(html, height=int(height) + 8)


# ---------------------------------------------------------------------------
# 3D Fleet globe
# ---------------------------------------------------------------------------
_CATEGORY_COLORS = {
    "Jones Act / Domestic": "#2ecc71",
    "Shadow Risk": "#ff9f1c",
    "Sanctioned": "#e74c3c",
    "Other": "#95a5a6",
}


def _points_payload(df: pd.DataFrame) -> list:
    """Return a JSON-serialisable list of vessel points for the WebGPU scene."""
    if df is None or df.empty:
        return []
    if not {"Latitude", "Longitude", "Category", "Cargo_Volume_bbls"}.issubset(df.columns):
        return []

    pts = []
    for lat, lon, cat, cargo, name, flag in zip(
        df["Latitude"].astype(float),
        df["Longitude"].astype(float),
        df["Category"].astype(str),
        df["Cargo_Volume_bbls"].astype(float),
        df.get("Vessel_Name", pd.Series(["vessel"] * len(df))).astype(str),
        df.get("Flag_State", pd.Series(["?"] * len(df))).astype(str),
    ):
        pts.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "color": _CATEGORY_COLORS.get(cat, _CATEGORY_COLORS["Other"]),
                "cargo": float(cargo),
                "name": name,
                "flag": flag,
                "category": cat,
            }
        )
    return pts


_GLOBE_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  html, body { margin: 0; padding: 0; background: radial-gradient(ellipse at center,#0b1220 0%,#05070c 80%); overflow: hidden; }
  #globe { width: 100%; height: __HEIGHT__px; display: block; }
  #globe-fallback {
    width: 100%; height: __HEIGHT__px;
    color: #e7ecf3; display: none; align-items: center; justify-content: center;
    font-family: system-ui, sans-serif;
  }
  #globe-badge {
    position: absolute; top: 10px; right: 16px;
    color: #a9b6c8; font-family: ui-monospace, Menlo, monospace; font-size: 11px;
    letter-spacing: 2px; background: rgba(10,16,24,0.4); padding: 3px 8px; border-radius: 4px;
  }
  #globe-legend {
    position: absolute; bottom: 10px; left: 16px;
    color: #e7ecf3; font-family: system-ui, sans-serif; font-size: 12px;
    background: rgba(10,16,24,0.5); padding: 6px 10px; border-radius: 6px;
    line-height: 1.5;
  }
  #globe-legend .sw { display: inline-block; width: 10px; height: 10px; margin-right: 6px; border-radius: 50%; vertical-align: middle; }
</style>
</head>
<body>
<canvas id="globe"></canvas>
<div id="globe-badge">WEBGPU</div>
<div id="globe-legend">
  <div><span class="sw" style="background:#2ecc71"></span>Jones Act / Domestic</div>
  <div><span class="sw" style="background:#ff9f1c"></span>Shadow Risk</div>
  <div><span class="sw" style="background:#e74c3c"></span>Sanctioned</div>
  <div><span class="sw" style="background:#95a5a6"></span>Other</div>
</div>
<div id="globe-fallback">WebGL/WebGPU unavailable in this browser.</div>
<script type="module">
  const POINTS = __POINTS_JSON__;
  const H = __HEIGHT__;
  const canvas = document.getElementById('globe');
  const fallback = document.getElementById('globe-fallback');
  const badge = document.getElementById('globe-badge');
  canvas.height = H;
  canvas.width = canvas.clientWidth || window.innerWidth;

  async function boot() {
    let THREE, useWebGPU = !!navigator.gpu, renderer;
    try {
      if (useWebGPU) {
        THREE = await import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.webgpu.min.js');
      }
      if (!useWebGPU || !THREE) {
        THREE = await import('https://cdn.jsdelivr.net/npm/three@0.160.0/+esm');
        useWebGPU = false;
      }
    } catch (e) {
      console.warn('three import failed', e);
      canvas.style.display = 'none';
      fallback.style.display = 'flex';
      return;
    }

    const scene = new THREE.Scene();
    const aspect = canvas.clientWidth / H;
    const camera = new THREE.PerspectiveCamera(42, aspect, 0.1, 100);
    camera.position.set(0, 0.6, 3.4);
    camera.lookAt(0, 0, 0);

    try {
      if (useWebGPU && THREE.WebGPURenderer) {
        renderer = new THREE.WebGPURenderer({ canvas, antialias: true, alpha: true });
        await renderer.init();
      } else {
        renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
      }
    } catch (e) {
      console.warn('renderer init failed, falling back to WebGL', e);
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
      useWebGPU = false;
    }
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(canvas.clientWidth, H, false);
    renderer.setClearColor(0x000000, 0);

    badge.textContent = useWebGPU ? 'WEBGPU' : 'WEBGL';

    // Globe
    const globeGeo = new THREE.SphereGeometry(1.0, 64, 48);
    const globeMat = new THREE.MeshStandardMaterial({
      color: 0x1b2838,
      roughness: 0.85,
      metalness: 0.15,
      emissive: 0x0a1018,
      emissiveIntensity: 0.35,
    });
    const globe = new THREE.Mesh(globeGeo, globeMat);
    scene.add(globe);

    // Wireframe "lat/lon" overlay
    const wire = new THREE.Mesh(
      new THREE.SphereGeometry(1.005, 36, 24),
      new THREE.MeshBasicMaterial({ color: 0x2e4a6b, wireframe: true, transparent: true, opacity: 0.28 })
    );
    scene.add(wire);

    // Atmosphere glow
    const atmo = new THREE.Mesh(
      new THREE.SphereGeometry(1.06, 48, 36),
      new THREE.MeshBasicMaterial({ color: 0x3a6ea5, transparent: true, opacity: 0.08, side: THREE.BackSide })
    );
    scene.add(atmo);

    // Lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const dir = new THREE.DirectionalLight(0xffffff, 1.1);
    dir.position.set(3, 2, 4);
    scene.add(dir);

    // Tanker points (instanced spheres)
    function latLonToVec3(lat, lon, r) {
      const phi = (90 - lat) * Math.PI / 180;
      const theta = (lon + 180) * Math.PI / 180;
      const x = -r * Math.sin(phi) * Math.cos(theta);
      const z =  r * Math.sin(phi) * Math.sin(theta);
      const y =  r * Math.cos(phi);
      return new THREE.Vector3(x, y, z);
    }

    const dotGeo = new THREE.SphereGeometry(1, 8, 8);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const instanced = new THREE.InstancedMesh(dotGeo, dotMat, Math.max(1, POINTS.length));
    instanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();

    POINTS.forEach((p, i) => {
      const v = latLonToVec3(p.lat, p.lon, 1.015);
      dummy.position.copy(v);
      // Scale by cargo (bbls) — clamp to reasonable pixel range
      const s = Math.min(0.028, 0.010 + (p.cargo / 2.3e6) * 0.018);
      dummy.scale.set(s, s, s);
      // Point "up" away from globe center
      dummy.lookAt(v.clone().multiplyScalar(2));
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);
      color.set(p.color);
      instanced.setColorAt(i, color);
    });
    instanced.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;
    scene.add(instanced);

    // Interaction: drag to rotate, wheel to zoom
    let isDragging = false, lastX = 0, lastY = 0;
    let rotY = 0.3, rotX = 0.1;
    canvas.addEventListener('pointerdown', (e) => { isDragging = true; lastX = e.clientX; lastY = e.clientY; });
    window.addEventListener('pointerup', () => { isDragging = false; });
    window.addEventListener('pointermove', (e) => {
      if (!isDragging) return;
      const dx = (e.clientX - lastX) / 200;
      const dy = (e.clientY - lastY) / 200;
      rotY += dx;
      rotX = Math.max(-1.2, Math.min(1.2, rotX + dy));
      lastX = e.clientX; lastY = e.clientY;
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      camera.position.z = Math.max(1.8, Math.min(6.0, camera.position.z + e.deltaY * 0.002));
    }, { passive: false });

    let autoRot = 0.001;
    function onResize() {
      const w = canvas.clientWidth;
      renderer.setSize(w, H, false);
      camera.aspect = w / H;
      camera.updateProjectionMatrix();
    }
    window.addEventListener('resize', onResize);

    function tick() {
      if (!isDragging) rotY += autoRot;
      globe.rotation.set(rotX, rotY, 0);
      wire.rotation.set(rotX, rotY, 0);
      instanced.rotation.set(rotX, rotY, 0);
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    }
    tick();
  }
  boot().catch(err => {
    console.warn('globe boot failed', err);
    canvas.style.display = 'none';
    fallback.style.display = 'flex';
  });
</script>
</body>
</html>
"""


def render_fleet_globe(ais_df: pd.DataFrame, height: int = 560) -> None:
    """Render the 3D globe with instanced tanker points."""
    points = _points_payload(ais_df)
    html = (
        _GLOBE_HTML
        .replace("__HEIGHT__", str(int(height)))
        .replace("__POINTS_JSON__", json.dumps(points))
    )
    _safe_components_html(html, height=int(height) + 10)


__all__ = ["render_hero_banner", "render_fleet_globe"]

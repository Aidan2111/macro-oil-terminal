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


# Pinned to a three.js build that ships `three/webgpu` + `three/tsl`
# as stable ES module entry points (r170+).
_THREE_VERSION = "0.170.0"
_THREE_WEBGPU_URL = f"https://cdn.jsdelivr.net/npm/three@{_THREE_VERSION}/build/three.webgpu.js"
_THREE_TSL_URL = f"https://cdn.jsdelivr.net/npm/three@{_THREE_VERSION}/build/three.tsl.js"
_THREE_CORE_URL = f"https://cdn.jsdelivr.net/npm/three@{_THREE_VERSION}/build/three.module.js"


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
    color: #e7ecf3; display: none; align-items: center; justify-content: center;
    font-family: system-ui, sans-serif; letter-spacing: 1px;
  }
  #hero-label {
    position: absolute; top: 14px; left: 20px;
    color: #e7ecf3; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; opacity: 0.78; pointer-events: none; letter-spacing: 2px;
    text-shadow: 0 0 6px rgba(0,0,0,0.6);
  }
</style>
</head>
<body>
<div id="hero-label">BOOTING // BRENT-WTI SIGNAL FLOW</div>
<canvas id="hero"></canvas>
<div id="hero-fallback">Hero render unavailable — static gradient fallback</div>
<script type="module">
  const THREE_WEBGPU = '__THREE_WEBGPU_URL__';
  const THREE_TSL    = '__THREE_TSL_URL__';
  const THREE_CORE   = '__THREE_CORE_URL__';
  const fallback = document.getElementById('hero-fallback');
  const canvas = document.getElementById('hero');
  const badge = document.getElementById('hero-label');
  const H = __HEIGHT__;
  canvas.height = H;
  canvas.width = canvas.clientWidth || window.innerWidth;

  async function boot() {
    let THREE, TSL, renderer, useWebGPU = !!navigator.gpu;

    // --- Path A: WebGPU + TSL ------------------------------------------
    if (useWebGPU) {
      try {
        THREE = await import(THREE_WEBGPU);
        TSL   = await import(THREE_TSL);
      } catch (e) {
        console.warn('WebGPU import failed, falling back to WebGL', e);
        useWebGPU = false;
        THREE = null; TSL = null;
      }
    }

    // --- Path B: classic WebGL -----------------------------------------
    if (!useWebGPU || !THREE) {
      try {
        THREE = await import(THREE_CORE);
      } catch (e) {
        console.warn('three core import failed', e);
        canvas.style.display = 'none';
        fallback.style.display = 'flex';
        return;
      }
    }

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    // --- Renderer -------------------------------------------------------
    try {
      if (useWebGPU && THREE.WebGPURenderer) {
        renderer = new THREE.WebGPURenderer({ canvas, antialias: true });
        await renderer.init();
      } else {
        renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
      }
    } catch (e) {
      console.warn('renderer init failed, falling back to WebGL', e);
      try {
        const core = await import(THREE_CORE);
        THREE = core;
        renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
        useWebGPU = false;
      } catch (ee) {
        canvas.style.display = 'none';
        fallback.style.display = 'flex';
        return;
      }
    }
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(canvas.clientWidth, H, false);

    // --- Material -------------------------------------------------------
    let mat, updateTime = () => {};
    const quadGeom = new THREE.PlaneGeometry(2, 2);

    if (useWebGPU && TSL) {
      // Three.js Shading Language — node material graph
      const {
        Fn, uv, vec2, vec3, color, float, mix,
        time, oscSine, positionLocal, sin, cos,
        mx_fractal_noise_float, fract, smoothstep,
      } = TSL;

      // Oil-slick iridescent color graph. fbm-ish via mx_fractal_noise_float
      // (OpenMaterialX-derived, available in three/tsl).
      const iridescent = Fn(() => {
        const st = uv().sub(0.5).mul(2.0);
        const ar = float(canvas.clientWidth / H);
        const warped = vec2(st.x.mul(ar), st.y);
        const t = time.mul(0.12);
        const q1 = warped.mul(2.5).add(vec2(t, t.mul(-0.7)));
        const q2 = warped.mul(2.5).add(vec2(t.mul(1.3), t.mul(0.4)));
        // Two layered fractal noises sum like fbm
        const n1 = mx_fractal_noise_float(vec3(q1.x, q1.y, t), float(5), float(2.02), float(0.5));
        const n2 = mx_fractal_noise_float(vec3(q2.x, q2.y, t.mul(0.6)), float(3), float(2.0), float(0.5));
        const n = n1.add(n2.mul(0.35));
        const c1 = color(0x0b1018);
        const c2 = color(0xc68a3a);
        const c3 = color(0x1ba6d9);
        const c4 = color(0x8c33a6);
        let col = mix(c1, c2, smoothstep(0.25, 0.55, n));
        col = mix(col, c3, smoothstep(0.45, 0.70, n));
        col = mix(col, c4, smoothstep(0.70, 0.95, n.mul(n)));
        // Signal-flow scan lines driven by oscSine(time)
        const stripe = smoothstep(
          0.48, 0.52,
          fract(uv().y.mul(8.0).add(oscSine(time.mul(0.3)).mul(0.5).add(0.5))),
        );
        col = mix(col, col.mul(1.22), stripe.mul(0.08));
        return col;
      });

      mat = new THREE.MeshBasicNodeMaterial();
      mat.colorNode = iridescent();
      // TSL `time` advances automatically via the renderer's animation loop;
      // no manual uniform tick needed.
      badge.textContent = 'WEBGPU // TSL // BRENT-WTI SIGNAL FLOW';
    } else {
      // WebGL fallback — classic GLSL raw shader with equivalent palette.
      const vert = `
        attribute vec3 position;
        varying vec2 vUv;
        void main() { vUv = position.xy * 0.5 + 0.5; gl_Position = vec4(position, 1.0); }
      `;
      const frag = `
        precision highp float;
        varying vec2 vUv; uniform float uTime; uniform vec2 uResolution;
        float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
        float noise(vec2 p){vec2 i=floor(p),f=fract(p);
          float a=hash(i),b=hash(i+vec2(1,0)),c=hash(i+vec2(0,1)),d=hash(i+vec2(1,1));
          vec2 u=f*f*(3.-2.*f);
          return mix(a,b,u.x)+(c-a)*u.y*(1.-u.x)+(d-b)*u.x*u.y;}
        float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*noise(p);p*=2.02;a*=.5;}return v;}
        void main(){
          vec2 uv=vUv; uv.x*=uResolution.x/uResolution.y;
          float t=uTime*0.12;
          vec2 q=uv*2.5+vec2(t,-t*0.7);
          float n=fbm(q+fbm(q+t));
          vec3 c1=vec3(0.04,0.06,0.10), c2=vec3(0.78,0.50,0.20),
               c3=vec3(0.10,0.65,0.85), c4=vec3(0.55,0.20,0.65);
          vec3 col=mix(c1,c2,smoothstep(0.25,0.55,n));
          col=mix(col,c3,smoothstep(0.45,0.70,n));
          col=mix(col,c4,smoothstep(0.70,0.90,n*n));
          float stripe=smoothstep(0.48,0.52,fract(uv.y*8.0+uTime*0.3));
          col=mix(col,col*1.2,0.07*stripe);
          gl_FragColor=vec4(col,1.0);
        }
      `;
      mat = new THREE.RawShaderMaterial({
        vertexShader: vert,
        fragmentShader: frag,
        uniforms: {
          uTime: { value: 0 },
          uResolution: { value: new THREE.Vector2(canvas.clientWidth, H) },
        },
        glslVersion: THREE.GLSL1 || 100,
      });
      updateTime = (t) => {
        mat.uniforms.uTime.value = t;
        mat.uniforms.uResolution.value.set(canvas.clientWidth, H);
      };
      badge.textContent = 'WEBGL // CLASSIC GLSL // BRENT-WTI SIGNAL FLOW';
    }

    const quad = new THREE.Mesh(quadGeom, mat);
    scene.add(quad);

    function onResize() {
      const w = canvas.clientWidth;
      renderer.setSize(w, H, false);
    }
    window.addEventListener('resize', onResize);

    const start = performance.now();
    // WebGPURenderer supports setAnimationLoop + renderAsync; WebGLRenderer
    // also supports setAnimationLoop. Prefer that for clean TSL time integration.
    const tick = async () => {
      updateTime((performance.now() - start) * 0.001);
      if (renderer.renderAsync) await renderer.renderAsync(scene, camera);
      else renderer.render(scene, camera);
    };
    if (renderer.setAnimationLoop) renderer.setAnimationLoop(tick);
    else {
      const loop = () => { tick(); requestAnimationFrame(loop); };
      loop();
    }
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
    """Render the animated oil-slick hero banner at the top of the app.

    WebGPU path uses Three.js TSL node materials
    (``MeshBasicNodeMaterial`` + ``Fn()`` colorNode with ``mx_fractal_noise_float``
    and ``oscSine(time)``). WebGL path uses an equivalent classic GLSL
    RawShaderMaterial so the visual is near-identical on either backend.
    """
    html = (
        _HERO_HTML
        .replace("__HEIGHT__", str(int(height)))
        .replace("__THREE_WEBGPU_URL__", _THREE_WEBGPU_URL)
        .replace("__THREE_TSL_URL__", _THREE_TSL_URL)
        .replace("__THREE_CORE_URL__", _THREE_CORE_URL)
    )
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
  #globe { width: 100%; height: __HEIGHT__px; display: block; cursor: grab; }
  #globe:active { cursor: grabbing; }
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
<div id="globe-badge">BOOTING</div>
<div id="globe-legend">
  <div><span class="sw" style="background:#2ecc71"></span>Jones Act / Domestic</div>
  <div><span class="sw" style="background:#ff9f1c"></span>Shadow Risk</div>
  <div><span class="sw" style="background:#e74c3c"></span>Sanctioned</div>
  <div><span class="sw" style="background:#95a5a6"></span>Other</div>
</div>
<div id="globe-fallback">WebGL/WebGPU unavailable in this browser.</div>
<script type="module">
  const POINTS = __POINTS_JSON__;
  const THREE_WEBGPU = '__THREE_WEBGPU_URL__';
  const THREE_TSL    = '__THREE_TSL_URL__';
  const THREE_CORE   = '__THREE_CORE_URL__';
  const EARTH_TEX    = '__EARTH_TEX_URL__';
  const EARTH_NIGHT  = '__EARTH_NIGHT_URL__';
  const H = __HEIGHT__;
  const canvas = document.getElementById('globe');
  const fallback = document.getElementById('globe-fallback');
  const badge = document.getElementById('globe-badge');
  canvas.height = H;
  canvas.width = canvas.clientWidth || window.innerWidth;

  async function boot() {
    let THREE, TSL = null, useWebGPU = !!navigator.gpu, renderer;

    if (useWebGPU) {
      try {
        THREE = await import(THREE_WEBGPU);
        TSL   = await import(THREE_TSL);
      } catch (e) {
        console.warn('WebGPU import failed, falling back', e);
        useWebGPU = false; THREE = null; TSL = null;
      }
    }
    if (!useWebGPU || !THREE) {
      try { THREE = await import(THREE_CORE); }
      catch (e) {
        console.warn('three core import failed', e);
        canvas.style.display = 'none'; fallback.style.display = 'flex'; return;
      }
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
      const core = await import(THREE_CORE);
      THREE = core;
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
      useWebGPU = false;
    }
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(canvas.clientWidth, H, false);
    renderer.setClearColor(0x000000, 0);
    badge.textContent = useWebGPU ? 'WEBGPU / TSL EARTH' : 'WEBGL / EARTH';

    // --- Earth textures (day + night) ----------------------------------
    // Day map is a threejs.org example texture; fallback = procedural color.
    const texLoader = new THREE.TextureLoader();
    texLoader.setCrossOrigin('anonymous');

    function loadTex(url) {
      return new Promise((resolve) => {
        texLoader.load(url, (t) => resolve(t), undefined, () => resolve(null));
      });
    }
    const [dayTex, nightTex] = await Promise.all([loadTex(EARTH_TEX), loadTex(EARTH_NIGHT)]);

    // --- Globe ---------------------------------------------------------
    const globeGeo = new THREE.SphereGeometry(1.0, 96, 64);
    let globe;

    if (useWebGPU && TSL && dayTex) {
      // TSL day/night earth: dot(normal, sunDir) selects day vs night.
      const {
        Fn, texture, normalLocal, vec3, float, max, smoothstep,
        positionLocal, time, mix, uv, cos, sin, dot, uniform,
      } = TSL;

      const sunDir = uniform(new THREE.Vector3(1, 0.15, 0.4));

      const colorGraph = Fn(() => {
        const n = normalLocal;
        const lambert = max(float(0), dot(n, sunDir));
        const day = texture(dayTex, uv()).rgb;
        const night = nightTex
          ? texture(nightTex, uv()).rgb.mul(1.4)
          : day.mul(0.1);
        const dayNight = mix(night, day, smoothstep(float(0.0), float(0.25), lambert));
        // Blue rim on terminator
        const rim = smoothstep(float(0.0), float(0.15), lambert).oneMinus().mul(
          smoothstep(float(-0.3), float(0.0), lambert)
        );
        const rimColor = vec3(0.18, 0.42, 0.72).mul(rim);
        return dayNight.add(rimColor);
      });

      const mat = new THREE.MeshBasicNodeMaterial();
      mat.colorNode = colorGraph();
      globe = new THREE.Mesh(globeGeo, mat);
      globe._sunDir = sunDir; // keep ref for animation
    } else if (dayTex) {
      // WebGL path — standard material with emissive night fallback
      const mat = new THREE.MeshPhongMaterial({
        map: dayTex,
        emissiveMap: nightTex || null,
        emissive: nightTex ? 0xffffff : 0x111122,
        emissiveIntensity: nightTex ? 1.15 : 0.3,
        shininess: 14,
        specular: 0x0a1522,
      });
      globe = new THREE.Mesh(globeGeo, mat);
    } else {
      // No texture reachable — procedural fallback (deep-ocean navy)
      const mat = new THREE.MeshStandardMaterial({
        color: 0x1b3550,
        roughness: 0.85,
        metalness: 0.12,
        emissive: 0x0a1830,
        emissiveIntensity: 0.35,
      });
      globe = new THREE.Mesh(globeGeo, mat);
    }
    scene.add(globe);

    // Faint lat/lon wire
    const wire = new THREE.Mesh(
      new THREE.SphereGeometry(1.004, 36, 24),
      new THREE.MeshBasicMaterial({ color: 0x2e4a6b, wireframe: true, transparent: true, opacity: 0.18 })
    );
    scene.add(wire);

    // Atmosphere scattering shell
    const atmo = new THREE.Mesh(
      new THREE.SphereGeometry(1.07, 64, 48),
      new THREE.MeshBasicMaterial({ color: 0x3a6ea5, transparent: true, opacity: 0.11, side: THREE.BackSide })
    );
    scene.add(atmo);

    // Lights (only matter for WebGL phong path)
    scene.add(new THREE.AmbientLight(0xffffff, 0.35));
    const dir = new THREE.DirectionalLight(0xffffff, 1.1);
    dir.position.set(3, 1.2, 4);
    scene.add(dir);

    // --- Instanced tanker dots -----------------------------------------
    function latLonToVec3(lat, lon, r) {
      const phi = (90 - lat) * Math.PI / 180;
      const theta = (lon + 180) * Math.PI / 180;
      const x = -r * Math.sin(phi) * Math.cos(theta);
      const z =  r * Math.sin(phi) * Math.sin(theta);
      const y =  r * Math.cos(phi);
      return new THREE.Vector3(x, y, z);
    }

    const dotGeo = new THREE.SphereGeometry(1, 10, 10);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const instanced = new THREE.InstancedMesh(dotGeo, dotMat, Math.max(1, POINTS.length));
    instanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();

    POINTS.forEach((p, i) => {
      const v = latLonToVec3(p.lat, p.lon, 1.018);
      dummy.position.copy(v);
      const s = Math.min(0.030, 0.011 + (p.cargo / 2.3e6) * 0.020);
      dummy.scale.set(s, s, s);
      dummy.lookAt(v.clone().multiplyScalar(2));
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);
      color.set(p.color);
      instanced.setColorAt(i, color);
    });
    instanced.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;
    scene.add(instanced);

    // --- Interaction ---------------------------------------------------
    let isDragging = false, lastX = 0, lastY = 0;
    let rotY = 0.35, rotX = 0.12;
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
      camera.position.z = Math.max(1.7, Math.min(6.0, camera.position.z + e.deltaY * 0.002));
    }, { passive: false });

    function onResize() {
      const w = canvas.clientWidth;
      renderer.setSize(w, H, false);
      camera.aspect = w / H;
      camera.updateProjectionMatrix();
    }
    window.addEventListener('resize', onResize);

    const start = performance.now();
    const autoRot = 0.0015;
    const tick = async () => {
      const t = (performance.now() - start) * 0.001;
      if (!isDragging) rotY += autoRot;
      globe.rotation.set(rotX, rotY, 0);
      wire.rotation.set(rotX, rotY, 0);
      instanced.rotation.set(rotX, rotY, 0);
      // Auto-rotate the sun in TSL path
      if (globe._sunDir) {
        const ang = t * 0.08;
        globe._sunDir.value.set(Math.cos(ang), 0.22, Math.sin(ang));
      } else {
        dir.position.set(Math.cos(t * 0.08) * 3, 1.2, Math.sin(t * 0.08) * 3);
      }
      if (renderer.renderAsync) await renderer.renderAsync(scene, camera);
      else renderer.render(scene, camera);
    };
    if (renderer.setAnimationLoop) renderer.setAnimationLoop(tick);
    else (function loop() { tick(); requestAnimationFrame(loop); })();
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


# Earth textures — public threejs.org example assets. These are standard
# CC-licensed equirectangular maps distributed with the three.js examples.
_EARTH_DAY_URL = "https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg"
_EARTH_NIGHT_URL = "https://threejs.org/examples/textures/planets/earth_lights_2048.png"


def render_fleet_globe(ais_df: pd.DataFrame, height: int = 560) -> None:
    """Render the interactive 3D Earth globe with instanced tanker points.

    Uses TSL node materials on WebGPU (day/night via ``dot(normal, sunDir)``
    with auto-rotating sun), MeshPhongMaterial with emissiveMap on WebGL,
    and a procedural navy fallback if the texture CDN is unreachable.
    Tankers are an ``InstancedMesh`` of 500 spheres colored by category.
    """
    points = _points_payload(ais_df)
    html = (
        _GLOBE_HTML
        .replace("__HEIGHT__", str(int(height)))
        .replace("__POINTS_JSON__", json.dumps(points))
        .replace("__THREE_WEBGPU_URL__", _THREE_WEBGPU_URL)
        .replace("__THREE_TSL_URL__", _THREE_TSL_URL)
        .replace("__THREE_CORE_URL__", _THREE_CORE_URL)
        .replace("__EARTH_TEX_URL__", _EARTH_DAY_URL)
        .replace("__EARTH_NIGHT_URL__", _EARTH_NIGHT_URL)
    )
    _safe_components_html(html, height=int(height) + 10)


__all__ = ["render_hero_banner", "render_fleet_globe"]

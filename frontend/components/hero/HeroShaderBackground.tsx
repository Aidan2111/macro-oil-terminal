"use client";

import { useEffect, useRef } from "react";
import { hasWebGPU } from "@/lib/has-webgpu";
import type {
  BufferGeometry as TBufferGeometry,
  Material as TMaterial,
} from "three";

type Props = {
  /** 0 = calm cyan, 1 = turbulent crimson. */
  stretchFactor: number;
  className?: string;
};

/**
 * Full-width WebGPU / TSL shader backdrop for the hero card.
 *
 * WebGPU-only by design — silently renders nothing when WebGPU is
 * absent (the hero card sits on top of the tokenised gradient fallback
 * provided by the layout's CSS).
 */
export function HeroShaderBackground({ stretchFactor, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stretchRef = useRef(stretchFactor);

  useEffect(() => {
    stretchRef.current = stretchFactor;
  }, [stretchFactor]);

  useEffect(() => {
    if (!hasWebGPU()) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    let cleanup: (() => void) | undefined;

    (async () => {
      try {
        // Single dynamic import. `three.webgpu.js` re-exports every core
        // class (Scene, Camera, Mesh, Vector3, …) AND every TSL helper
        // (`color`, `uniform`, `mix`, `mx_fractal_noise_float`, …) so
        // we don't need separate `three` and `three/tsl` imports. Using
        // both at runtime triggers three's `globalThis.__THREE__` guard
        // and prints "Multiple instances of Three.js being imported."
        const THREE = await import("three/webgpu");
        const TSL = THREE; // alias for legibility on the destructure
        const { WebGPURenderer, MeshBasicNodeMaterial } = THREE;

        const {
          color,
          mix,
          timerLocal,
          mx_fractal_noise_float,
          positionWorld,
          uniform,
          float,
        } = TSL;

        const scene = new THREE.Scene();
        const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

        const renderer = new WebGPURenderer({
          canvas,
          antialias: true,
          alpha: true,
        });
        await renderer.init();
        renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
        renderer.setSize(
          canvas.clientWidth || 1,
          canvas.clientHeight || 1,
          false,
        );
        renderer.setClearColor(new THREE.Color(0x000000), 0);

        const stretchU = uniform(stretchRef.current);

        const mat = new MeshBasicNodeMaterial();
        mat.transparent = true;
        mat.opacity = 0.3;
        mat.blending = THREE.AdditiveBlending;

        const t = timerLocal(0.2);
        const noise = mx_fractal_noise_float(positionWorld.xy.mul(t));
        mat.colorNode = mix(
          color("#22d3ee"),
          color("#f43f5e"),
          stretchU,
        ).mul(noise.mul(float(0.5)).add(float(0.5)));

        const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat);
        scene.add(quad);

        const ro = new ResizeObserver(() => {
          renderer.setSize(
            canvas.clientWidth || 1,
            canvas.clientHeight || 1,
            false,
          );
        });
        ro.observe(canvas);

        let raf = 0;
        const tick = () => {
          raf = requestAnimationFrame(tick);
          stretchU.value = stretchRef.current;
          renderer.renderAsync(scene, camera).catch(() => {});
        };
        raf = requestAnimationFrame(tick);

        cleanup = () => {
          cancelAnimationFrame(raf);
          ro.disconnect();
          (quad.geometry as TBufferGeometry).dispose();
          (quad.material as TMaterial).dispose();
          renderer.dispose();
        };
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("[HeroShader] WebGPU unavailable or failed", err);
      }
    })();

    return () => {
      cleanup?.();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      data-testid="hero-shader-canvas"
      className={className}
    />
  );
}

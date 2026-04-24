"use client";

import { useEffect, useRef } from "react";
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
    if (typeof navigator === "undefined") return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (!(navigator as any).gpu) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    let disposed = false;
    let cleanup: (() => void) | undefined;

    (async () => {
      try {
        const THREE = await import("three");
        const { WebGPURenderer, MeshBasicNodeMaterial } = await import(
          "three/webgpu"
        );
        const TSL = await import("three/tsl");

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

        const stretchU = uniform(float(stretchRef.current));

        const mat = new MeshBasicNodeMaterial();
        mat.transparent = true;
        mat.opacity = 0.3;
        mat.blending = THREE.AdditiveBlending;

        const t = timerLocal(0.2);
        const noise = mx_fractal_noise_float(
          (positionWorld as any).xy.mul(t as any) as any,
        );
        mat.colorNode = mix(
          color("#22d3ee"),
          color("#f43f5e"),
          stretchU as any,
        ).mul((noise.mul(float(0.5)).add(float(0.5))) as any);

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
          // stretchU is a uniform(float(x)) whose runtime .value is a number.
          // TS sees it as a Node; cast through unknown for the live update.
          (stretchU as unknown as { value: number }).value = stretchRef.current;
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
      disposed = true;
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

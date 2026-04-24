import { describe, it, expect } from "vitest";
import {
  latLonToCartesian,
  cartesianToLatLon,
  greatCirclePoints,
  solarPos,
} from "@/lib/globe-physics";

const EPS = 1e-6;

function close(a: number, b: number, eps = 1e-4): boolean {
  return Math.abs(a - b) <= eps;
}

describe("latLonToCartesian", () => {
  it("maps the equator+prime meridian to the +x axis on a unit sphere", () => {
    const [x, y, z] = latLonToCartesian(0, 0, 1);
    // Three.js convention used in the prior art: lon=0,lat=0 -> (0,0,1) is
    // not what the Streamlit port used; it used (-sin(phi)cos(theta),
    // cos(phi), sin(phi)sin(theta)). With phi=90deg,theta=180deg this is
    // (-sin90*cos180, cos90, sin90*sin180) = (1, 0, 0).
    expect(close(x, 1)).toBe(true);
    expect(close(y, 0)).toBe(true);
    expect(close(z, 0, 1e-10)).toBe(true);
  });

  it("maps the north pole to +y", () => {
    const [x, y, z] = latLonToCartesian(90, 0, 1);
    expect(close(x, 0)).toBe(true);
    expect(close(y, 1)).toBe(true);
    expect(close(z, 0)).toBe(true);
  });

  it("maps the south pole to -y", () => {
    const [x, y, z] = latLonToCartesian(-90, 123.4, 2);
    expect(close(x, 0)).toBe(true);
    expect(close(y, -2)).toBe(true);
    expect(close(z, 0)).toBe(true);
  });

  it("scales with radius", () => {
    const [x, y, z] = latLonToCartesian(0, 0, 2.5);
    const r = Math.sqrt(x * x + y * y + z * z);
    expect(close(r, 2.5)).toBe(true);
  });

  it("antipodal points are opposite vectors", () => {
    const a = latLonToCartesian(30, 40, 1);
    const b = latLonToCartesian(-30, 40 + 180, 1);
    expect(close(a[0], -b[0])).toBe(true);
    expect(close(a[1], -b[1])).toBe(true);
    expect(close(a[2], -b[2])).toBe(true);
  });

  it("wraps longitude across the antimeridian smoothly", () => {
    // lon=179 and lon=-181 should produce the same point
    const a = latLonToCartesian(10, 179, 1);
    const b = latLonToCartesian(10, -181, 1);
    expect(close(a[0], b[0])).toBe(true);
    expect(close(a[1], b[1])).toBe(true);
    expect(close(a[2], b[2])).toBe(true);
  });
});

describe("cartesianToLatLon", () => {
  it("inverts latLonToCartesian for arbitrary points", () => {
    const cases: Array<[number, number]> = [
      [0, 0],
      [45, 45],
      [-23.5, 117.3],
      [60, -120],
    ];
    for (const [lat, lon] of cases) {
      const [x, y, z] = latLonToCartesian(lat, lon, 1);
      const [lat2, lon2] = cartesianToLatLon(x, y, z);
      expect(close(lat, lat2)).toBe(true);
      // Longitude wraps, so compare via sin/cos to dodge +/-180 seam
      expect(close(Math.sin((lon * Math.PI) / 180), Math.sin((lon2 * Math.PI) / 180))).toBe(true);
      expect(close(Math.cos((lon * Math.PI) / 180), Math.cos((lon2 * Math.PI) / 180))).toBe(true);
    }
  });

  it("is stable at the poles (longitude undefined, lat clamped)", () => {
    const [lat] = cartesianToLatLon(0, 1, 0);
    expect(close(lat, 90)).toBe(true);
    const [lat2] = cartesianToLatLon(0, -1, 0);
    expect(close(lat2, -90)).toBe(true);
  });
});

describe("greatCirclePoints", () => {
  it("starts at (lat1,lon1) and ends at (lat2,lon2)", () => {
    const pts = greatCirclePoints(0, 0, 45, 90, 20);
    expect(pts.length).toBe(20);
    expect(close(pts[0][0], 0)).toBe(true);
    expect(close(pts[0][1], 0)).toBe(true);
    expect(close(pts[pts.length - 1][0], 45)).toBe(true);
    expect(close(pts[pts.length - 1][1], 90)).toBe(true);
  });

  it("stays on the unit sphere (radius 1) when interpolating", () => {
    const pts = greatCirclePoints(10, 20, 70, -30, 30);
    for (const [lat, lon] of pts) {
      const [x, y, z] = latLonToCartesian(lat, lon, 1);
      const r = Math.sqrt(x * x + y * y + z * z);
      expect(close(r, 1, 1e-3)).toBe(true);
    }
  });

  it("crosses the antimeridian when endpoints straddle it", () => {
    // Tokyo (35.68, 139.77) to San Francisco (37.77, -122.42) — great
    // circle goes over the Pacific, not across Europe.
    const pts = greatCirclePoints(35.68, 139.77, 37.77, -122.42, 50);
    // Midpoint longitude should be > |160| (near the dateline), not near 0
    const mid = pts[Math.floor(pts.length / 2)];
    expect(Math.abs(mid[1])).toBeGreaterThan(160);
  });
});

describe("solarPos", () => {
  it("returns declination near 0 at the vernal equinox", () => {
    // 2024 vernal equinox: 2024-03-20 03:06 UTC
    const { dec } = solarPos(new Date("2024-03-20T03:06:00Z"));
    expect(Math.abs(dec)).toBeLessThan(0.02); // within ~1 degree
  });

  it("returns declination near +23.44deg at June solstice", () => {
    // 2024-06-20 20:51 UTC
    const { dec } = solarPos(new Date("2024-06-20T20:51:00Z"));
    const deg = (dec * 180) / Math.PI;
    expect(deg).toBeGreaterThan(22.5);
    expect(deg).toBeLessThan(24.0);
  });

  it("returns declination near -23.44deg at December solstice", () => {
    const { dec } = solarPos(new Date("2024-12-21T09:21:00Z"));
    const deg = (dec * 180) / Math.PI;
    expect(deg).toBeGreaterThan(-24.0);
    expect(deg).toBeLessThan(-22.5);
  });

  it("returns dec and ra as finite radians", () => {
    const { dec, ra } = solarPos(new Date());
    expect(Number.isFinite(dec)).toBe(true);
    expect(Number.isFinite(ra)).toBe(true);
    expect(Math.abs(dec)).toBeLessThan(Math.PI);
    expect(Math.abs(ra)).toBeLessThan(2 * Math.PI + EPS);
  });
});

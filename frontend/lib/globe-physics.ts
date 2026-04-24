/**
 * Globe physics helpers — pure math, no three.js dependency so they
 * are trivially unit-testable in jsdom and reusable from server
 * components / workers / anywhere.
 *
 * Lat/Lon convention matches the Streamlit prior art in
 * ``webgpu_components.py::latLonToVec3`` so vessel positions line up
 * with the ported Earth texture (NASA Blue Marble, equirectangular,
 * prime meridian at the horizontal centre).
 *
 *   phi   = (90 - lat) * pi/180    — polar angle from +y down
 *   theta = (lon + 180) * pi/180   — azimuth
 *   x = -r * sin(phi) * cos(theta)
 *   y =  r * cos(phi)
 *   z =  r * sin(phi) * sin(theta)
 */

const DEG = Math.PI / 180;
const RAD = 180 / Math.PI;

export function latLonToCartesian(
  lat: number,
  lon: number,
  r: number,
): [number, number, number] {
  const phi = (90 - lat) * DEG;
  const theta = (lon + 180) * DEG;
  const sinPhi = Math.sin(phi);
  return [
    -r * sinPhi * Math.cos(theta),
    r * Math.cos(phi),
    r * sinPhi * Math.sin(theta),
  ];
}

export function cartesianToLatLon(
  x: number,
  y: number,
  z: number,
): [number, number] {
  const r = Math.sqrt(x * x + y * y + z * z) || 1;
  const yUnit = Math.max(-1, Math.min(1, y / r));
  const phi = Math.acos(yUnit); // 0..pi, 0 at +y (north)
  const lat = 90 - phi * RAD;
  // Invert x = -r sinPhi cos(theta), z = r sinPhi sin(theta)
  // -> theta = atan2(z, -x); lon = theta*RAD - 180
  const sinPhi = Math.sin(phi);
  let lon: number;
  if (sinPhi < 1e-9) {
    lon = 0; // pole — longitude undefined; return 0 deterministically
  } else {
    const theta = Math.atan2(z, -x);
    lon = theta * RAD - 180;
    // Normalise to [-180, 180)
    if (lon < -180) lon += 360;
    if (lon >= 180) lon -= 360;
  }
  return [lat, lon];
}

/**
 * Great-circle interpolation using slerp on the 3D unit vectors.
 * Returns ``n`` (lat, lon) samples, inclusive of both endpoints.
 * Handles antipodal pairs gracefully by falling back to linear
 * interpolation (the great circle is undefined for exact antipodes).
 */
export function greatCirclePoints(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
  n: number,
): Array<[number, number]> {
  if (n < 2) {
    return n === 1 ? [[lat1, lon1]] : [];
  }
  const a = latLonToCartesian(lat1, lon1, 1);
  const b = latLonToCartesian(lat2, lon2, 1);
  const dot = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const omega = Math.acos(dot);
  const sinOmega = Math.sin(omega);

  const out: Array<[number, number]> = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    let x: number, y: number, z: number;
    if (sinOmega < 1e-9) {
      // Endpoints coincident — just return lat/lon lerps
      x = a[0] * (1 - t) + b[0] * t;
      y = a[1] * (1 - t) + b[1] * t;
      z = a[2] * (1 - t) + b[2] * t;
    } else {
      const s1 = Math.sin((1 - t) * omega) / sinOmega;
      const s2 = Math.sin(t * omega) / sinOmega;
      x = a[0] * s1 + b[0] * s2;
      y = a[1] * s1 + b[1] * s2;
      z = a[2] * s1 + b[2] * s2;
    }
    out.push(cartesianToLatLon(x, y, z));
  }
  // Guarantee exact endpoints (slerp round-off can wobble lat by 1e-6)
  out[0] = [lat1, lon1];
  out[out.length - 1] = [lat2, lon2];
  return out;
}

/**
 * Rough analytic solar position in equatorial coordinates.
 * Accurate to ~0.5 degrees — good enough for lighting a rendered
 * globe, not for navigation. Returns radians.
 *
 * Algorithm: NOAA / Jean Meeus low-precision formulas
 * (https://gml.noaa.gov/grad/solcalc/solareqns.PDF).
 */
export function solarPos(date: Date): { dec: number; ra: number } {
  // Fractional year gamma (radians)
  const year = date.getUTCFullYear();
  const startOfYear = Date.UTC(year, 0, 1, 0, 0, 0);
  const msPerDay = 86_400_000;
  const daysIntoYear = (date.getTime() - startOfYear) / msPerDay; // 0..365/366
  const leap = ((year % 4 === 0 && year % 100 !== 0) || year % 400 === 0) ? 366 : 365;
  const hourFrac = date.getUTCHours() + date.getUTCMinutes() / 60 +
    date.getUTCSeconds() / 3600;
  const gamma = (2 * Math.PI / leap) * (daysIntoYear + (hourFrac - 12) / 24);

  // Declination (radians)
  const dec =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma);

  // Equation of time (minutes) -> convert to right-ascension-like angle.
  const eqTimeMin =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(gamma) -
      0.032077 * Math.sin(gamma) -
      0.014615 * Math.cos(2 * gamma) -
      0.040849 * Math.sin(2 * gamma));

  // Solar hour angle at the Greenwich meridian -> right ascension proxy.
  // True-solar-time minutes at 0deg lon:
  const tstMin = hourFrac * 60 + eqTimeMin;
  // Hour angle (radians) east-positive, zero at solar noon.
  const ha = ((tstMin / 4) - 180) * DEG;
  // Right ascension here = -ha so sun vector = (cos(dec)cos(ra), sin(dec), cos(dec)sin(ra))
  const ra = -ha;
  return { dec, ra };
}

/** Convert (dec, ra) radians to a unit vector in the same convention
 *  used by latLonToCartesian — i.e. y=up, declination=latitude. */
export function solarUnitVector(date: Date): [number, number, number] {
  const { dec, ra } = solarPos(date);
  const latDeg = (dec * 180) / Math.PI;
  const lonDeg = (ra * 180) / Math.PI;
  return latLonToCartesian(latDeg, lonDeg, 1);
}

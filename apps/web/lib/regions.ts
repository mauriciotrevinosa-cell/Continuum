/**
 * Normalized regions: a rectangle as fractions (0..1) of the image it sits on.
 *
 * The server stores exactly this shape beside a content locator, so a crop is
 * never copied bytes - only a view of the original page.
 */

export interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The smallest edge a selection may have; matches the server's minimum. */
export const MIN_EDGE = 0.01;

const clamp = (value: number) => Math.min(1, Math.max(0, value));
const round = (value: number) => Math.round(value * 10000) / 10000;

/** A region from two points given in element pixels, clamped and normalized. */
export function regionFromPoints(
  a: { x: number; y: number },
  b: { x: number; y: number },
  box: { width: number; height: number },
): Region | null {
  if (box.width <= 0 || box.height <= 0) return null;
  const left = clamp(Math.min(a.x, b.x) / box.width);
  const top = clamp(Math.min(a.y, b.y) / box.height);
  const right = clamp(Math.max(a.x, b.x) / box.width);
  const bottom = clamp(Math.max(a.y, b.y) / box.height);
  const region = {
    x: round(left),
    y: round(top),
    width: round(right - left),
    height: round(bottom - top),
  };
  if (region.width < MIN_EDGE || region.height < MIN_EDGE) return null;
  if (region.x + region.width > 1) region.width = round(1 - region.x);
  if (region.y + region.height > 1) region.height = round(1 - region.y);
  return region;
}

/** CSS placement of a region over its image, in percent. */
export function regionStyle(region: Region): {
  left: string;
  top: string;
  width: string;
  height: string;
} {
  return {
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.width * 100}%`,
    height: `${region.height * 100}%`,
  };
}

export function overlaps(a: Region, b: Region): boolean {
  return (
    Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x) > 1e-9 &&
    Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y) > 1e-9
  );
}

"use client";

import { useRef, useState } from "react";
import { type Region, regionFromPoints, regionStyle } from "@/lib/regions";

export interface Box {
  key: string;
  region: Region;
  label?: string;
  kind?: string;
}

/**
 * An image you can draw a rectangle on. The rectangle is reported as a
 * normalized region of the image - never as pixels of the screen - so it maps
 * to the exact same area of the original page at any size.
 */
export function RegionSelector({
  src,
  alt,
  selecting,
  draft,
  boxes = [],
  onSelect,
  onImageClick,
  onError,
  imgClassName,
}: {
  src: string;
  alt: string;
  selecting: boolean;
  draft: Region | null;
  boxes?: Box[];
  onSelect: (region: Region | null) => void;
  onImageClick?: () => void;
  onError?: () => void;
  imgClassName?: string;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [live, setLive] = useState<Region | null>(null);

  const point = (event: React.PointerEvent) => {
    const rect = stage.current?.getBoundingClientRect();
    return rect
      ? { x: event.clientX - rect.left, y: event.clientY - rect.top, box: rect }
      : null;
  };

  return (
    <div
      ref={stage}
      className={`region-stage${selecting ? " selecting" : ""}`}
      onPointerDown={(event) => {
        if (!selecting) return;
        const p = point(event);
        if (!p) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        setStart({ x: p.x, y: p.y });
        setLive(null);
      }}
      onPointerMove={(event) => {
        if (!selecting || !start) return;
        const p = point(event);
        if (p) setLive(regionFromPoints(start, p, p.box));
      }}
      onPointerUp={(event) => {
        if (!selecting || !start) return;
        const p = point(event);
        setStart(null);
        setLive(null);
        if (p) onSelect(regionFromPoints(start, p, p.box));
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id */}
      <img
        src={src}
        alt={alt}
        className={imgClassName}
        draggable={false}
        onError={onError}
        onClick={selecting ? undefined : onImageClick}
      />
      {boxes.map((box) => (
        <span key={box.key} className="region-box" data-kind={box.kind} style={regionStyle(box.region)}>
          {box.label ? <b>{box.label}</b> : null}
        </span>
      ))}
      {live ?? draft ? (
        <span className="region-box draft" style={regionStyle((live ?? draft) as Region)} />
      ) : null}
    </div>
  );
}

"use client";

import * as React from "react";
import Image from "next/image";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";

import { cn } from "@/lib/utils";

/**
 * Drifts a decorative image as it passes through the viewport.
 *
 * Reserved for ambient decor on the
 * dashboard.
 */
export function ParallaxLayer({
  src,
  alt = "",
  width,
  height,
  className,
  speed = 80,
  axis = "y",
  priority = false,
}: {
  src: string;
  alt?: string;
  width: number;
  height: number;
  className?: string;
  /** Total px of travel across the scroll-through. Larger = faster drift. */
  speed?: number;
  axis?: "x" | "y";
  priority?: boolean;
}) {
  const reduce = useReducedMotion();
  const ref = React.useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  // Travel from +speed/2 to -speed/2 as the element crosses the viewport.
  const shift = useTransform(
    scrollYProgress,
    [0, 1],
    [speed / 2, -speed / 2],
  );

  const style = reduce
    ? undefined
    : axis === "y"
      ? { y: shift }
      : { x: shift };

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={cn("pointer-events-none absolute select-none", className)}
    >
      <motion.div style={style} className="h-full w-full">
        <Image
          src={src}
          alt={alt}
          width={width}
          height={height}
          priority={priority}
          className="h-full w-full object-contain"
        />
      </motion.div>
    </div>
  );
}

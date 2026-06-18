"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

const emptySubscribe = () => () => {};

/** True on the client, false during SSR — without a setState-in-effect. */
function useHydrated() {
  return React.useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
}

type Particle = {
  left: number; // % across the field
  size: number; // px
  delay: number; // s
  duration: number; // s
  drift: number; // px horizontal sway
  opacity: number;
};

// Deterministic pseudo-random, seeded by index (not Math.random()). Values are
// rounded to short fixed precision so there's no long-decimal for SSR/CSR to
// disagree on; the component is also mount-gated below as a belt-and-braces
// guard against framer-motion style serialization mismatches.
function buildParticles(count: number): Particle[] {
  const round = (value: number, dp = 2) => Number(value.toFixed(dp));
  const particles: Particle[] = [];
  for (let i = 0; i < count; i++) {
    const r = (n: number) => {
      const x = Math.sin(i * 12.9898 + n * 78.233) * 43758.5453;
      return x - Math.floor(x); // 0..1
    };
    particles.push({
      left: round(8 + r(1) * 84),
      size: Math.round(28 + r(2) * 40),
      delay: round(r(3) * 7),
      duration: round(7 + r(4) * 6),
      drift: Math.round((r(5) - 0.5) * 40),
      // Peak opacity ~0.28–0.48: visible as gentle steam, still atmospheric.
      opacity: round(0.28 + r(6) * 0.2, 3),
    });
  }
  return particles;
}

/**
 * Faint caramel "steam" motes drifting upward over the hero focal art.
 * Atmosphere only: pointer-events-none, low opacity, and fully static when
 * the user prefers reduced motion.
 */
export function SteamField({
  className,
  count = 9,
}: {
  className?: string;
  count?: number;
}) {
  const reduce = useReducedMotion();
  const hydrated = useHydrated();
  const particles = React.useMemo(() => buildParticles(count), [count]);

  // Render only on the client: framer-motion serializes animated style values
  // (e.g. left/opacity) differently than the SSR snapshot, which trips a
  // hydration mismatch. This is decorative + absolutely positioned, so
  // deferring to the client causes no layout shift.
  if (reduce || !hydrated) return null;

  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
    >
      {particles.map((p, i) => (
        <motion.span
          key={i}
          className="absolute bottom-0 rounded-full bg-primary blur-lg"
          style={{
            left: `${p.left}%`,
            width: p.size,
            height: p.size,
          }}
          initial={{ y: 40, x: 0, opacity: 0 }}
          animate={{
            y: [-20, -260],
            x: [0, p.drift],
            opacity: [0, p.opacity, 0],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}

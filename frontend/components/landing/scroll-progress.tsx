"use client";

import { motion, useReducedMotion, useScroll, useSpring } from "framer-motion";

/**
 * Thin caramel rail at the very top of the page that fills with scroll
 * progress — a 2026-standard "where am I on the page" cue. Fixed above the
 * header; honors reduced motion by following scroll without spring easing.
 */
export function ScrollProgress() {
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: reduce ? 1000 : 120,
    damping: reduce ? 100 : 30,
    restDelta: 0.001,
  });

  return (
    <motion.div
      aria-hidden="true"
      style={{ scaleX }}
      className="fixed inset-x-0 top-0 z-[60] h-0.5 origin-left bg-gradient-to-r from-primary/70 via-primary to-primary/40"
    />
  );
}

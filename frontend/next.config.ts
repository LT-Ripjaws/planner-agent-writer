import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the floating Next.js dev badge (the "N" in the lower-left corner).
  // It only ever renders in `next dev` — never in production — but we don't
  // want it during local development either.
  devIndicators: false,
  images: {
    // Serve AVIF first (smaller, supports alpha for the cup/leaf/bean cutouts),
    // WebP next, original last. next/image negotiates per-browser at request time.
    formats: ["image/avif", "image/webp"],
  },
};

export default nextConfig;

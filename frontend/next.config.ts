import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Serve AVIF first (smaller, supports alpha for the cup/leaf/bean cutouts),
    // WebP next, original last. next/image negotiates per-browser at request time.
    formats: ["image/avif", "image/webp"],
  },
};

export default nextConfig;

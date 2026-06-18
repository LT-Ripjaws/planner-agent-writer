import type { Metadata } from "next";
import { Dancing_Script, Fraunces, Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/components/providers";
import { cn } from "@/lib/utils";

import "../styles/globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz", "SOFT"],
  style: ["normal", "italic"],
});

const dancingScript = Dancing_Script({
  variable: "--font-dancing-script",
  subsets: ["latin"],
  display: "swap",
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  title: "BrewNarrate - brew a blog, steeped in research",
  description:
    "A cozy local workspace where an agent researches, plans, and writes a cited blog post while you watch it brew.",
  openGraph: {
    title: "BrewNarrate",
    description: "Brew a blog, steeped in research.",
    images: ["/images/og-cover.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={cn(
        "dark",
        geistSans.variable,
        geistMono.variable,
        fraunces.variable,
        dancingScript.variable,
        "h-full antialiased",
      )}
    >
      <body className="min-h-full bg-background font-sans text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

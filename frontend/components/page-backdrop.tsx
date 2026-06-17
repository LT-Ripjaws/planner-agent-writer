import Image from "next/image";

/**
 * A fixed, softly-blurred full-bleed backdrop for the app (non-landing) pages.
 * Uses the books + cup focal image, zoomed to cover left-to-right, behind a
 * warm scrim so foreground cards stay readable. Decorative only.
 *
 * Requires the host page's <main> to NOT paint a solid background (so this
 * shows through); the espresso base color comes from <body>.
 */
export function PageBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <Image
        src="/images/hero-focal.png"
        alt=""
        fill
        priority
        sizes="100vw"
        className="scale-110 object-cover object-center opacity-30 blur-[3px]"
      />
      {/* Warm scrims: keep the image as atmosphere, never competing with text. */}
      <div className="absolute inset-0 bg-background/72" />
      <div className="absolute inset-0 bg-gradient-to-b from-background/85 via-background/55 to-background" />
    </div>
  );
}

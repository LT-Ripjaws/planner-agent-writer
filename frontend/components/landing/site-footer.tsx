import Image from "next/image";
import Link from "next/link";

import { Brand } from "@/components/brand";

export function SiteFooter() {
  return (
    <footer className="relative overflow-hidden bg-card/30 pb-24 pt-4">
      {/* Full-width bean strip along the bottom, fading up under the content. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 -z-0 h-28">
        <Image
          src="/images/beans.png"
          alt=""
          fill
          sizes="100vw"
          className="object-cover object-bottom opacity-[0.18] [mask-image:linear-gradient(to_top,black,transparent)]"
        />
      </div>
      <div className="relative z-10 mx-auto grid w-full max-w-6xl gap-10 px-6 py-14 sm:grid-cols-[2fr_1fr_1fr]">
        <div className="space-y-3">
          <Brand />
          <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
            Stories, steeped in research. An agent researches, plans, and writes
            a cited draft while you watch it brew.
          </p>
        </div>
        <div className="space-y-3 text-sm">
          <h4 className="font-sans text-sm font-medium text-foreground">
            Product
          </h4>
          <Link
            className="block text-muted-foreground transition-colors hover:text-primary"
            href="#how"
          >
            How it works
          </Link>
          <Link
            className="block text-muted-foreground transition-colors hover:text-primary"
            href="/dashboard"
          >
            The workspace
          </Link>
        </div>
        <div className="space-y-3 text-sm">
          <h4 className="font-sans text-sm font-medium text-foreground">
            Local-first
          </h4>
          <span className="block text-muted-foreground">Runs on your machine</span>
          <span className="block text-muted-foreground">No account needed</span>
        </div>
      </div>
      <div className="relative z-10 border-t border-border/60 py-6 text-center text-xs text-muted-foreground">
        Brewed locally · BrewNarrate
      </div>
    </footer>
  );
}

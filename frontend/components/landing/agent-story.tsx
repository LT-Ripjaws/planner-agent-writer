import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export function AgentStory() {
  return (
    <section className="relative overflow-hidden border-y border-border bg-[hsl(var(--ink))]">
      <div className="relative min-h-[78svh]">
        <Image
          src="/images/agent-story-writing-robots.png"
          alt="Tiny brass writing agents collaborating over coffee and an open book"
          fill
          sizes="100vw"
          className="object-cover"
        />
        {/* Vignette + bottom-left scrim so the copy reads cleanly over the scene. */}
        <div className="absolute inset-0 bg-gradient-to-t from-[hsl(var(--ink))]/92 via-[hsl(var(--ink))]/35 to-[hsl(var(--ink))]/15" />
        <div className="absolute inset-0 bg-gradient-to-r from-[hsl(var(--ink))]/88 via-[hsl(var(--ink))]/30 to-transparent" />

        <div className="relative mx-auto flex min-h-[78svh] w-full max-w-6xl items-end px-6 py-16">
          <div className="max-w-2xl">
            <p className="font-script text-2xl text-primary sm:text-3xl">
              Small agents, serious draft
            </p>
            <h2 className="mt-2 text-balance font-serif text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
              The article brews while the scribes work.
            </h2>
            <p className="mt-5 max-w-xl leading-relaxed text-foreground/80">
              A team of small agents handles the busywork — gathering sources,
              outlining sections, drafting in parallel, and checking every
              citation — so what you get back is a draft you can actually use.
            </p>
            <Button asChild size="lg" className="mt-8 shadow-warm">
              <Link href="/dashboard">
                Start a run
                <ArrowRight />
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

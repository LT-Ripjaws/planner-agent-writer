import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Reveal } from "@/components/landing/reveal";
import { Button } from "@/components/ui/button";

export function Showcase() {
  return (
    <section id="showcase" className="relative overflow-hidden py-24">
      <div className="absolute inset-0 -z-20">
        <Image
          src="/images/workspace-cafe-background.png"
          alt=""
          fill
          sizes="100vw"
          className="scale-105 object-cover"
        />
      </div>
      {/* a lighter overall wash plus a
          stronger fade at the edges so it blends into the page, and the text
          stays legible. */}
      <div className="absolute inset-0 -z-10 bg-[hsl(var(--ink))]/55" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-background via-transparent to-background" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-r from-[hsl(var(--ink))]/70 via-transparent to-[hsl(var(--ink))]/55" />

      <div className="mx-auto grid w-full max-w-6xl items-center gap-10 px-6 lg:grid-cols-2">
        <Reveal>
          <div className="relative overflow-hidden border border-border shadow-warm-lg">
            <Image
              src="/images/workspace-lifestyle.png"
              alt="A cozy late-night writing desk with a laptop and a steaming latte"
              width={1024}
              height={640}
              sizes="(min-width: 1024px) 50vw, 100vw"
              className="h-full w-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-[hsl(var(--ink))]/30 to-transparent" />
          </div>
        </Reveal>

        <Reveal delay={0.1}>
          <p className="font-script text-2xl text-primary">Live agent work</p>
          <h2 className="mt-1 text-balance font-serif text-4xl font-semibold tracking-tight">
            Watch the draft take shape in real time
          </h2>
          <p className="mt-5 leading-relaxed text-muted-foreground">
            Submit a topic, then follow the real pipeline: routing, research,
            planning, parallel section writing, citation checks, and quality
            review. The page is calm, but the work is visible.
          </p>
          <ul className="mt-6 space-y-2 text-sm text-muted-foreground">
            <li className="flex items-center gap-2">
              <span className="size-1.5 bg-primary" />
              Live progress over Server-Sent Events with no refreshing
            </li>
            <li className="flex items-center gap-2">
              <span className="size-1.5 bg-primary" />
              Sources, warnings, plan, quality, and article tabs
            </li>
            <li className="flex items-center gap-2">
              <span className="size-1.5 bg-primary" />
              Resume a failed run from the workspace
            </li>
          </ul>
          <Button asChild size="lg" className="mt-8 shadow-warm">
            <Link href="/dashboard">
              Open the workspace
              <ArrowRight />
            </Link>
          </Button>
        </Reveal>
      </div>
    </section>
  );
}

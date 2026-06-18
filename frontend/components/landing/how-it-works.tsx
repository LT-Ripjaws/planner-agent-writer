"use client";

import * as React from "react";
import Image from "next/image";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { FileText, PenLine, Route, Search, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { RevealGroup, RevealItem } from "@/components/landing/reveal";

type Step = {
  n: string;
  icon: LucideIcon;
  title: string;
  kicker: string;
  body: string;
};

const STEPS: Step[] = [
  {
    n: "01",
    icon: Route,
    title: "Route",
    kicker: "Choose the right mode",
    body: "The agent reads your topic and decides whether to write closed-book, use fresh research, or blend both.",
  },
  {
    n: "02",
    icon: Search,
    title: "Research",
    kicker: "Gather evidence",
    body: "When the web is needed, it searches in parallel, dedupes results, and keeps the strongest source material.",
  },
  {
    n: "03",
    icon: FileText,
    title: "Plan",
    kicker: "Approve the structure",
    body: "It builds a section outline with goals and word targets before spending calls on the full draft.",
  },
  {
    n: "04",
    icon: PenLine,
    title: "Write",
    kicker: "Draft in parallel",
    body: "Writers fan out across the plan so each section is produced from the same topic, evidence, and constraints.",
  },
  {
    n: "05",
    icon: Sparkles,
    title: "Polish",
    kicker: "Guard citations",
    body: "A citation guard checks every link, then a quality pass scores the article and reworks weak sections.",
  },
];

function StoryStep({ step }: { step: Step }) {
  const Icon = step.icon;

  return (
    <RevealItem className="relative pl-16">
      <span className="absolute left-[18px] top-1 flex size-10 -translate-x-1/2 items-center justify-center border border-primary/50 bg-card/95 text-primary shadow-warm">
        <Icon className="size-5" />
      </span>

      <div className="flex items-baseline gap-3">
        <span className="font-serif text-4xl font-semibold leading-none text-primary/90">
          {step.n}
        </span>
        <div>
          <h3 className="font-serif text-2xl font-semibold leading-tight text-foreground">
            {step.title}
          </h3>
          <p className="text-sm font-medium text-primary">{step.kicker}</p>
        </div>
      </div>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
        {step.body}
      </p>
    </RevealItem>
  );
}

export function HowItWorks() {
  const reduce = useReducedMotion();
  const railRef = React.useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: railRef,
    offset: ["start 65%", "end 70%"],
  });
  const fillScale = useTransform(scrollYProgress, [0, 1], [0, 1]);

  return (
    <section id="how" className="relative overflow-hidden py-28">
      <div
        className="pointer-events-none absolute right-[-8vw] top-[-9vw] hidden w-[42vw] max-w-[560px] opacity-[0.13] lg:block"
        aria-hidden="true"
      >
        <Image
          src="/images/leaves.png"
          alt=""
          width={520}
          height={520}
          className="h-auto w-full -scale-x-100"
        />
      </div>

      <div className="mx-auto w-full max-w-6xl px-6">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <p className="font-script text-2xl text-primary">From topic to draft</p>
          <h2 className="mt-1 text-balance font-serif text-4xl font-semibold tracking-tight">
            A visible agent pipeline
          </h2>
          <p className="mt-4 text-muted-foreground">
            BrewNarrate shows each stage as it happens, so the article never
            arrives from a black box.
          </p>
        </div>

        <div className="grid gap-12 lg:grid-cols-2 lg:gap-20">
          <div className="hidden lg:block">
            <div className="sticky top-28">
              <div className="relative">
                <div className="absolute -inset-8 -z-10 bg-primary/10 blur-2xl" />
                <Image
                  src="/images/how-it-works-source-desk.png"
                  alt="A warm research desk with a glowing five-stage writing pipeline"
                  width={620}
                  height={620}
                  className="h-auto w-full max-w-[540px] border border-border/50 brightness-110 contrast-110 saturate-110 shadow-warm-lg"
                />
              </div>
            </div>
          </div>

          <div ref={railRef} className="relative">
            <div className="absolute bottom-2 left-[18px] top-2 w-px -translate-x-1/2 bg-border" />
            <motion.div
              style={{ scaleY: reduce ? 1 : fillScale }}
              className="absolute bottom-2 left-[18px] top-2 w-px -translate-x-1/2 origin-top bg-gradient-to-b from-primary to-primary/40"
            />
            <RevealGroup className="space-y-14">
              {STEPS.map((step) => (
                <StoryStep key={step.n} step={step} />
              ))}
            </RevealGroup>
          </div>
        </div>
      </div>
    </section>
  );
}

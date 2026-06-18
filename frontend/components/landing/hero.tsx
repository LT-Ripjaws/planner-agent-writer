"use client";

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import {
  motion,
  useReducedMotion,
  useScroll,
  useTransform,
  type Variants,
} from "framer-motion";
import { ArrowRight, ListChecks, PenLine, Quote, Search } from "lucide-react";

import { SteamField } from "@/components/landing/steam-field";
import { Button } from "@/components/ui/button";

const PRODUCT_SIGNALS = [
  { icon: Search, label: "Researches the web" },
  { icon: ListChecks, label: "Plans first" },
  { icon: PenLine, label: "Writes in parallel" },
  { icon: Quote, label: "Cites sources" },
];

const LINE_ONE = ["BrewNarrate", "turns", "topics"];
const LINE_TWO = ["into", "cited", "drafts."];

const EASE = [0.22, 1, 0.36, 1] as const;

// On-load stagger for the whole intro column.
const containerVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
};

const wordVariants: Variants = {
  hidden: { opacity: 0, y: "0.5em" },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE } },
};

const blockVariants: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE } },
};

export function Hero() {
  const reduce = useReducedMotion();
  const ref = React.useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });

  const photoY = useTransform(scrollYProgress, [0, 1], ["0%", reduce ? "0%" : "12%"]);
  const photoScale = useTransform(scrollYProgress, [0, 1], [1, reduce ? 1 : 1.08]);
  const textY = useTransform(scrollYProgress, [0, 1], ["0%", reduce ? "0%" : "-6%"]);
  const fade = useTransform(scrollYProgress, [0, 0.85], [1, reduce ? 1 : 0]);

  // With reduced motion we render everything in its final state (no stagger).
  const animProps = reduce
    ? {}
    : { variants: containerVariants, initial: "hidden", animate: "show" };

  // A line of words; the accent line gets a base delay so it "draws in last".
  const renderLine = (words: string[], accent = false, baseDelay = 0) =>
    words.map((word, i) => (
      <motion.span
        key={`${word}-${i}`}
        className="inline-block whitespace-nowrap"
        variants={reduce ? undefined : wordVariants}
        transition={
          reduce ? undefined : { duration: 0.55, ease: EASE, delay: baseDelay }
        }
      >
        <span className={accent ? "text-primary" : undefined}>{word}</span>
        {i < words.length - 1 ? " " : null}
      </motion.span>
    ));

  return (
    <section
      ref={ref}
      className="relative flex min-h-[86svh] items-center overflow-hidden"
    >
      <motion.div
        style={{ y: photoY, scale: photoScale }}
        className="absolute inset-0 -z-20 origin-center"
      >
        <Image
          src="/images/landing-hero-writing-agent.png"
          alt="A brass writing automaton drafting in a warm library workspace"
          fill
          priority
          sizes="100vw"
          className="object-cover object-[67%_center] sm:object-center"
        />
      </motion.div>

      {/* Layered warm overlay so the headline stays legible over the photo. */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-r from-[hsl(var(--ink))]/95 from-15% via-[hsl(var(--ink))]/70 to-[hsl(var(--ink))]/15" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-t from-[hsl(var(--ink))]/85 via-transparent to-[hsl(var(--ink))]/40" />
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(120%_90%_at_70%_40%,transparent,hsl(var(--ink))/0.35)]" />
      <div className="absolute inset-x-0 bottom-0 -z-10 h-40 bg-gradient-to-b from-transparent to-background" />

      {/* Steam drifting up over the right-side focal art. */}
      <SteamField className="left-1/2 -z-10 hidden sm:block" count={9} />

      <div className="w-full px-6 py-24 sm:px-8 lg:px-10">
        <motion.div style={{ y: textY, opacity: fade }} className="max-w-2xl">
          <motion.div {...animProps}>
            <motion.p
              className="font-script text-2xl text-primary sm:text-3xl"
              variants={reduce ? undefined : blockVariants}
            >
              Research, drafted by an agent
            </motion.p>

            <h1 className="mt-2 font-serif text-5xl font-semibold leading-[1.04] tracking-tight text-foreground sm:text-6xl lg:text-7xl">
              <span className="block">{renderLine(LINE_ONE)}</span>
              <span className="mt-1 block">
                {renderLine(LINE_TWO, true, reduce ? 0 : 0.25)}
              </span>
            </h1>

            <motion.p
              className="mt-6 max-w-lg text-lg leading-relaxed text-foreground/80"
              variants={reduce ? undefined : blockVariants}
            >
              Give it a topic. It researches the web, plans the outline, writes
              every section, and checks the citations and you watch it happen,
              live.
            </motion.p>

            <motion.div
              className="mt-8 flex flex-wrap items-center gap-3"
              variants={reduce ? undefined : blockVariants}
            >
              <Button asChild size="lg" className="shadow-warm">
                <Link href="/dashboard">
                  Start brewing
                  <ArrowRight />
                </Link>
              </Button>
              <Button
                asChild
                size="lg"
                variant="outline"
                className="border-foreground/30 bg-foreground/5 text-foreground backdrop-blur-sm hover:bg-foreground/10 hover:text-foreground"
              >
                <Link href="#how">How it works</Link>
              </Button>
            </motion.div>

            <motion.ul
              className="mt-10 grid max-w-xl grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:gap-x-5 sm:gap-y-3"
              variants={reduce ? undefined : blockVariants}
            >
              {PRODUCT_SIGNALS.map(({ icon: Icon, label }) => (
                <li
                  key={label}
                  className="flex items-center gap-2 text-sm text-foreground/80"
                >
                  <span className="flex size-7 items-center justify-center rounded-full bg-primary/18 text-primary ring-1 ring-primary/25">
                    <Icon className="size-3.5" />
                  </span>
                  {label}
                </li>
              ))}
            </motion.ul>
          </motion.div>
        </motion.div>
      </div>

      <motion.div
        style={{ opacity: fade }}
        className="absolute inset-x-0 bottom-5 flex justify-center"
      >
        <span className="flex h-9 w-5 items-start justify-center rounded-full border border-foreground/30 p-1">
          <motion.span
            className="h-1.5 w-1 rounded-full bg-primary"
            animate={reduce ? undefined : { y: [0, 10, 0] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          />
        </span>
      </motion.div>
    </section>
  );
}

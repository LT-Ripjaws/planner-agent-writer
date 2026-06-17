import Link from "next/link";
import { ArrowLeft, History } from "lucide-react";

import { ActiveRunCard } from "@/components/active-run-card";
import { Brand } from "@/components/brand";
import { PageBackdrop } from "@/components/page-backdrop";
import { QuickStats } from "@/components/quick-stats";
import { RunList } from "@/components/run-list";
import { TopicForm } from "@/components/topic-form";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      <PageBackdrop />
      {/* Warm top glow over the backdrop, behind the launcher. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[28rem] bg-[radial-gradient(60%_100%_at_25%_0%,hsl(var(--primary)/0.12),transparent_70%)]" />

      <header className="relative border-b border-border/60 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8">
          <Brand />
          <Button asChild variant="ghost" size="sm">
            <Link href="/">
              <ArrowLeft className="size-4" />
              Go Back
            </Link>
          </Button>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-8 px-5 py-10 lg:grid-cols-[minmax(0,1fr)_24rem] lg:px-8">
        <section className="space-y-6">
          <div>
            <p className="font-script text-2xl text-primary sm:text-3xl">
              Your brewing station
            </p>
            <h1 className="mt-1 font-serif text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
              Brew a cited draft.
            </h1>
            <p className="mt-3 max-w-2xl leading-7 text-muted-foreground">
              Hand the agent a topic, choose how much it should research, and
              watch the pipeline assemble a sourced article live.
            </p>
          </div>

          {/* Primary action — lifted with a caramel top accent so the eye lands here. */}
          <div className="relative border border-primary/25 bg-card/80 p-5 shadow-warm-lg md:p-6">
            <span className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-primary/70 via-primary to-primary/40" />
            <TopicForm />
          </div>
        </section>

        <aside className="space-y-5">
          <ActiveRunCard />
          <QuickStats />
        </aside>
      </div>

      <section className="mx-auto max-w-7xl px-5 pb-16 lg:px-8">
        <div className="mb-4 flex items-center gap-2">
          <History className="size-4 text-primary" />
          <h2 className="font-serif text-2xl font-semibold tracking-tight text-foreground">
            Recent brews
          </h2>
        </div>
        <RunList />
      </section>
    </main>
  );
}

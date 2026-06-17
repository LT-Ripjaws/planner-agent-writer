import Link from "next/link";
import { ArrowLeft, AlertCircle, SearchX } from "lucide-react";

import { ApiError, getRun } from "@/lib/api";
import type { BlogRunDetail } from "@/lib/types";
import { Brand } from "@/components/brand";
import { PageBackdrop } from "@/components/page-backdrop";
import { RunDetailClient } from "@/components/run-detail-client";
import { Button } from "@/components/ui/button";

function LookupState({
  kind,
  runId,
}: {
  kind: "missing" | "backend";
  runId: string;
}) {
  const Icon = kind === "missing" ? SearchX : AlertCircle;
  return (
    <div className="mx-auto max-w-3xl px-5 py-20 text-center">
      <Icon className="mx-auto size-10 text-primary" />
      <h1 className="mt-6 text-3xl font-semibold">
        {kind === "missing" ? "Run not found" : "Backend unavailable"}
      </h1>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        {kind === "missing"
          ? `No run exists for ${runId}.`
          : "The frontend could not reach the FastAPI server on port 8000."}
      </p>
      <Button asChild className="mt-6">
        <Link href="/dashboard">
          <ArrowLeft className="size-4" />
          Back to dashboard
        </Link>
      </Button>
    </div>
  );
}

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let kind: "missing" | "backend" | null = null;
  let run: BlogRunDetail | null = null;

  try {
    run = await getRun(id, { cache: "no-store" });
  } catch (error) {
    kind = error instanceof ApiError && error.status === 404 ? "missing" : "backend";
  }

  if (!run) {
    return (
      <main className="relative min-h-screen">
        <PageBackdrop />
        <header className="border-b border-border/60 bg-background/70 backdrop-blur-md">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8">
            <Brand href="/dashboard" />
          </div>
        </header>
        <LookupState kind={kind ?? "backend"} runId={id} />
      </main>
    );
  }

  return (
    <main className="relative min-h-screen">
      <PageBackdrop />
      <header className="border-b border-border/60 bg-background/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8">
          <Brand href="/dashboard" />
          <Button asChild variant="ghost" size="sm">
            <Link href="/dashboard">
              <ArrowLeft className="size-4" />
              Dashboard
            </Link>
          </Button>
        </div>
      </header>
      <RunDetailClient runId={id} initialRun={run} />
    </main>
  );
}

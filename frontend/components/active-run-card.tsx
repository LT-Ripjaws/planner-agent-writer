"use client";

import Link from "next/link";
import { ArrowRight, Coffee, RotateCcw } from "lucide-react";

import { formatRelativeTime } from "@/lib/format";
import { isLiveRun, useRuns } from "@/lib/use-runs";
import { StatusBadge } from "@/components/status-badge";
import { ResumeButton } from "@/components/resume-button";
import { DeleteRunButton } from "@/components/delete-run-button";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function ActiveRunCard() {
  const { data: runs, isLoading } = useRuns(20);

  if (isLoading) return <Skeleton className="h-44 w-full" />;

  const active = runs?.find(isLiveRun);
  const failed = runs?.find((run) => run.status === "failed");

  if (active) {
    return (
      <div className="border bg-card/70 p-5">
        <div className="flex items-center justify-between gap-3">
          <StatusBadge status={active.status} />
          <span className="font-mono text-xs text-muted-foreground">
            {formatRelativeTime(active.updated_at)}
          </span>
        </div>
        <h3 className="mt-5 line-clamp-2 font-serif text-xl font-semibold leading-7">
          {active.blog_title || active.topic}
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          The latest live run is ready to watch.
        </p>
        <Button asChild className="mt-5 w-full">
          <Link href={`/runs/${active.id}`}>
            Open timeline
            <ArrowRight className="size-4" />
          </Link>
        </Button>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="border border-warning/30 bg-warning/10 p-5">
        <div className="flex items-center gap-2 text-warning">
          <RotateCcw className="size-4" />
          <span className="text-sm font-medium">Resume failed run</span>
        </div>
        <h3 className="mt-5 line-clamp-2 font-serif text-xl font-semibold leading-7 text-foreground">
          {failed.blog_title || failed.topic}
        </h3>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <ResumeButton runId={failed.id} />
          <Button asChild variant="ghost" size="sm">
            <Link href={`/runs/${failed.id}`}>
              Inspect
              <ArrowRight className="size-4" />
            </Link>
          </Button>
          <DeleteRunButton
            runId={failed.id}
            title={failed.blog_title || failed.topic}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="border bg-card/55 p-5">
      <Coffee className="size-5 text-primary" />
      <h3 className="mt-5 font-serif text-xl font-semibold">No active brew</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        Start a topic and the live pipeline will appear here.
      </p>
    </div>
  );
}

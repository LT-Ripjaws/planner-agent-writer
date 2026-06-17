"use client";

import Image from "next/image";
import Link from "next/link";
import { AlertCircle, ArrowRight, History } from "lucide-react";

import { formatRelativeTime, humanizeToken } from "@/lib/format";
import { useRuns } from "@/lib/use-runs";
import { DeleteRunButton } from "@/components/delete-run-button";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const deletableStatuses = new Set([
  "completed",
  "completed_with_warnings",
  "failed",
]);

export function RunList() {
  const { data: runs, error, isLoading } = useRuns(20);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((item) => (
          <Skeleton key={item} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="border border-destructive/35 bg-destructive/10 p-4 text-sm text-destructive">
        <div className="flex items-center gap-2 font-medium">
          <AlertCircle className="size-4" />
          Backend unavailable
        </div>
        <p className="mt-2 text-destructive/85">
          Start the FastAPI server on port 8000, then refresh this panel.
        </p>
      </div>
    );
  }

  if (!runs?.length) {
    return (
      <div className="relative min-h-52 overflow-hidden border bg-card/55 p-6">
        <Image
          src="/images/empty-state.png"
          alt=""
          width={180}
          height={180}
          className="pointer-events-none absolute -right-4 bottom-0 opacity-35"
        />
        <History className="size-5 text-primary" />
        <h3 className="mt-4 font-serif text-xl font-semibold text-foreground">
          Nothing brewing yet
        </h3>
        <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
          Your recent drafts, pauses, and finished articles will collect here.
        </p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-border border bg-card/60">
      {runs.map((run) => {
        const title = run.blog_title || run.topic;
        const canDelete = deletableStatuses.has(run.status);

        return (
          <div
            key={run.id}
            className="group flex items-start justify-between gap-4 p-4 transition-colors hover:bg-accent/45"
          >
            <Link href={`/runs/${run.id}`} className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={run.status} size="sm" />
                {run.mode ? (
                  <span className="font-mono text-[11px] uppercase tracking-normal text-muted-foreground">
                    {humanizeToken(run.mode)}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 line-clamp-2 font-serif text-base leading-6 text-foreground transition-colors group-hover:text-primary">
                {title}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {formatRelativeTime(run.updated_at)}
              </p>
            </Link>
            <div className="flex shrink-0 items-center gap-1">
              {canDelete ? (
                <DeleteRunButton
                  runId={run.id}
                  title={title}
                  className="text-muted-foreground opacity-70 transition-all hover:text-destructive hover:opacity-100"
                />
              ) : null}
              <Button
                asChild
                size="icon"
                variant="ghost"
                className="text-muted-foreground opacity-70 transition-all group-hover:translate-x-0.5 group-hover:text-primary group-hover:opacity-100"
                aria-label="Open run"
              >
                <Link href={`/runs/${run.id}`}>
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
